from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
from typing import Dict, List, Optional
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import OrderStatus, PaymentStatus
from app.core.exceptions import ResourceNotFoundException
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.product import Product
from app.db.models.product_variant import ProductVariant
from app.db.models.user import User
from app.db.repositories.order_repository import OrderRepository
from app.db.repositories.product_repository import ProductRepository
from app.db.repositories.product_variant_repository import ProductVariantRepository
from app.services.redis.redis_client import redis_client
from app.v1.schemas.dashboard import (
    AdminDashboardSummary,
    LowStockInventoryResponse,
    LowStockVariantItem,
    RevenueDailyItem,
    SellerDashboardSummary,
    TopProductLikesItem,
    TopProductSalesItem,
)


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_repo = OrderRepository(session)
        self.variant_repo = ProductVariantRepository(session)
        self.product_repo = ProductRepository(session)

    async def get_admin_summary(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> AdminDashboardSummary:
        cache_key = f"dashboard:admin:{date_from}:{date_to}"
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return AdminDashboardSummary.model_validate(cached)

        # 1. Total revenue & orders count & orders by status
        filters = []
        if date_from:
            filters.append(Order.created_at >= date_from)
        if date_to:
            filters.append(Order.created_at <= date_to)
        base_filter = and_(*filters) if filters else True

        rev_stmt = select(func.coalesce(func.sum(Order.total), 0)).where(
            base_filter, Order.payment_status == PaymentStatus.PAID
        )
        total_rev = (await self.session.execute(rev_stmt)).scalar_one()

        count_stmt = select(func.count(Order.id)).where(base_filter)
        orders_count = (await self.session.execute(count_stmt)).scalar_one()

        status_stmt = select(Order.status, func.count(Order.id)).where(base_filter).group_by(Order.status)
        status_results = (await self.session.execute(status_stmt)).all()
        orders_by_status = {str(s.value if hasattr(s, "value") else s): c for s, c in status_results}

        # 2. New users (registered in range or total)
        u_stmt = select(func.count(User.id))
        if date_from:
            u_stmt = u_stmt.where(User.created_at >= date_from)
        if date_to:
            u_stmt = u_stmt.where(User.created_at <= date_to)
        new_users = (await self.session.execute(u_stmt)).scalar_one()

        # 3. Active products
        p_stmt = select(func.count(Product.id)).where(Product.is_active == True)
        active_products = (await self.session.execute(p_stmt)).scalar_one()

        # 4. Low stock count (threshold <= 5)
        ls_stmt = select(func.count(ProductVariant.id)).where(
            ProductVariant.is_active == True, ProductVariant.stock <= 5
        )
        low_stock_count = (await self.session.execute(ls_stmt)).scalar_one()

        # 5. Top products by sales
        top_sales_stmt = (
            select(
                OrderItem.product_id,
                OrderItem.product_name,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.line_total).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.product_id != None,
                base_filter,
                Order.payment_status == PaymentStatus.PAID,
            )
            .group_by(OrderItem.product_id, OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        )
        top_sales_res = (await self.session.execute(top_sales_stmt)).all()
        top_products_by_sales = [
            TopProductSalesItem(
                product_id=row.product_id,
                product_name=row.product_name,
                units_sold=row.units_sold,
                total_revenue=f"{row.revenue:.2f}",
            )
            for row in top_sales_res
        ]

        # 6. Top products by likes
        top_likes_stmt = (
            select(Product.id, Product.name, Product.likes_count)
            .where(Product.is_active == True)
            .order_by(Product.likes_count.desc())
            .limit(5)
        )
        top_likes_res = (await self.session.execute(top_likes_stmt)).all()
        top_products_by_likes = [
            TopProductLikesItem(
                product_id=row.id,
                product_name=row.name,
                likes_count=row.likes_count,
            )
            for row in top_likes_res
        ]

        # 7. Daily revenue series
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        daily_filter = and_(
            Order.payment_status == PaymentStatus.PAID,
            Order.created_at >= (date_from or thirty_days_ago),
        )
        if date_to:
            daily_filter = and_(daily_filter, Order.created_at <= date_to)

        daily_stmt = (
            select(
                func.to_char(Order.created_at, "YYYY-MM-DD").label("date_label"),
                func.sum(Order.total).label("revenue"),
                func.count(Order.id).label("orders_count"),
            )
            .where(daily_filter)
            .group_by("date_label")
            .order_by("date_label")
        )
        daily_res = (await self.session.execute(daily_stmt)).all()
        revenue_daily = [
            RevenueDailyItem(
                date=row.date_label,
                revenue=f"{row.revenue:.2f}",
                orders_count=row.orders_count,
            )
            for row in daily_res
        ]

        summary = AdminDashboardSummary(
            total_revenue=f"{total_rev:.2f}",
            orders_count=orders_count,
            orders_by_status=orders_by_status,
            new_users=new_users,
            active_products=active_products,
            low_stock_count=low_stock_count,
            top_products_by_sales=top_products_by_sales,
            top_products_by_likes=top_products_by_likes,
            revenue_daily=revenue_daily,
        )

        await redis_client.set(
            cache_key,
            summary.model_dump(),
            ttl=settings.CACHE_TTL_DASHBOARD,
        )
        return summary

    async def get_seller_summary(self, seller: User) -> SellerDashboardSummary:
        # Active products for this seller
        p_stmt = select(func.count(Product.id)).where(
            Product.seller_id == seller.id, Product.is_active == True
        )
        active_products = (await self.session.execute(p_stmt)).scalar_one()

        # Low stock variants for this seller's products
        ls_stmt = (
            select(func.count(ProductVariant.id))
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                Product.seller_id == seller.id,
                ProductVariant.is_active == True,
                ProductVariant.stock <= 5,
            )
        )
        low_stock_count = (await self.session.execute(ls_stmt)).scalar_one()

        # Total revenue & orders count from OrderItems
        rev_stmt = (
            select(
                func.coalesce(func.sum(OrderItem.line_total), 0),
                func.count(func.distinct(OrderItem.order_id)),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.seller_id == seller.id,
                Order.payment_status == PaymentStatus.PAID,
            )
        )
        rev_res = (await self.session.execute(rev_stmt)).one()
        total_rev, orders_count = rev_res

        # Status of seller items or orders
        status_stmt = (
            select(Order.status, func.count(func.distinct(Order.id)))
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.seller_id == seller.id)
            .group_by(Order.status)
        )
        status_res = (await self.session.execute(status_stmt)).all()
        orders_by_status = {str(s.value if hasattr(s, "value") else s): c for s, c in status_res}

        # Top products by sales
        top_sales_stmt = (
            select(
                OrderItem.product_id,
                OrderItem.product_name,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.line_total).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.seller_id == seller.id,
                Order.payment_status == PaymentStatus.PAID,
            )
            .group_by(OrderItem.product_id, OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        )
        top_sales_res = (await self.session.execute(top_sales_stmt)).all()
        top_products_by_sales = [
            TopProductSalesItem(
                product_id=row.product_id,
                product_name=row.product_name,
                units_sold=row.units_sold,
                total_revenue=f"{row.revenue:.2f}",
            )
            for row in top_sales_res
        ]

        # Top products by likes for seller
        top_likes_stmt = (
            select(Product.id, Product.name, Product.likes_count)
            .where(Product.seller_id == seller.id, Product.is_active == True)
            .order_by(Product.likes_count.desc())
            .limit(5)
        )
        top_likes_res = (await self.session.execute(top_likes_stmt)).all()
        top_products_by_likes = [
            TopProductLikesItem(
                product_id=row.id,
                product_name=row.name,
                likes_count=row.likes_count,
            )
            for row in top_likes_res
        ]

        # Daily series for seller
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        daily_stmt = (
            select(
                func.to_char(Order.created_at, "YYYY-MM-DD").label("date_label"),
                func.sum(OrderItem.line_total).label("revenue"),
                func.count(func.distinct(Order.id)).label("orders_count"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.seller_id == seller.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= thirty_days_ago,
            )
            .group_by("date_label")
            .order_by("date_label")
        )
        daily_res = (await self.session.execute(daily_stmt)).all()
        revenue_daily = [
            RevenueDailyItem(
                date=row.date_label,
                revenue=f"{row.revenue:.2f}",
                orders_count=row.orders_count,
            )
            for row in daily_res
        ]

        return SellerDashboardSummary(
            total_revenue=f"{total_rev:.2f}",
            orders_count=orders_count,
            orders_by_status=orders_by_status,
            active_products=active_products,
            low_stock_count=low_stock_count,
            top_products_by_sales=top_products_by_sales,
            top_products_by_likes=top_products_by_likes,
            revenue_daily=revenue_daily,
        )

    async def get_low_stock_inventory(self, threshold: int = 5) -> LowStockInventoryResponse:
        variants = await self.order_repo.get_low_stock_variants(threshold=threshold)
        items = [
            LowStockVariantItem(
                variant_id=v.id,
                product_id=v.product_id,
                product_name=v.product.name if v.product else "Product",
                sku=v.sku,
                size=v.size,
                color=v.color,
                stock=v.stock,
            )
            for v in variants
        ]
        return LowStockInventoryResponse(
            items=items,
            threshold=threshold,
            count=len(items),
        )

    async def update_variant_stock(self, variant_id: uuid.UUID, new_stock: int) -> LowStockVariantItem:
        variant = await self.variant_repo.get_by_id(variant_id)
        if not variant:
            raise ResourceNotFoundException("ProductVariant", variant_id)

        variant.stock = new_stock
        await self.session.commit()
        await redis_client.invalidate_product_caches(str(variant.product_id))

        # Re-fetch with product
        variant = await self.variant_repo.get_by_id(variant_id)
        return LowStockVariantItem(
            variant_id=variant.id,
            product_id=variant.product_id,
            product_name=variant.product.name if variant.product else "Product",
            sku=variant.sku,
            size=variant.size,
            color=variant.color,
            stock=variant.stock,
        )
