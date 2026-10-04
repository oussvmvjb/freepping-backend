import uuid
from typing import Callable, Optional
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    RateLimitException,
)
from app.core.security import decode_token
from app.db.models.user import User
from app.db.repositories.user_repository import UserRepository
from app.db.session import get_db
from app.services.redis.redis_auth_service import redis_auth_service

# Bearer security scheme for Swagger / OpenAPI documentation
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validates the bearer access JWT and loads the current user from PostgreSQL.
    Guarantees user identity is always derived from the token and reflects latest DB state.
    """
    if not credentials or not credentials.credentials:
        raise AuthenticationException("Not authenticated. Bearer token is missing.")

    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise AuthenticationException("Invalid token type. Expected access token.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthenticationException("Token missing subject identifier.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise AuthenticationException("Invalid user identifier format in token.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise AuthenticationException("User not found.")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verifies that the authenticated user account is active."""
    if not current_user.is_active:
        raise AuthenticationException("User account is inactive.")
    return current_user


# Alias for clarity
require_authenticated_user = get_current_active_user


async def require_super_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Requires the caller to be a SUPER_ADMIN."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise AuthorizationException("This operation requires SUPER_ADMIN privileges.")
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Requires the caller to be an ADMIN or SUPER_ADMIN."""
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
        raise AuthorizationException("This operation requires ADMIN privileges.")
    return current_user


async def require_seller(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Requires the caller to be a SELLER."""
    if current_user.role != UserRole.SELLER:
        raise AuthorizationException("This operation requires SELLER privileges.")
    return current_user


async def require_seller_or_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Requires the caller to be a SELLER, ADMIN, or SUPER_ADMIN."""
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SELLER]:
        raise AuthorizationException("This operation requires SELLER or ADMIN privileges.")
    return current_user


def check_rate_limit(action: str, max_requests: int) -> Callable:
    """FastAPI dependency for endpoint rate limiting using Redis."""
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        # Forwarded-For support if behind a proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        allowed = await redis_auth_service.check_rate_limit(
            identifier=client_ip,
            action=action,
            max_requests=max_requests,
            window_seconds=60,
        )
        if not allowed:
            raise RateLimitException(f"Too many {action} requests. Please wait a minute and try again.")

    return dependency
