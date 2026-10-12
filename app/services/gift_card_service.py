from datetime import datetime, timezone
import math
import random
import string
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
)
from app.core.security import hash_pin, verify_pin
from app.db.models.user import User
from app.db.repositories.gift_card_repository import GiftCardRepository
from app.v1.schemas.gift_card import (
    GiftCardCheckRequest,
    GiftCardCheckResponse,
    GiftCardCreateAdmin,
    GiftCardCreatedAdminResponse,
    GiftCardListResponse,
    GiftCardResponse,
    GiftCardUpdateAdmin,
)


class GiftCardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = GiftCardRepository(session)

    @staticmethod
    def generate_code() -> str:
        part1 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        part2 = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"FRP-GC-{part1}-{part2}"

    @staticmethod
    def generate_pin() -> str:
        return "".join(random.choices(string.digits, k=4))

    async def check_balance(self, check_in: GiftCardCheckRequest) -> GiftCardCheckResponse:
        card = await self.repo.get_by_code(check_in.number)
        if not card:
            raise BusinessRuleException("Gift card not found or invalid code.")

        if not verify_pin(check_in.pin, card.pin_hash):
            raise BusinessRuleException("Invalid gift card PIN.")

        now = datetime.now(timezone.utc)
        if not card.is_active:
            raise BusinessRuleException("This gift card has been deactivated.")
        if card.expires_at and card.expires_at < now:
            raise BusinessRuleException("This gift card has expired.")

        return GiftCardCheckResponse(
            code=card.code,
            balance=f"{card.balance:.2f}",
            currency=card.currency,
            is_active=card.is_active,
            expires_at=card.expires_at,
        )

    async def create_gift_card_admin(
        self,
        card_in: GiftCardCreateAdmin,
        admin_user: User,
    ) -> GiftCardCreatedAdminResponse:
        code = self.generate_code()
        # Ensure code uniqueness
        while await self.repo.get_by_code(code):
            code = self.generate_code()

        plain_pin = self.generate_pin()
        hashed = hash_pin(plain_pin)

        card = await self.repo.create({
            "code": code,
            "pin_hash": hashed,
            "initial_balance": card_in.initial_balance,
            "balance": card_in.initial_balance,
            "currency": card_in.currency.upper(),
            "is_active": True,
            "expires_at": card_in.expires_at,
            "created_by": admin_user.id,
        })

        return GiftCardCreatedAdminResponse(
            id=card.id,
            code=card.code,
            pin=plain_pin,
            initial_balance=f"{card.initial_balance:.2f}",
            balance=f"{card.balance:.2f}",
            currency=card.currency,
            is_active=card.is_active,
            expires_at=card.expires_at,
            created_at=card.created_at,
        )

    async def list_gift_cards_admin(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> GiftCardListResponse:
        items, total = await self.repo.list_all(page=page, page_size=page_size)
        pages = math.ceil(total / page_size) if total > 0 else 0
        return GiftCardListResponse(
            items=[
                GiftCardResponse(
                    id=c.id,
                    code=c.code,
                    initial_balance=f"{c.initial_balance:.2f}",
                    balance=f"{c.balance:.2f}",
                    currency=c.currency,
                    is_active=c.is_active,
                    expires_at=c.expires_at,
                    created_at=c.created_at,
                )
                for c in items
            ],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def update_gift_card_admin(
        self,
        card_id: uuid.UUID,
        card_in: GiftCardUpdateAdmin,
    ) -> GiftCardResponse:
        card = await self.repo.get_by_id(card_id)
        if not card:
            raise ResourceNotFoundException("Gift card", card_id)

        update_data = card_in.model_dump(exclude_unset=True)
        updated = await self.repo.update(card, update_data)
        return GiftCardResponse(
            id=updated.id,
            code=updated.code,
            initial_balance=f"{updated.initial_balance:.2f}",
            balance=f"{updated.balance:.2f}",
            currency=updated.currency,
            is_active=updated.is_active,
            expires_at=updated.expires_at,
            created_at=updated.created_at,
        )
