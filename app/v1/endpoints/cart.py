import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.cart_service import CartService
from app.v1.schemas.cart import (
    ApplyPromoRequest,
    CartItemAdd,
    CartItemUpdate,
    CartResponse,
    GiftWrapRequest,
)

router = APIRouter()


@router.get(
    "",
    response_model=CartResponse,
    summary="Get shopping cart",
    description="Returns current authenticated user's cart with prices, discounts, and line totals.",
)
async def get_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.get_cart(current_user)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add item to cart",
    description="Adds a product/variant to the cart. Merges quantity if line item already exists.",
)
async def add_cart_item(
    item_in: CartItemAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.add_item(current_user, item_in)


@router.patch(
    "/items/{item_id}",
    response_model=CartResponse,
    summary="Update cart item quantity",
    description="Updates quantity for an existing cart item.",
)
async def update_cart_item(
    item_id: uuid.UUID,
    item_in: CartItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.update_item_quantity(current_user, item_id, item_in.quantity)


@router.delete(
    "/items/{item_id}",
    response_model=CartResponse,
    summary="Remove item from cart",
    description="Deletes a line item from the cart.",
)
async def delete_cart_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.delete_item(current_user, item_id)


@router.delete(
    "",
    response_model=CartResponse,
    summary="Clear shopping cart",
    description="Removes all line items from current user's cart.",
)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.clear_cart(current_user)


@router.post(
    "/promo",
    response_model=CartResponse,
    summary="Apply promo code to cart",
    description="Validates and applies a discount promo code to the cart.",
)
async def apply_promo(
    promo_in: ApplyPromoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.apply_promo(current_user, promo_in.code)


@router.delete(
    "/promo",
    response_model=CartResponse,
    summary="Remove promo code from cart",
    description="Removes any currently applied promo code from the cart.",
)
async def remove_promo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.remove_promo(current_user)


@router.patch(
    "/gift-wrap",
    response_model=CartResponse,
    summary="Toggle gift wrapping",
    description="Enables or disables gift wrap service on the cart.",
)
async def toggle_gift_wrap(
    wrap_in: GiftWrapRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CartResponse:
    service = CartService(db)
    return await service.toggle_gift_wrap(current_user, wrap_in.enabled)
