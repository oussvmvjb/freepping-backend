from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.order_service import OrderService
from app.v1.schemas.order import (
    CheckoutPlaceOrderRequest,
    CheckoutPreviewRequest,
    CheckoutPreviewResponse,
    OrderResponse,
)

router = APIRouter()


@router.post(
    "/preview",
    response_model=CheckoutPreviewResponse,
    summary="Checkout preview",
    description="Returns order pricing calculation before placing an order.",
)
async def checkout_preview(
    preview_in: CheckoutPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> CheckoutPreviewResponse:
    service = OrderService(db)
    return await service.preview_checkout(current_user, preview_in)


@router.post(
    "/place-order",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place order",
    description=(
        "Executes checkout in an atomic transaction: locks inventory with FOR UPDATE, "
        "recomputes totals, applies discounts, charges payment / verifies gift card, "
        "deducts stock, and creates order records. Supports Idempotency-Key header."
    ),
)
async def place_order(
    checkout_in: CheckoutPlaceOrderRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrderResponse:
    service = OrderService(db)
    return await service.place_order(current_user, checkout_in, idempotency_key=idempotency_key)
