import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.db.repositories.delivery_option_repository import DeliveryOptionRepository
from app.services.redis.redis_client import redis_client
from app.v1.schemas.delivery_option import (
    DeliveryOptionCreate,
    DeliveryOptionResponse,
    DeliveryOptionUpdate,
)

DELIVERY_CACHE_KEY = "delivery_options:active"


class DeliveryOptionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DeliveryOptionRepository(session)

    async def list_active(self) -> List[DeliveryOptionResponse]:
        cached = await redis_client.get(DELIVERY_CACHE_KEY)
        if cached is not None:
            return [DeliveryOptionResponse.model_validate(item) for item in cached]

        options = await self.repo.list_active()
        responses = [DeliveryOptionResponse.model_validate(o) for o in options]
        await redis_client.set(
            DELIVERY_CACHE_KEY,
            [r.model_dump() for r in responses],
            ttl=settings.CACHE_TTL_DELIVERY_OPTIONS,
        )
        return responses

    async def list_all_admin(self) -> List[DeliveryOptionResponse]:
        options = await self.repo.list_all()
        return [DeliveryOptionResponse.model_validate(o) for o in options]

    async def get_by_id(self, option_id: uuid.UUID) -> DeliveryOptionResponse:
        option = await self.repo.get_by_id(option_id)
        if not option:
            raise ResourceNotFoundException("DeliveryOption", option_id)
        return DeliveryOptionResponse.model_validate(option)

    async def create_option(self, option_in: DeliveryOptionCreate) -> DeliveryOptionResponse:
        existing = await self.repo.get_by_code(option_in.code)
        if existing:
            raise DuplicateResourceException(f"Delivery option with code '{option_in.code}' already exists.")

        data = option_in.model_dump()
        option = await self.repo.create(data)
        await redis_client.delete(DELIVERY_CACHE_KEY)
        return DeliveryOptionResponse.model_validate(option)

    async def update_option(
        self,
        option_id: uuid.UUID,
        option_in: DeliveryOptionUpdate,
    ) -> DeliveryOptionResponse:
        option = await self.repo.get_by_id(option_id)
        if not option:
            raise ResourceNotFoundException("DeliveryOption", option_id)

        update_data = option_in.model_dump(exclude_unset=True)
        if "code" in update_data and update_data["code"].upper() != option.code:
            existing = await self.repo.get_by_code(update_data["code"])
            if existing:
                raise DuplicateResourceException(f"Delivery option with code '{update_data['code']}' already exists.")
            update_data["code"] = update_data["code"].upper()

        updated = await self.repo.update(option, update_data)
        await redis_client.delete(DELIVERY_CACHE_KEY)
        return DeliveryOptionResponse.model_validate(updated)

    async def delete_option(self, option_id: uuid.UUID) -> None:
        option = await self.repo.get_by_id(option_id)
        if not option:
            raise ResourceNotFoundException("DeliveryOption", option_id)
        await self.repo.delete(option)
        await redis_client.delete(DELIVERY_CACHE_KEY)
