import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.enums import OrderStatus
from app.db.models.user import User
from app.db.session import get_db
from app.services.order_service import OrderService
from app.v1.schemas.order import (
    OrderListResponse,
    OrderResponse,
)

router = APIRouter()


@router.get(
    "/my",
    response_model=OrderListResponse,
    summary="List my orders",
    description="Returns paginated orders placed by the current authenticated user.",
)
async def list_my_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[OrderStatus] = Query(None, description="Optional status filter"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrderListResponse:
    service = OrderService(db)
    return await service.list_my_orders(current_user, page=page, page_size=page_size, status=status)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order details",
    description="Returns order by ID. Accessible by order owner, ADMIN/SUPER_ADMIN, or SELLER whose products are in this order.",
)
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrderResponse:
    service = OrderService(db)
    return await service.get_order_by_id(order_id, current_user)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel order",
    description="Cancels an order if in PENDING, PAID, or PROCESSING status. Restocks variants and refunds payments.",
)
async def cancel_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrderResponse:
    service = OrderService(db)
    return await service.cancel_order(order_id, current_user)
