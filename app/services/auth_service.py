import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    DuplicateResourceException,
    ResourceNotFoundException,
    ValidationErrorException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models.user import User
from app.db.repositories.refresh_session_repository import RefreshSessionRepository
from app.db.repositories.user_repository import UserRepository
from app.services.redis.redis_auth_service import redis_auth_service
from app.v1.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.v1.schemas.user import UserResponse

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.session_repo = RefreshSessionRepository(session)

    async def register(
        self,
        payload: RegisterRequest,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        # Normalize email
        email = payload.email.strip().lower()

        # Check existing user
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            raise DuplicateResourceException(f"User with email '{email}' already exists.")

        # Hash password using Argon2id
        pwd_hash = hash_password(payload.password)

        # Public registration always assigns CUSTOMER role
        user = await self.user_repo.create(
            email=email,
            password_hash=pwd_hash,
            first_name=payload.first_name,
            last_name=payload.last_name,
            role=UserRole.CUSTOMER,
            is_active=True,
            is_verified=False,
        )

        return await self._create_tokens_and_session(user, user_agent, ip_address)

    async def login(
        self,
        payload: LoginRequest,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        email = payload.email.strip().lower()
        user = await self.user_repo.get_by_email(email)

        # Generic failure message prevents user enumeration
        if not user or not verify_password(payload.password, user.password_hash):
            raise AuthenticationException("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationException("User account is inactive. Please contact support.")

        return await self._create_tokens_and_session(user, user_agent, ip_address)

    async def refresh(
        self,
        refresh_token_raw: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        # 1. Decode token and validate signature & expiration
        payload = decode_token(refresh_token_raw)

        # 2. Validate token type
        if payload.get("type") != "refresh":
            raise AuthenticationException("Invalid token type. Expected refresh token.")

        user_id_str = payload.get("sub")
        session_id_str = payload.get("jti")
        if not user_id_str or not session_id_str:
            raise AuthenticationException("Invalid token claims.")

        try:
            user_id = uuid.UUID(user_id_str)
            session_id = uuid.UUID(session_id_str)
        except ValueError:
            raise AuthenticationException("Malformed token identifiers.")

        # 3. Lookup session in database (PostgreSQL is durable source of truth)
        refresh_session = await self.session_repo.get_by_id(session_id)
        if not refresh_session:
            raise AuthenticationException("Refresh session not found or has expired.")

        # 4. REUSE DETECTION: If session was already revoked, someone is reusing an old token!
        if refresh_session.revoked_at is not None:
            # Revoke all sessions for this user to protect account
            logger.warning(
                f"SECURITY ALERT: Refresh token reuse detected for user {user_id}. "
                f"Session {session_id} was already revoked. Invalidate all user sessions."
            )
            await self.session_repo.revoke_all_for_user(user_id)
            await redis_auth_service.revoke_cached_session(session_id)
            raise AuthenticationException("Revoked refresh token presented. Security reuse detected. Please log in again.")

        # 5. Check session expiration
        now = datetime.now(timezone.utc)
        if refresh_session.expires_at <= now:
            raise AuthenticationException("Refresh session has expired. Please log in again.")

        # 6. Verify cryptographic hash of supplied token matches stored hash
        supplied_hash = hash_token(refresh_token_raw)
        if supplied_hash != refresh_session.token_hash:
            raise AuthenticationException("Invalid refresh token hash.")

        # 7. Check user status
        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationException("User account is inactive or not found.")

        # 8. ROTATION:
        # Generate new session ID and new tokens
        new_session_id = uuid.uuid4()
        new_refresh_token, new_refresh_expires_at = create_refresh_token(user.id, new_session_id)
        new_token_hash = hash_token(new_refresh_token)

        # Create new session in DB
        new_session = await self.session_repo.create(
            user_id=user.id,
            token_hash=new_token_hash,
            expires_at=new_refresh_expires_at,
            session_id=new_session_id,
            user_agent=user_agent or refresh_session.user_agent,
            ip_address=ip_address or refresh_session.ip_address,
        )

        # Revoke old session and link to replacement
        await self.session_repo.revoke(refresh_session, replaced_by_session_id=new_session.id)

        # Update Redis: revoke old session, cache new session
        await redis_auth_service.revoke_cached_session(session_id)
        await redis_auth_service.cache_refresh_session(
            new_session_id, user.id, new_token_hash, new_refresh_expires_at
        )

        # Generate new 15-minute access token
        access_token, _ = create_access_token(user.id, user.role.value)

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    async def logout(self, refresh_token_raw: str) -> None:
        """Revokes the refresh session in both DB and Redis."""
        try:
            payload = decode_token(refresh_token_raw)
            if payload.get("type") == "refresh" and payload.get("jti"):
                session_id = uuid.UUID(payload["jti"])
                session = await self.session_repo.get_by_id(session_id)
                if session and session.revoked_at is None:
                    await self.session_repo.revoke(session)
                await redis_auth_service.revoke_cached_session(session_id)
        except Exception as e:
            logger.debug(f"Logout session revocation handled gracefully: {e}")

    async def _create_tokens_and_session(
        self,
        user: User,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        session_id = uuid.uuid4()
        refresh_token, refresh_expires_at = create_refresh_token(user.id, session_id)
        token_hash = hash_token(refresh_token)

        # Durable record in PostgreSQL
        await self.session_repo.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=refresh_expires_at,
            session_id=session_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Fast lookup cache in Redis
        await redis_auth_service.cache_refresh_session(
            session_id, user.id, token_hash, refresh_expires_at
        )

        access_token, _ = create_access_token(user.id, user.role.value)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )
