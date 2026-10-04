from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_rate_limit, get_current_active_user
from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.services.auth_service import AuthService
from app.v1.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.v1.schemas.user import UserResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new customer account",
    description="Registers a new user with CUSTOMER role and returns authentication tokens. Role cannot be self-selected.",
    dependencies=[Depends(check_rate_limit("register", settings.RATE_LIMIT_REGISTER_PER_MINUTE))],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None
    return await service.register(payload, user_agent=user_agent, ip_address=ip_address)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with email and password",
    description="Validates credentials, creates a refresh session, and returns access and refresh tokens.",
    dependencies=[Depends(check_rate_limit("login", settings.RATE_LIMIT_LOGIN_PER_MINUTE))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None
    return await service.login(payload, user_agent=user_agent, ip_address=ip_address)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue new access token",
    description="Validates the refresh token, revokes the old session, creates a new session, and returns a new token pair. If a revoked token is used, reuse detection invalidates all sessions for that user.",
    dependencies=[Depends(check_rate_limit("refresh", settings.RATE_LIMIT_REFRESH_PER_MINUTE))],
)
async def refresh_tokens(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    service = AuthService(db)
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None
    return await service.refresh(payload.refresh_token, user_agent=user_agent, ip_address=ip_address)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out and revoke refresh session",
    description="Revokes the refresh token session in PostgreSQL and invalidates the Redis cache entry.",
)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(db)
    await service.logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
    description="Retrieves the authenticated user profile derived from the validated access token.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
