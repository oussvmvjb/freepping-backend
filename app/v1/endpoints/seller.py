import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_seller
from app.core.exceptions import AuthorizationException
from app.db.models.user import User
from app.db.session import get_db
from app.services.dashboard_service import DashboardService
from app.services.like_service import LikeService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.v1.schemas.dashboard import SellerDashboardSummary
from app.v1.schemas.order import (
    OrderItemResponse,
    OrderListResponse,
    SellerItemStatusUpdateRequest,
)
from app.v1.schemas.product import ProductLikeToggleResponse

router = APIRouter()


@router.get(
    "/dashboard/summary",
    response_model=SellerDashboardSummary,
    summary="Seller dashboard analytics summary",
    description="Returns aggregate sales, orders, and product stats scoped strictly to the authenticated seller's catalog.",
)
async def get_seller_dashboard(
    db: AsyncSession = Depends(get_db),
    seller_user: User = Depends(require_seller),
) -> SellerDashboardSummary:
    service = DashboardService(db)
    return await service.get_seller_summary(seller_user)


@router.get(
    "/orders",
    response_model=OrderListResponse,
    summary="List orders containing seller items",
    description="Returns orders containing this seller's products, showing only their line items.",
)
async def list_seller_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    seller_user: User = Depends(require_seller),
) -> OrderListResponse:
    service = OrderService(db)
    return await service.list_seller_orders(seller_user, page=page, page_size=page_size)


@router.patch(
    "/orders/{order_id}/items/{item_id}/status",
    response_model=OrderItemResponse,
    summary="Update line item fulfillment status",
    description="Updates fulfillment status for an item owned by the authenticated seller.",
)
async def update_item_status(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    status_in: SellerItemStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    seller_user: User = Depends(require_seller),
) -> OrderItemResponse:
    service = OrderService(db)
    return await service.update_seller_item_status(order_id, item_id, status_in, seller_user)


@router.get(
    "/products/{product_id}/likes",
    response_model=ProductLikeToggleResponse,
    summary="Get product likes count (seller)",
    description="Returns total likes count for a product owned by this seller.",
)
async def get_seller_product_likes(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    seller_user: User = Depends(require_seller),
) -> ProductLikeToggleResponse:
    prod_service = ProductService(db)
    product = await prod_service.repository.get_by_id(product_id)
    if not product or product.seller_id != seller_user.id:
        raise AuthorizationException("You do not have permission to view stats for this product.")
    return ProductLikeToggleResponse(liked=False, likes_count=product.likes_count)
