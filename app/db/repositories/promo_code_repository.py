import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promo_code import PromoCode
from app.db.models.promo_redemption import PromoRedemption


class PromoCodeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, promo_id: uuid.UUID) -> Optional[PromoCode]:
        stmt = select(PromoCode).where(PromoCode.id == promo_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[PromoCode]:
        stmt = select(PromoCode).where(PromoCode.code == code.upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, page: int = 1, page_size: int = 20) -> Tuple[List[PromoCode], int]:
        stmt = select(PromoCode)
        count_stmt = select(func.count()).select_from(PromoCode)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.order_by(PromoCode.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_active(self) -> List[PromoCode]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(PromoCode)
            .where(
                PromoCode.is_active == True,
                (PromoCode.starts_at == None) | (PromoCode.starts_at <= now),
                (PromoCode.expires_at == None) | (PromoCode.expires_at > now),
                (PromoCode.usage_limit == None) | (PromoCode.used_count < PromoCode.usage_limit),
            )
            .order_by(PromoCode.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> PromoCode:
        data["code"] = data["code"].upper()
        promo = PromoCode(**data)
        self.session.add(promo)
        await self.session.commit()
        return promo

    async def update(self, promo: PromoCode, data: dict) -> PromoCode:
        for k, v in data.items():
            setattr(promo, k, v)
        await self.session.commit()
        return promo

    async def delete(self, promo: PromoCode) -> None:
        await self.session.delete(promo)
        await self.session.commit()

    async def get_user_redemption_count(self, user_id: uuid.UUID, promo_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            PromoRedemption.user_id == user_id,
            PromoRedemption.promo_code_id == promo_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create_redemption(
        self,
        promo_id: uuid.UUID,
        user_id: uuid.UUID,
        order_id: Optional[uuid.UUID] = None,
    ) -> PromoRedemption:
        redemption = PromoRedemption(
            promo_code_id=promo_id,
            user_id=user_id,
            order_id=order_id,
        )
        self.session.add(redemption)
        # Increment used_count
        await self.session.execute(
            PromoCode.__table__.update()
            .where(PromoCode.id == promo_id)
            .values(used_count=PromoCode.used_count + 1)
        )
        return redemption
