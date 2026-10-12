import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.product import Product
from app.db.models.product_variant import ProductVariant


class CartRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[Cart]:
        stmt = (
            select(Cart)
            .options(
                selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.images),
                selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.category),
                selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.variants),
                selectinload(Cart.items).selectinload(CartItem.variant),
                selectinload(Cart.promo_code),
            )
            .where(Cart.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: uuid.UUID) -> Cart:
        cart = await self.get_by_user_id(user_id)
        if not cart:
            cart = Cart(user_id=user_id)
            self.session.add(cart)
            await self.session.commit()
            cart = await self.get_by_user_id(user_id)
        return cart

    async def get_item(self, cart_id: uuid.UUID, item_id: uuid.UUID) -> Optional[CartItem]:
        stmt = (
            select(CartItem)
            .options(
                selectinload(CartItem.product).selectinload(Product.images),
                selectinload(CartItem.variant),
            )
            .where(CartItem.id == item_id, CartItem.cart_id == cart_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_item_by_product_variant(
        self,
        cart_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: Optional[uuid.UUID],
    ) -> Optional[CartItem]:
        stmt = select(CartItem).where(
            CartItem.cart_id == cart_id,
            CartItem.product_id == product_id,
            CartItem.variant_id == variant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_item(
        self,
        cart_id: uuid.UUID,
        product_id: uuid.UUID,
        variant_id: Optional[uuid.UUID],
        quantity: int,
    ) -> CartItem:
        existing = await self.get_item_by_product_variant(cart_id, product_id, variant_id)
        if existing:
            existing.quantity += quantity
            await self.session.commit()
            return existing
        item = CartItem(
            cart_id=cart_id,
            product_id=product_id,
            variant_id=variant_id,
            quantity=quantity,
        )
        self.session.add(item)
        await self.session.commit()
        return item

    async def update_item_quantity(self, item: CartItem, quantity: int) -> CartItem:
        item.quantity = quantity
        await self.session.commit()
        return item

    async def delete_item(self, item: CartItem) -> None:
        await self.session.delete(item)
        await self.session.commit()

    async def clear(self, cart: Cart) -> None:
        for item in cart.items:
            await self.session.delete(item)
        await self.session.commit()

    async def set_promo(self, cart: Cart, promo_code_id: Optional[uuid.UUID]) -> Cart:
        cart.promo_code_id = promo_code_id
        await self.session.commit()
        return await self.get_by_user_id(cart.user_id)

    async def set_gift_wrap(self, cart: Cart, enabled: bool) -> Cart:
        cart.has_gift_wrap = enabled
        await self.session.commit()
        return await self.get_by_user_id(cart.user_id)

    async def lock_items_for_update(self, cart_id: uuid.UUID) -> List[CartItem]:
        """SELECT FOR UPDATE on cart items for checkout concurrency control."""
        from sqlalchemy import text
        stmt = (
            select(CartItem)
            .options(
                selectinload(CartItem.product),
                selectinload(CartItem.variant),
            )
            .where(CartItem.cart_id == cart_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
