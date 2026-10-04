import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException
from app.db.models.category import Category
from app.db.repositories.category_repository import CategoryRepository
from app.services.redis.redis_client import redis_client
from app.v1.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate


class CategoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = CategoryRepository(session)

    async def list_categories(self, is_active_only: bool = True) -> List[CategoryResponse]:
        cache_key = "categories:list"
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return [CategoryResponse.model_validate(c) for c in cached]

        categories = await self.repository.get_all(is_active_only=is_active_only)
        result = [CategoryResponse.model_validate(c) for c in categories]

        # Cache in background
        await redis_client.set(
            cache_key,
            [c.model_dump() for c in result],
            ttl=settings.CACHE_TTL_CATEGORIES
        )
        return result

    async def get_category(self, category_id: uuid.UUID) -> CategoryResponse:
        cache_key = f"categories:{category_id}"
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return CategoryResponse.model_validate(cached)

        category = await self.repository.get_by_id(category_id)
        if not category:
            raise ResourceNotFoundException("Category", category_id)

        response = CategoryResponse.model_validate(category)
        await redis_client.set(cache_key, response.model_dump(), ttl=settings.CACHE_TTL_CATEGORIES)
        return response

    async def create_category(self, category_in: CategoryCreate) -> CategoryResponse:
        existing = await self.repository.get_by_slug(category_in.slug)
        if existing:
            raise DuplicateResourceException(f"Category with slug '{category_in.slug}' already exists.")

        category = await self.repository.create(category_in)
        await redis_client.invalidate_category_caches()
        return CategoryResponse.model_validate(category)

    async def update_category(self, category_id: uuid.UUID, category_in: CategoryUpdate) -> CategoryResponse:
        category = await self.repository.get_by_id(category_id)
        if not category:
            raise ResourceNotFoundException("Category", category_id)

        if category_in.slug and category_in.slug != category.slug:
            existing = await self.repository.get_by_slug(category_in.slug)
            if existing:
                raise DuplicateResourceException(f"Category with slug '{category_in.slug}' already exists.")

        updated = await self.repository.update(category, category_in)
        await redis_client.invalidate_category_caches(str(category_id))
        return CategoryResponse.model_validate(updated)

    async def delete_category(self, category_id: uuid.UUID) -> None:
        category = await self.repository.get_by_id(category_id)
        if not category:
            raise ResourceNotFoundException("Category", category_id)

        await self.repository.delete(category)
        await redis_client.invalidate_category_caches(str(category_id))
