import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.address import Address


class AddressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: uuid.UUID) -> List[Address]:
        stmt = (
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.is_default.desc(), Address.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, address_id: uuid.UUID) -> Optional[Address]:
        stmt = select(Address).where(Address.id == address_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_user(self, address_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Address]:
        stmt = select(Address).where(Address.id == address_id, Address.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user_id: uuid.UUID, data: dict) -> Address:
        # If this is the first address, make it default
        existing = await self.list_by_user(user_id)
        is_default = data.pop("is_default", len(existing) == 0)
        if is_default:
            await self._clear_default(user_id)
        address = Address(user_id=user_id, is_default=is_default, **data)
        self.session.add(address)
        await self.session.commit()
        return address

    async def update(self, address: Address, data: dict) -> Address:
        if data.get("is_default"):
            await self._clear_default(address.user_id)
        for k, v in data.items():
            setattr(address, k, v)
        await self.session.commit()
        return address

    async def delete(self, address: Address) -> None:
        user_id = address.user_id
        was_default = address.is_default
        await self.session.delete(address)
        await self.session.commit()
        # If deleted was default, promote next address
        if was_default:
            remaining = await self.list_by_user(user_id)
            if remaining:
                remaining[0].is_default = True
                await self.session.commit()

    async def set_default(self, address: Address) -> Address:
        await self._clear_default(address.user_id)
        address.is_default = True
        await self.session.commit()
        return address

    async def _clear_default(self, user_id: uuid.UUID) -> None:
        stmt = (
            Address.__table__.update()
            .where(Address.user_id == user_id)
            .values(is_default=False)
        )
        await self.session.execute(stmt)
