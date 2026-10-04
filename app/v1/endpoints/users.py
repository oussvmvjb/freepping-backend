import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import math

from app.api.deps import require_admin, require_super_admin
from app.core.enums import UserRole
from app.db.models.user import User
from app.db.session import get_db
from app.services.user_service import UserService
from app.v1.schemas.user import (
    UserListResponse,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)

router = APIRouter()


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users",
    description="Lists users with optional role and search filters. Requires ADMIN or SUPER_ADMIN.",
)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[UserRole] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserListResponse:
    service = UserService(db)
    users, total = await service.list_users(page, page_size, role, search)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Returns a user by their UUID. Requires ADMIN or SUPER_ADMIN.",
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    service = UserService(db)
    user = await service.get_user_by_id(user_id)
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change user role",
    description=(
        "SUPER_ADMIN: can change any role. "
        "ADMIN: can only toggle CUSTOMER <-> SELLER."
    ),
)
async def update_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    service = UserService(db)
    user = await service.update_user_role(user_id, payload.role, current_user)
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    summary="Activate or deactivate user account",
    description="Requires ADMIN or SUPER_ADMIN.",
)
async def update_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserResponse:
    service = UserService(db)
    user = await service.update_user_status(user_id, payload.is_active, current_user)
    return UserResponse.model_validate(user)
