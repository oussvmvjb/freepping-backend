import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.delivery_option import DeliveryOption


class DeliveryOptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self) -> List[DeliveryOption]:
        stmt = (
            select(DeliveryOption)
            .where(DeliveryOption.is_active == True)
            .order_by(DeliveryOption.sort_order, DeliveryOption.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> List[DeliveryOption]:
        stmt = select(DeliveryOption).order_by(DeliveryOption.sort_order, DeliveryOption.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, option_id: uuid.UUID) -> Optional[DeliveryOption]:
        stmt = select(DeliveryOption).where(DeliveryOption.id == option_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[DeliveryOption]:
        stmt = select(DeliveryOption).where(DeliveryOption.code == code.upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> DeliveryOption:
        option = DeliveryOption(**data)
        self.session.add(option)
        await self.session.commit()
        return option

    async def update(self, option: DeliveryOption, data: dict) -> DeliveryOption:
        for k, v in data.items():
            setattr(option, k, v)
        await self.session.commit()
        return option

    async def delete(self, option: DeliveryOption) -> None:
        await self.session.delete(option)
        await self.session.commit()
