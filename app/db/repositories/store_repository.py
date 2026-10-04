import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.store import Store
from app.v1.schemas.store import StoreCreate, StoreUpdate


class StoreRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, store_id: uuid.UUID) -> Optional[Store]:
        stmt = select(Store).where(Store.id == store_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_seller_id(self, seller_id: uuid.UUID) -> Optional[Store]:
        stmt = select(Store).where(Store.seller_id == seller_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Store]:
        stmt = select(Store).where(Store.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, seller_id: uuid.UUID, store_in: StoreCreate) -> Store:
        store = Store(
            seller_id=seller_id,
            name=store_in.name,
            slug=store_in.slug,
            description=store_in.description,
            logo_url=store_in.logo_url,
            banner_url=store_in.banner_url,
            is_active=True,
        )
        self.session.add(store)
        await self.session.commit()
        await self.session.refresh(store)
        return store

    async def update(self, store: Store, update_data: StoreUpdate) -> Store:
        data = update_data.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(store, field, value)
        self.session.add(store)
        await self.session.commit()
        await self.session.refresh(store)
        return store

    async def deactivate(self, store: Store) -> Store:
        store.is_active = False
        self.session.add(store)
        await self.session.commit()
        await self.session.refresh(store)
        return store
