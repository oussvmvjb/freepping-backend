from datetime import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.models.user import User
from app.db.session import get_db
from app.services.dashboard_service import DashboardService
from app.services.delivery_option_service import DeliveryOptionService
from app.services.gift_card_service import GiftCardService
from app.services.like_service import LikeService
from app.services.order_service import OrderService
from app.services.promo_service import PromoService
from app.v1.schemas.dashboard import (
    AdminDashboardSummary,
    LowStockInventoryResponse,
    LowStockVariantItem,
    VariantStockUpdateRequest,
)
from app.v1.schemas.delivery_option import (
    DeliveryOptionCreate,
    DeliveryOptionResponse,
    DeliveryOptionUpdate,
)
from app.v1.schemas.gift_card import (
    GiftCardCreateAdmin,
    GiftCardCreatedAdminResponse,
    GiftCardListResponse,
    GiftCardResponse,
    GiftCardUpdateAdmin,
)
from app.v1.schemas.order import (
    OrderListResponse,
    OrderResponse,
    OrderStatusUpdateRequest,
)
from app.v1.schemas.product import ProductLikersListResponse
from app.v1.schemas.promo_code import (
    PromoCodeCreate,
    PromoCodeListResponse,
    PromoCodeResponse,
    PromoCodeUpdate,
)

router = APIRouter()


# ── Dashboard & Analytics ─────────────────────────────────────────────────────

@router.get(
    "/dashboard/summary",
    response_model=AdminDashboardSummary,
    summary="Admin dashboard analytics summary",
    description="Returns aggregate sales, orders by status, top products, and revenue time-series. Cached in Redis for 60s.",
)
async def get_dashboard_summary(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> AdminDashboardSummary:
    service = DashboardService(db)
    return await service.get_admin_summary(date_from=date_from, date_to=date_to)


# ── Orders Management ─────────────────────────────────────────────────────────

@router.get(
    "/orders",
    response_model=OrderListResponse,
    summary="List all platform orders",
    description="Paginated list of orders with filters for status, payment status, user, and date range.",
)
async def list_admin_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None),
    user_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> OrderListResponse:
    service = OrderService(db)
    return await service.list_admin_orders(
        page=page,
        page_size=page_size,
        status=status,
        payment_status=payment_status,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    summary="Get order details (admin)",
)
async def get_admin_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> OrderResponse:
    service = OrderService(db)
    return await service.get_order_by_id(order_id, admin_user)


@router.patch(
    "/orders/{order_id}/status",
    response_model=OrderResponse,
    summary="Update order status (admin)",
    description="Transitions order status, updates timestamps, and logs an order_status_history entry.",
)
async def update_order_status(
    order_id: uuid.UUID,
    status_in: OrderStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> OrderResponse:
    service = OrderService(db)
    return await service.admin_update_order_status(order_id, status_in, admin_user)


@router.post(
    "/orders/{order_id}/refund",
    response_model=OrderResponse,
    summary="Refund order (admin)",
    description="Processes full refund via payment gateway/gift card, sets status to REFUNDED, and restocks items.",
)
async def refund_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> OrderResponse:
    service = OrderService(db)
    return await service.admin_refund_order(order_id, admin_user)


# ── Inventory Management ──────────────────────────────────────────────────────

@router.get(
    "/inventory/low-stock",
    response_model=LowStockInventoryResponse,
    summary="List low stock variants",
    description="Retrieves product variants with stock at or below the given threshold.",
)
async def get_low_stock_inventory(
    threshold: int = Query(5, ge=0),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> LowStockInventoryResponse:
    service = DashboardService(db)
    return await service.get_low_stock_inventory(threshold=threshold)


@router.patch(
    "/variants/{variant_id}/stock",
    response_model=LowStockVariantItem,
    summary="Update variant stock quantity",
    description="Directly updates inventory count for a variant and invalidates product caches.",
)
async def update_variant_stock(
    variant_id: uuid.UUID,
    payload: VariantStockUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> LowStockVariantItem:
    service = DashboardService(db)
    return await service.update_variant_stock(variant_id, payload.stock)


# ── Gift Cards (Admin) ────────────────────────────────────────────────────────

@router.post(
    "/gift-cards",
    response_model=GiftCardCreatedAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create gift card",
    description="Generates a new gift card with a secure hashed PIN. The plain PIN is returned ONCE in this response.",
)
async def create_gift_card(
    card_in: GiftCardCreateAdmin,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> GiftCardCreatedAdminResponse:
    service = GiftCardService(db)
    return await service.create_gift_card_admin(card_in, admin_user)


@router.get(
    "/gift-cards",
    response_model=GiftCardListResponse,
    summary="List gift cards",
    description="Paginated list of all generated gift cards.",
)
async def list_gift_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> GiftCardListResponse:
    service = GiftCardService(db)
    return await service.list_gift_cards_admin(page=page, page_size=page_size)


@router.patch(
    "/gift-cards/{card_id}",
    response_model=GiftCardResponse,
    summary="Update gift card status",
    description="Enables or disables an existing gift card.",
)
async def update_gift_card(
    card_id: uuid.UUID,
    card_in: GiftCardUpdateAdmin,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> GiftCardResponse:
    service = GiftCardService(db)
    return await service.update_gift_card_admin(card_id, card_in)


# ── Promo Codes (Admin) ───────────────────────────────────────────────────────

@router.post(
    "/promos",
    response_model=PromoCodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create promo code",
)
async def create_promo(
    promo_in: PromoCodeCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> PromoCodeResponse:
    service = PromoService(db)
    return await service.create_promo(promo_in)


@router.get(
    "/promos",
    response_model=PromoCodeListResponse,
    summary="List all promo codes",
)
async def list_promos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> PromoCodeListResponse:
    service = PromoService(db)
    return await service.list_admin_promos(page=page, page_size=page_size)


@router.get(
    "/promos/{promo_id}",
    response_model=PromoCodeResponse,
    summary="Get promo code by ID",
)
async def get_promo(
    promo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> PromoCodeResponse:
    service = PromoService(db)
    return await service.get_promo(promo_id)


@router.patch(
    "/promos/{promo_id}",
    response_model=PromoCodeResponse,
    summary="Update promo code",
)
async def update_promo(
    promo_id: uuid.UUID,
    promo_in: PromoCodeUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> PromoCodeResponse:
    service = PromoService(db)
    return await service.update_promo(promo_id, promo_in)


@router.delete(
    "/promos/{promo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete promo code",
)
async def delete_promo(
    promo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> None:
    service = PromoService(db)
    await service.delete_promo(promo_id)


# ── Delivery Options (Admin) ──────────────────────────────────────────────────

@router.post(
    "/delivery-options",
    response_model=DeliveryOptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create delivery option",
)
async def create_delivery_option(
    option_in: DeliveryOptionCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> DeliveryOptionResponse:
    service = DeliveryOptionService(db)
    return await service.create_option(option_in)


@router.patch(
    "/delivery-options/{option_id}",
    response_model=DeliveryOptionResponse,
    summary="Update delivery option",
)
async def update_delivery_option(
    option_id: uuid.UUID,
    option_in: DeliveryOptionUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> DeliveryOptionResponse:
    service = DeliveryOptionService(db)
    return await service.update_option(option_id, option_in)


@router.delete(
    "/delivery-options/{option_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete delivery option",
)
async def delete_delivery_option(
    option_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> None:
    service = DeliveryOptionService(db)
    await service.delete_option(option_id)


# ── Product Likes (Admin) ─────────────────────────────────────────────────────

@router.get(
    "/products/{product_id}/likes",
    response_model=ProductLikersListResponse,
    summary="Get users who liked a product",
    description="Returns total likes count and a paginated list of users who liked the product.",
)
async def get_product_likes_admin(
    product_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
) -> ProductLikersListResponse:
    service = LikeService(db)
    return await service.get_product_likers(product_id, page=page, page_size=page_size)
