import uuid
from typing import List, Optional, Tuple
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.gift_card import GiftCard
from app.db.models.gift_card_transaction import GiftCardTransaction


class GiftCardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str) -> Optional[GiftCard]:
        stmt = select(GiftCard).where(GiftCard.code == code.upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, card_id: uuid.UUID) -> Optional[GiftCard]:
        stmt = select(GiftCard).where(GiftCard.id == card_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, page: int = 1, page_size: int = 20) -> Tuple[List[GiftCard], int]:
        count_stmt = select(func.count()).select_from(GiftCard)
        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = select(GiftCard).order_by(GiftCard.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, data: dict) -> GiftCard:
        card = GiftCard(**data)
        self.session.add(card)
        await self.session.commit()
        return card

    async def update(self, card: GiftCard, data: dict) -> GiftCard:
        for k, v in data.items():
            setattr(card, k, v)
        await self.session.commit()
        return card

    async def deduct_balance(
        self,
        card: GiftCard,
        amount: Decimal,
        order_id: Optional[uuid.UUID] = None,
    ) -> GiftCardTransaction:
        """Deducts balance and records a transaction. Returns the transaction."""
        card.balance -= amount
        txn = GiftCardTransaction(
            gift_card_id=card.id,
            order_id=order_id,
            amount=-amount,  # negative = redemption
            balance_after=card.balance,
        )
        self.session.add(txn)
        return txn

    async def refund_balance(
        self,
        card: GiftCard,
        amount: Decimal,
        order_id: Optional[uuid.UUID] = None,
    ) -> GiftCardTransaction:
        """Refunds balance back to the gift card."""
        card.balance += amount
        txn = GiftCardTransaction(
            gift_card_id=card.id,
            order_id=order_id,
            amount=amount,  # positive = refund
            balance_after=card.balance,
        )
        self.session.add(txn)
        return txn
