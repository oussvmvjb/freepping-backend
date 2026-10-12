from datetime import datetime, timezone
from decimal import Decimal
import math
import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DiscountType
from app.core.exceptions import (
    BusinessRuleException,
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.db.models.cart_item import CartItem
from app.db.models.promo_code import PromoCode
from app.db.models.user import User
from app.db.repositories.cart_repository import CartRepository
from app.db.repositories.promo_code_repository import PromoCodeRepository
from app.v1.schemas.promo_code import (
    PromoCodeCreate,
    PromoCodeListResponse,
    PromoCodeResponse,
    PromoCodeUpdate,
    PromoValidateResponse,
)


class PromoService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.promo_repo = PromoCodeRepository(session)
        self.cart_repo = CartRepository(session)

    async def validate_for_cart(self, user: User, code: str) -> PromoValidateResponse:
        promo = await self.promo_repo.get_by_code(code)
        if not promo:
            raise BusinessRuleException(f"Promo code '{code.upper()}' is invalid.")

        now = datetime.now(timezone.utc)
        if not promo.is_active:
            raise BusinessRuleException("Promo code is inactive.")
        if promo.starts_at and promo.starts_at > now:
            raise BusinessRuleException("Promo code offer has not started yet.")
        if promo.expires_at and promo.expires_at < now:
            raise BusinessRuleException("Promo code has expired.")
        if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
            raise BusinessRuleException("Promo code usage limit has been reached.")

        user_count = await self.promo_repo.get_user_redemption_count(user.id, promo.id)
        if user_count >= promo.per_user_limit:
            raise BusinessRuleException("You have already used this promo code.")

        cart = await self.cart_repo.get_or_create(user.id)
        subtotal = Decimal("0.00")
        for it in (cart.items or []):
            if it.variant and it.variant.price is not None:
                p = Decimal(str(it.variant.price))
            elif it.product and it.product.price is not None:
                p = Decimal(str(it.product.price))
            else:
                p = Decimal("0.00")
            subtotal += (p * it.quantity)

        if subtotal < Decimal(str(promo.min_order_amount or 0)):
            raise BusinessRuleException(
                f"Minimum order amount of ${promo.min_order_amount:.2f} not met. Current cart subtotal: ${subtotal:.2f}."
            )

        # Compute discount
        discount = Decimal("0.00")
        if promo.discount_type == DiscountType.PERCENT:
            rate = Decimal(str(promo.discount_value)) / Decimal("100")
            discount = subtotal * rate
            if promo.max_discount_amount is not None:
                max_d = Decimal(str(promo.max_discount_amount))
                if discount > max_d:
                    discount = max_d
        elif promo.discount_type == DiscountType.FIXED:
            discount = Decimal(str(promo.discount_value))
            if discount > subtotal:
                discount = subtotal

        discount = discount.quantize(Decimal("0.01"))
        new_subtotal = max(Decimal("0.00"), subtotal - discount).quantize(Decimal("0.01"))

        return PromoValidateResponse(
            valid=True,
            code=promo.code,
            discount_type=promo.discount_type.value,
            discount_value=str(promo.discount_value),
            discount_amount=f"{discount:.2f}",
            subtotal=f"{subtotal:.2f}",
            new_subtotal=f"{new_subtotal:.2f}",
            message=f"Promo code '{promo.code}' applied successfully!",
        )

    async def list_active_promos(self) -> List[PromoCodeResponse]:
        promos = await self.promo_repo.list_active()
        return [PromoCodeResponse.model_validate(p) for p in promos]

    async def list_admin_promos(self, page: int = 1, page_size: int = 20) -> PromoCodeListResponse:
        items, total = await self.promo_repo.list_all(page=page, page_size=page_size)
        pages = math.ceil(total / page_size) if total > 0 else 0
        return PromoCodeListResponse(
            items=[PromoCodeResponse.model_validate(p) for p in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def get_promo(self, promo_id: uuid.UUID) -> PromoCodeResponse:
        promo = await self.promo_repo.get_by_id(promo_id)
        if not promo:
            raise ResourceNotFoundException("Promo code", promo_id)
        return PromoCodeResponse.model_validate(promo)

    async def create_promo(self, promo_in: PromoCodeCreate) -> PromoCodeResponse:
        existing = await self.promo_repo.get_by_code(promo_in.code)
        if existing:
            raise DuplicateResourceException(f"Promo code '{promo_in.code.upper()}' already exists.")

        data = promo_in.model_dump()
        promo = await self.promo_repo.create(data)
        return PromoCodeResponse.model_validate(promo)

    async def update_promo(self, promo_id: uuid.UUID, promo_in: PromoCodeUpdate) -> PromoCodeResponse:
        promo = await self.promo_repo.get_by_id(promo_id)
        if not promo:
            raise ResourceNotFoundException("Promo code", promo_id)

        update_data = promo_in.model_dump(exclude_unset=True)
        if "code" in update_data and update_data["code"].upper() != promo.code:
            existing = await self.promo_repo.get_by_code(update_data["code"])
            if existing:
                raise DuplicateResourceException(f"Promo code '{update_data['code'].upper()}' already exists.")
            update_data["code"] = update_data["code"].upper()

        updated = await self.promo_repo.update(promo, update_data)
        return PromoCodeResponse.model_validate(updated)

    async def delete_promo(self, promo_id: uuid.UUID) -> None:
        promo = await self.promo_repo.get_by_id(promo_id)
        if not promo:
            raise ResourceNotFoundException("Promo code", promo_id)
        await self.promo_repo.delete(promo)
