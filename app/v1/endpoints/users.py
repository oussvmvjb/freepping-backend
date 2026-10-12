import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_admin
from app.core.enums import UserRole
from app.core.exceptions import ResourceNotFoundException
from app.db.models.user import User
from app.db.repositories.saved_payment_method_repository import SavedPaymentMethodRepository
from app.db.session import get_db
from app.services.address_service import AddressService
from app.services.like_service import LikeService
from app.services.user_service import UserService
from app.v1.schemas.address import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
)
from app.v1.schemas.product import ProductListResponse
from app.v1.schemas.saved_payment_method import SavedPaymentMethodResponse
from app.v1.schemas.user import (
    UserListResponse,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)

router = APIRouter()


# ── Current User Endpoints (/users/me/...) ────────────────────────────────────

@router.get(
    "/me/favorites",
    response_model=ProductListResponse,
    tags=["Likes"],
    summary="Get user favorite products",
    description="Returns paginated products liked by the current authenticated user.",
)
async def get_my_favorites(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProductListResponse:
    service = LikeService(db)
    return await service.list_user_favorites(current_user, page=page, page_size=page_size)


@router.get(
    "/me/addresses",
    response_model=List[AddressResponse],
    tags=["Addresses"],
    summary="List my shipping addresses",
    description="Returns all shipping addresses for the authenticated user with the default address first.",
)
async def list_my_addresses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[AddressResponse]:
    service = AddressService(db)
    return await service.list_addresses(current_user)


@router.post(
    "/me/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Addresses"],
    summary="Create shipping address",
    description="Creates a new address. If marked as default or first address, becomes default.",
)
async def create_address(
    address_in: AddressCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AddressResponse:
    service = AddressService(db)
    return await service.create_address(current_user, address_in)


@router.patch(
    "/me/addresses/{address_id}",
    response_model=AddressResponse,
    tags=["Addresses"],
    summary="Update shipping address",
    description="Updates existing address fields.",
)
async def update_address(
    address_id: uuid.UUID,
    address_in: AddressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AddressResponse:
    service = AddressService(db)
    return await service.update_address(address_id, current_user, address_in)


@router.delete(
    "/me/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Addresses"],
    summary="Delete shipping address",
    description="Deletes address. If default was deleted, promotes the next address to default.",
)
async def delete_address(
    address_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    service = AddressService(db)
    await service.delete_address(address_id, current_user)


@router.patch(
    "/me/addresses/{address_id}/default",
    response_model=AddressResponse,
    tags=["Addresses"],
    summary="Set address as default",
    description="Sets specified address as default and clears default on all other user addresses.",
)
async def set_default_address(
    address_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AddressResponse:
    service = AddressService(db)
    return await service.set_default_address(address_id, current_user)


@router.get(
    "/me/payment-methods",
    response_model=List[SavedPaymentMethodResponse],
    tags=["Checkout"],
    summary="List saved payment methods",
    description="Returns tokenized saved payment methods for the authenticated user.",
)
async def list_payment_methods(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[SavedPaymentMethodResponse]:
    repo = SavedPaymentMethodRepository(db)
    methods = await repo.list_by_user(current_user.id)
    return [SavedPaymentMethodResponse.model_validate(m) for m in methods]


@router.delete(
    "/me/payment-methods/{method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Checkout"],
    summary="Delete saved payment method",
    description="Removes saved payment method from user profile.",
)
async def delete_payment_method(
    method_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    repo = SavedPaymentMethodRepository(db)
    method = await repo.get_by_id_and_user(method_id, current_user.id)
    if not method:
        raise ResourceNotFoundException("Saved payment method", method_id)
    await repo.delete(method)


# ── Administrative Endpoints ──────────────────────────────────────────────────

@router.get(
    "",
    response_model=UserListResponse,
    tags=["Users"],
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
    tags=["Users"],
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
    tags=["Users"],
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
    tags=["Users"],
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
