import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import OrderStatus, PaymentStatus
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.payment import Payment


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        stmt = (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.items).selectinload(OrderItem.variant),
                selectinload(Order.status_history),
                selectinload(Order.payments),
                selectinload(Order.promo_code),
                selectinload(Order.delivery_option),
            )
            .where(Order.id == order_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order_number(self, order_number: str) -> Optional[Order]:
        stmt = select(Order).where(Order.order_number == order_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Optional[Order]:
        stmt = select(Order).where(Order.idempotency_key == key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[OrderStatus] = None,
    ) -> Tuple[List[Order], int]:
        stmt = (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.delivery_option),
            )
            .where(Order.user_id == user_id)
        )
        if status:
            stmt = stmt.where(Order.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_admin(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        payment_status: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Order], int]:
        stmt = (
            select(Order)
            .options(
                selectinload(Order.items),
                selectinload(Order.delivery_option),
            )
        )
        if status:
            stmt = stmt.where(Order.status == status)
        if payment_status:
            stmt = stmt.where(Order.payment_status == payment_status)
        if user_id:
            stmt = stmt.where(Order.user_id == user_id)
        if date_from:
            stmt = stmt.where(Order.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Order.created_at <= date_to)
        if search:
            stmt = stmt.join(Order.user, isouter=True).where(
                or_(
                    Order.order_number.ilike(f"%{search}%"),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_seller_orders(
        self,
        seller_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Order], int]:
        """Returns orders that contain items from this seller."""
        stmt = (
            select(Order)
            .join(Order.items)
            .options(
                selectinload(Order.items),
                selectinload(Order.delivery_option),
            )
            .where(OrderItem.seller_id == seller_id)
            .distinct()
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, order_data: dict, items_data: List[dict]) -> Order:
        order = Order(**order_data)
        self.session.add(order)
        await self.session.flush()  # get order.id without committing
        for item_data in items_data:
            item = OrderItem(order_id=order.id, **item_data)
            self.session.add(item)
        return order

    async def add_status_history(
        self,
        order_id: uuid.UUID,
        from_status: Optional[str],
        to_status: str,
        changed_by: Optional[uuid.UUID] = None,
        note: Optional[str] = None,
    ) -> OrderStatusHistory:
        history = OrderStatusHistory(
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            note=note,
        )
        self.session.add(history)
        return history

    async def add_payment(self, payment_data: dict) -> Payment:
        payment = Payment(**payment_data)
        self.session.add(payment)
        return payment

    async def update_status(
        self,
        order: Order,
        new_status: OrderStatus,
        changed_by: Optional[uuid.UUID] = None,
        note: Optional[str] = None,
        tracking_number: Optional[str] = None,
    ) -> Order:
        old_status = order.status
        order.status = new_status
        now = datetime.now(timezone.utc)
        if new_status == OrderStatus.PAID:
            order.paid_at = now
            order.payment_status = PaymentStatus.PAID
        elif new_status == OrderStatus.SHIPPED:
            order.shipped_at = now
            if tracking_number:
                order.tracking_number = tracking_number
        elif new_status == OrderStatus.DELIVERED:
            order.delivered_at = now
        elif new_status == OrderStatus.CANCELLED:
            order.cancelled_at = now
        elif new_status == OrderStatus.REFUNDED:
            order.payment_status = PaymentStatus.REFUNDED

        await self.add_status_history(
            order.id, old_status.value if old_status else None, new_status.value, changed_by, note
        )
        await self.session.commit()
        return await self.get_by_id(order.id)

    async def get_dashboard_summary(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        """Aggregated dashboard stats for admins."""
        filters = []
        if date_from:
            filters.append(Order.created_at >= date_from)
        if date_to:
            filters.append(Order.created_at <= date_to)

        base_filter = and_(*filters) if filters else True

        # Total revenue (PAID orders)
        rev_stmt = select(func.coalesce(func.sum(Order.total), 0)).where(
            base_filter, Order.payment_status == PaymentStatus.PAID
        )
        total_revenue = (await self.session.execute(rev_stmt)).scalar_one()

        # Orders count
        count_stmt = select(func.count(Order.id)).where(base_filter)
        orders_count = (await self.session.execute(count_stmt)).scalar_one()

        # Orders by status
        status_stmt = select(Order.status, func.count(Order.id)).where(base_filter).group_by(Order.status)
        status_results = (await self.session.execute(status_stmt)).all()
        orders_by_status = {str(s): c for s, c in status_results}

        return {
            "total_revenue": str(total_revenue),
            "orders_count": orders_count,
            "orders_by_status": orders_by_status,
        }

    async def get_low_stock_variants(self, threshold: int = 5) -> list:
        from app.db.models.product_variant import ProductVariant
        from app.db.models.product import Product
        stmt = (
            select(ProductVariant)
            .options(selectinload(ProductVariant.product))
            .where(
                ProductVariant.stock <= threshold,
                ProductVariant.is_active == True,
            )
            .order_by(ProductVariant.stock)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_top_products_by_sales(self, limit: int = 10, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list:
        from app.db.models.product import Product
        filters = [OrderItem.product_id != None]
        if date_from:
            filters.append(Order.created_at >= date_from)
        if date_to:
            filters.append(Order.created_at <= date_to)
        stmt = (
            select(OrderItem.product_id, func.sum(OrderItem.quantity).label("total_sold"))
            .join(Order, Order.id == OrderItem.order_id)
            .where(*filters)
            .group_by(OrderItem.product_id)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def get_revenue_daily(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list:
        filters = [Order.payment_status == PaymentStatus.PAID]
        if date_from:
            filters.append(Order.created_at >= date_from)
        if date_to:
            filters.append(Order.created_at <= date_to)
        stmt = (
            select(
                func.date_trunc("day", Order.created_at).label("day"),
                func.sum(Order.total).label("revenue"),
            )
            .where(*filters)
            .group_by(func.date_trunc("day", Order.created_at))
            .order_by(func.date_trunc("day", Order.created_at))
        )
        result = await self.session.execute(stmt)
        return result.all()
