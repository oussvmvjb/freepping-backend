import math
import uuid
from typing import Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories.product_like_repository import ProductLikeRepository
from app.db.repositories.product_repository import ProductRepository
from app.services.redis.redis_client import redis_client
from app.v1.schemas.product import (
    ProductLikeToggleResponse,
    ProductLikerItemResponse,
    ProductLikersListResponse,
    ProductListResponse,
    ProductResponse,
)


class LikeService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.like_repo = ProductLikeRepository(session)
        self.product_repo = ProductRepository(session)

    @staticmethod
    def enrich_product(product: Product, is_liked: bool = False) -> ProductResponse:
        in_stock = any(v.is_active and (v.stock or 0) > 0 for v in (product.variants or []))
        discount_percent = None
        if product.compare_price and product.price and product.compare_price > product.price:
            discount_percent = int(
                round(((product.compare_price - product.price) / product.compare_price) * 100)
            )

        resp = ProductResponse.model_validate(product)
        resp.is_liked = is_liked
        resp.in_stock = in_stock
        resp.discount_percent = discount_percent
        return resp

    async def like_product(self, product_id: uuid.UUID, user: User) -> ProductLikeToggleResponse:
        product = await self.product_repo.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        existing = await self.like_repo.get(user.id, product_id)
        if existing:
            # Idempotent - already liked
            return ProductLikeToggleResponse(liked=True, likes_count=product.likes_count)

        await self.like_repo.create(user.id, product_id)
        # Reload product to get fresh likes_count
        product = await self.product_repo.get_by_id(product_id)
        likes_count = product.likes_count if product else 1

        await redis_client.invalidate_product_caches(str(product_id))
        return ProductLikeToggleResponse(liked=True, likes_count=likes_count)

    async def unlike_product(self, product_id: uuid.UUID, user: User) -> ProductLikeToggleResponse:
        product = await self.product_repo.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        existing = await self.like_repo.get(user.id, product_id)
        if not existing:
            # Idempotent - already not liked
            return ProductLikeToggleResponse(liked=False, likes_count=product.likes_count)

        await self.like_repo.delete(existing)
        # Reload product to get fresh likes_count
        product = await self.product_repo.get_by_id(product_id)
        likes_count = product.likes_count if product else 0

        await redis_client.invalidate_product_caches(str(product_id))
        return ProductLikeToggleResponse(liked=False, likes_count=likes_count)

    async def list_user_favorites(
        self,
        user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductListResponse:
        items, total = await self.like_repo.list_liked_products(user.id, page=page, page_size=page_size)
        pages = math.ceil(total / page_size) if total > 0 else 0

        enriched = [self.enrich_product(p, is_liked=True) for p in items]
        return ProductListResponse(
            items=enriched,
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def get_product_likers(
        self,
        product_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductLikersListResponse:
        product = await self.product_repo.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        likes, total = await self.like_repo.get_likers(product_id, page=page, page_size=page_size)
        pages = math.ceil(total / page_size) if total > 0 else 0

        items = []
        for lk in likes:
            items.append(
                ProductLikerItemResponse(
                    id=lk.id,
                    user_id=lk.user_id,
                    email=lk.user.email if lk.user else None,
                    full_name=f"{lk.user.first_name or ''} {lk.user.last_name or ''}".strip() if lk.user else None,
                    created_at=lk.created_at,
                )
            )

        return ProductLikersListResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
            likes_count=product.likes_count,
        )
