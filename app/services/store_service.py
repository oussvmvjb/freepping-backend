import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationException,
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.db.models.store import Store
from app.db.models.user import User
from app.db.repositories.store_repository import StoreRepository
from app.v1.schemas.store import StoreCreate, StoreUpdate


class StoreService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.store_repo = StoreRepository(session)

    async def get_by_slug(self, slug: str) -> Store:
        store = await self.store_repo.get_by_slug(slug)
        if not store or not store.is_active:
            raise ResourceNotFoundException("Store", slug)
        return store

    async def get_my_store(self, current_user: User) -> Store:
        store = await self.store_repo.get_by_seller_id(current_user.id)
        if not store:
            raise ResourceNotFoundException("Store for current seller", current_user.id)
        return store

    async def create_store(self, current_user: User, store_in: StoreCreate) -> Store:
        # Check if seller already has a store (1 SELLER = 1 STORE)
        existing = await self.store_repo.get_by_seller_id(current_user.id)
        if existing:
            raise DuplicateResourceException("You already have a registered store. Only one store per seller is allowed.")

        # Check unique slug
        slug_existing = await self.store_repo.get_by_slug(store_in.slug)
        if slug_existing:
            raise DuplicateResourceException(f"Store with slug '{store_in.slug}' already exists.")

        # Always derive seller_id from authenticated user
        return await self.store_repo.create(seller_id=current_user.id, store_in=store_in)

    async def update_my_store(self, current_user: User, store_in: StoreUpdate) -> Store:
        store = await self.get_my_store(current_user)

        if store_in.slug and store_in.slug != store.slug:
            slug_existing = await self.store_repo.get_by_slug(store_in.slug)
            if slug_existing and slug_existing.id != store.id:
                raise DuplicateResourceException(f"Store with slug '{store_in.slug}' already exists.")

        return await self.store_repo.update(store, store_in)

    async def deactivate_my_store(self, current_user: User) -> Store:
        store = await self.get_my_store(current_user)
        return await self.store_repo.deactivate(store)
