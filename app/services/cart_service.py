from datetime import datetime, timezone
from decimal import Decimal
import uuid
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import DiscountType
from app.core.exceptions import (
    BusinessRuleException,
    ResourceNotFoundException,
)
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.product import Product
from app.db.models.product_variant import ProductVariant
from app.db.models.promo_code import PromoCode
from app.db.models.user import User
from app.db.repositories.cart_repository import CartRepository
from app.db.repositories.product_repository import ProductRepository
from app.db.repositories.product_variant_repository import ProductVariantRepository
from app.db.repositories.promo_code_repository import PromoCodeRepository
from app.v1.schemas.cart import (
    CartItemAdd,
    CartItemResponse,
    CartResponse,
)
from app.v1.schemas.product import ProductResponse
from app.v1.schemas.product_variant import ProductVariantResponse
from app.v1.schemas.promo_code import PromoCodeResponse


class CartService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.cart_repo = CartRepository(session)
        self.product_repo = ProductRepository(session)
        self.variant_repo = ProductVariantRepository(session)
        self.promo_repo = PromoCodeRepository(session)

    @staticmethod
    def _compute_item_price(item: CartItem) -> Decimal:
        if item.variant and item.variant.price is not None:
            return Decimal(str(item.variant.price))
        if item.product and item.product.price is not None:
            return Decimal(str(item.product.price))
        return Decimal("0.00")

    def _calculate_discount(self, promo: Optional[PromoCode], subtotal: Decimal, user_id: uuid.UUID) -> Decimal:
        if not promo or not promo.is_active:
            return Decimal("0.00")

        now = datetime.now(timezone.utc)
        if promo.starts_at and promo.starts_at > now:
            return Decimal("0.00")
        if promo.expires_at and promo.expires_at < now:
            return Decimal("0.00")
        if promo.usage_limit is not None and promo.used_count >= promo.usage_limit:
            return Decimal("0.00")
        if subtotal < Decimal(str(promo.min_order_amount or 0)):
            return Decimal("0.00")

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

        return discount.quantize(Decimal("0.01"))

    def build_cart_response(
        self,
        cart: Cart,
        delivery_cost: Decimal = Decimal("0.00"),
    ) -> CartResponse:
        item_responses = []
        subtotal = Decimal("0.00")

        for it in (cart.items or []):
            unit_price = self._compute_item_price(it)
            line_total = (unit_price * it.quantity).quantize(Decimal("0.01"))
            subtotal += line_total

            img_url = None
            if it.product and it.product.images:
                # Primary or first image
                primary = next((img.image_url for img in it.product.images if img.is_primary), None)
                img_url = primary or it.product.images[0].image_url

            prod_resp = None
            if it.product:
                try:
                    prod_resp = ProductResponse.model_validate(it.product)
                except Exception:
                    pass

            var_resp = None
            if it.variant:
                try:
                    var_resp = ProductVariantResponse.model_validate(it.variant)
                except Exception:
                    pass

            item_responses.append(
                CartItemResponse(
                    id=it.id,
                    product_id=it.product_id,
                    variant_id=it.variant_id,
                    quantity=it.quantity,
                    unit_price=f"{unit_price:.2f}",
                    line_total=f"{line_total:.2f}",
                    product=prod_resp,
                    variant=var_resp,
                    image_url=img_url,
                )
            )


        promo_discount = self._calculate_discount(cart.promo_code, subtotal, cart.user_id)
        gift_wrap_cost = Decimal(str(settings.GIFT_WRAP_COST)).quantize(Decimal("0.01")) if cart.has_gift_wrap else Decimal("0.00")
        total = max(Decimal("0.00"), subtotal - promo_discount) + gift_wrap_cost + delivery_cost

        return CartResponse(
            id=cart.id,
            has_gift_wrap=cart.has_gift_wrap,
            items=item_responses,
            subtotal=f"{subtotal:.2f}",
            promo_discount=f"{promo_discount:.2f}",
            gift_wrap_cost=f"{gift_wrap_cost:.2f}",
            delivery_cost=f"{delivery_cost:.2f}",
            total=f"{total:.2f}",
            applied_promo=PromoCodeResponse.model_validate(cart.promo_code) if cart.promo_code else None,
        )

    async def get_cart(self, user: User) -> CartResponse:
        cart = await self.cart_repo.get_or_create(user.id)
        return self.build_cart_response(cart)

    async def add_item(self, user: User, item_in: CartItemAdd) -> CartResponse:
        product = await self.product_repo.get_by_id(item_in.product_id)
        if not product or not product.is_active:
            raise BusinessRuleException("Product is inactive or does not exist.")

        variant: Optional[ProductVariant] = None
        if item_in.variant_id:
            variant = await self.variant_repo.get_by_id(item_in.variant_id)
            if not variant or not variant.is_active or variant.product_id != product.id:
                raise BusinessRuleException("Selected product variant is invalid or inactive.")

        cart = await self.cart_repo.get_or_create(user.id)
        existing_item = await self.cart_repo.get_item_by_product_variant(cart.id, item_in.product_id, item_in.variant_id)

        target_quantity = item_in.quantity + (existing_item.quantity if existing_item else 0)

        # Validate stock against variant if variant exists
        if variant and variant.stock is not None and target_quantity > variant.stock:
            raise BusinessRuleException(f"Requested quantity ({target_quantity}) exceeds available stock ({variant.stock}).")

        await self.cart_repo.add_item(
            cart_id=cart.id,
            product_id=item_in.product_id,
            variant_id=item_in.variant_id,
            quantity=item_in.quantity,
        )

        cart = await self.cart_repo.get_by_user_id(user.id)
        return self.build_cart_response(cart)

    async def update_item_quantity(self, user: User, item_id: uuid.UUID, quantity: int) -> CartResponse:
        cart = await self.cart_repo.get_or_create(user.id)
        item = await self.cart_repo.get_item(cart.id, item_id)
        if not item:
            raise ResourceNotFoundException("Cart item", item_id)

        # Check stock against variant
        if item.variant and item.variant.stock is not None and quantity > item.variant.stock:
            raise BusinessRuleException(f"Requested quantity ({quantity}) exceeds available stock ({item.variant.stock}).")

        await self.cart_repo.update_item_quantity(item, quantity)
        cart = await self.cart_repo.get_by_user_id(user.id)
        return self.build_cart_response(cart)

    async def delete_item(self, user: User, item_id: uuid.UUID) -> CartResponse:
        cart = await self.cart_repo.get_or_create(user.id)
        item = await self.cart_repo.get_item(cart.id, item_id)
        if not item:
            raise ResourceNotFoundException("Cart item", item_id)

        await self.cart_repo.delete_item(item)
        cart = await self.cart_repo.get_by_user_id(user.id)
        return self.build_cart_response(cart)

    async def clear_cart(self, user: User) -> CartResponse:
        cart = await self.cart_repo.get_or_create(user.id)
        await self.cart_repo.clear(cart)
        cart = await self.cart_repo.get_by_user_id(user.id)
        return self.build_cart_response(cart)

    async def apply_promo(self, user: User, code: str) -> CartResponse:
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

        user_redemptions = await self.promo_repo.get_user_redemption_count(user.id, promo.id)
        if user_redemptions >= promo.per_user_limit:
            raise BusinessRuleException("You have already used this promo code.")

        cart = await self.cart_repo.get_or_create(user.id)
        # Check subtotal against min order amount
        subtotal = sum(self._compute_item_price(it) * it.quantity for it in cart.items)
        if subtotal < Decimal(str(promo.min_order_amount or 0)):
            raise BusinessRuleException(
                f"Minimum order subtotal of ${promo.min_order_amount:.2f} required for promo code '{promo.code}'."
            )

        cart = await self.cart_repo.set_promo(cart, promo.id)
        return self.build_cart_response(cart)

    async def remove_promo(self, user: User) -> CartResponse:
        cart = await self.cart_repo.get_or_create(user.id)
        cart = await self.cart_repo.set_promo(cart, None)
        return self.build_cart_response(cart)

    async def toggle_gift_wrap(self, user: User, enabled: bool) -> CartResponse:
        cart = await self.cart_repo.get_or_create(user.id)
        cart = await self.cart_repo.set_gift_wrap(cart, enabled)
        return self.build_cart_response(cart)
