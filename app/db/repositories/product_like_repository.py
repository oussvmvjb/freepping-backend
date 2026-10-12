import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.product_like import ProductLike
from app.db.models.product import Product


class ProductLikeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: uuid.UUID, product_id: uuid.UUID) -> Optional[ProductLike]:
        stmt = select(ProductLike).where(
            ProductLike.user_id == user_id,
            ProductLike.product_id == product_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user_id: uuid.UUID, product_id: uuid.UUID) -> ProductLike:
        like = ProductLike(user_id=user_id, product_id=product_id)
        self.session.add(like)
        # Increment likes_count in same transaction
        await self.session.execute(
            Product.__table__.update()
            .where(Product.id == product_id)
            .values(likes_count=Product.likes_count + 1)
        )
        await self.session.commit()
        return like

    async def delete(self, like: ProductLike) -> None:
        product_id = like.product_id
        await self.session.delete(like)
        # Decrement likes_count in same transaction (floor at 0)
        await self.session.execute(
            Product.__table__.update()
            .where(Product.id == product_id)
            .where(Product.likes_count > 0)
            .values(likes_count=Product.likes_count - 1)
        )
        await self.session.commit()

    async def list_liked_products(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Product], int]:
        """Returns products liked by a user, paginated."""
        from app.db.models.product_image import ProductImage
        from app.db.models.product_variant import ProductVariant
        from app.db.models.category import Category

        stmt = (
            select(Product)
            .join(ProductLike, ProductLike.product_id == Product.id)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
                selectinload(Product.variants),
            )
            .where(ProductLike.user_id == user_id)
            .where(Product.is_active == True)
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.order_by(ProductLike.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_likers(
        self,
        product_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ProductLike], int]:
        """Returns likes for a product with user info, for admin endpoints."""
        stmt = (
            select(ProductLike)
            .options(selectinload(ProductLike.user))
            .where(ProductLike.product_id == product_id)
            .order_by(ProductLike.created_at.desc())
        )
        count_stmt = select(func.count()).select_from(
            select(ProductLike).where(ProductLike.product_id == product_id).subquery()
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_user_liked_product_ids(
        self,
        user_id: uuid.UUID,
        product_ids: List[uuid.UUID],
    ) -> set:
        """Returns set of product IDs liked by this user among the given list."""
        if not product_ids:
            return set()
        stmt = select(ProductLike.product_id).where(
            ProductLike.user_id == user_id,
            ProductLike.product_id.in_(product_ids),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

