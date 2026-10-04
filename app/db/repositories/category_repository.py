import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category import Category
from app.v1.schemas.category import CategoryCreate, CategoryUpdate


class CategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, category_id: uuid.UUID) -> Optional[Category]:
        stmt = select(Category).where(Category.id == category_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Category]:
        stmt = select(Category).where(Category.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, is_active_only: bool = True) -> List[Category]:
        stmt = select(Category)
        if is_active_only:
            stmt = stmt.where(Category.is_active == True)
        stmt = stmt.order_by(Category.name.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, category_in: CategoryCreate) -> Category:
        category = Category(
            name=category_in.name,
            slug=category_in.slug,
            description=category_in.description,
            image_url=category_in.image_url,
            is_active=category_in.is_active,
        )
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def update(self, category: Category, category_in: CategoryUpdate) -> Category:
        update_data = category_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(category, field, value)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def delete(self, category: Category) -> None:
        await self.session.delete(category)
        await self.session.commit()
