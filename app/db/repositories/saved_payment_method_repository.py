import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.saved_payment_method import SavedPaymentMethod


class SavedPaymentMethodRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: uuid.UUID) -> List[SavedPaymentMethod]:
        stmt = (
            select(SavedPaymentMethod)
            .where(SavedPaymentMethod.user_id == user_id)
            .order_by(SavedPaymentMethod.is_default.desc(), SavedPaymentMethod.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, method_id: uuid.UUID) -> Optional[SavedPaymentMethod]:
        stmt = select(SavedPaymentMethod).where(SavedPaymentMethod.id == method_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self,
        method_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[SavedPaymentMethod]:
        stmt = select(SavedPaymentMethod).where(
            SavedPaymentMethod.id == method_id,
            SavedPaymentMethod.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> SavedPaymentMethod:
        method = SavedPaymentMethod(**data)
        self.session.add(method)
        await self.session.commit()
        return method

    async def delete(self, method: SavedPaymentMethod) -> None:
        await self.session.delete(method)
        await self.session.commit()
