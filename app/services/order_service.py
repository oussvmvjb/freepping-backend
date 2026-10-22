from datetime import datetime, timezone
from decimal import Decimal
import logging
import math
import random
import string
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import (
    FulfillmentStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    UserRole,
    DiscountType,
)
from app.core.exceptions import (
    AuthorizationException,
    BusinessRuleException,
    ResourceNotFoundException,
)
from app.core.security import verify_pin
from app.db.models.address import Address
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.delivery_option import DeliveryOption
from app.db.models.gift_card import GiftCard
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.order_status_history import OrderStatusHistory
from app.db.models.payment import Payment
from app.db.models.product_variant import ProductVariant
from app.db.models.promo_code import PromoCode
from app.db.models.saved_payment_method import SavedPaymentMethod
from app.db.models.user import User
from app.db.repositories.address_repository import AddressRepository
from app.db.repositories.cart_repository import CartRepository
from app.db.repositories.delivery_option_repository import DeliveryOptionRepository
from app.db.repositories.gift_card_repository import GiftCardRepository
from app.db.repositories.order_repository import OrderRepository
from app.db.repositories.product_repository import ProductRepository
from app.db.repositories.promo_code_repository import PromoCodeRepository
from app.db.repositories.saved_payment_method_repository import SavedPaymentMethodRepository
from app.services.payment_gateway import payment_gateway
from app.services.redis.redis_client import redis_client
from app.v1.schemas.address import AddressResponse
from app.v1.schemas.cart import CartItemResponse
from app.v1.schemas.delivery_option import DeliveryOptionResponse
from app.v1.schemas.order import (
    AddressSnapshot,
    CheckoutPlaceOrderRequest,
    CheckoutPreviewRequest,
    CheckoutPreviewResponse,
    OrderItemResponse,
    OrderListResponse,
    OrderResponse,
    OrderStatusHistoryResponse,
    OrderStatusUpdateRequest,
    PaymentSummaryResponse,
    SellerItemStatusUpdateRequest,
)

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.order_repo = OrderRepository(session)
        self.cart_repo = CartRepository(session)
        self.address_repo = AddressRepository(session)
        self.delivery_repo = DeliveryOptionRepository(session)
        self.promo_repo = PromoCodeRepository(session)
        self.gift_card_repo = GiftCardRepository(session)
        self.saved_pm_repo = SavedPaymentMethodRepository(session)
        self.product_repo = ProductRepository(session)

    @staticmethod
    def generate_order_number() -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"FRP-{date_str}-{rand_str}"

    @staticmethod
    def _compute_item_price(item: CartItem) -> Decimal:
        if item.variant and item.variant.price is not None:
            return Decimal(str(item.variant.price))
        if item.product and item.product.price is not None:
            return Decimal(str(item.product.price))
        return Decimal("0.00")

    def _calculate_discount(self, promo: Optional[PromoCode], subtotal: Decimal) -> Decimal:
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

    def build_order_response(self, order: Order, scoped_seller_id: Optional[uuid.UUID] = None) -> OrderResponse:
        # Filter items if viewing as seller
        items = order.items or []
        if scoped_seller_id is not None:
            items = [it for it in items if it.seller_id == scoped_seller_id]

        item_responses = [
            OrderItemResponse(
                id=it.id or uuid.uuid4(),
                order_id=it.order_id or order.id,
                product_id=it.product_id,
                variant_id=it.variant_id,
                seller_id=it.seller_id,
                product_name=it.product_name or "Product",
                variant_label=it.variant_label,
                sku=it.sku,
                image_url=it.image_url,
                unit_price=f"{it.unit_price:.2f}" if it.unit_price is not None else "0.00",
                quantity=it.quantity or 1,
                line_total=f"{it.line_total:.2f}" if it.line_total is not None else "0.00",
                fulfillment_status=it.fulfillment_status,
            )
            for it in items
        ]


        history_responses = [
            OrderStatusHistoryResponse(
                id=h.id,
                from_status=h.from_status,
                to_status=h.to_status,
                changed_by=h.changed_by,
                note=h.note,
                created_at=h.created_at,
            )
            for h in (order.status_history or [])
        ]

        payment_summary = None
        if order.payments and len(order.payments) > 0:
            pm = order.payments[0]
            payment_summary = PaymentSummaryResponse(
                id=pm.id,
                provider=pm.provider,
                provider_ref=pm.provider_ref,
                amount=f"{pm.amount:.2f}",
                currency=pm.currency,
                status=pm.status,
                card_brand=pm.card_brand,
                card_last4=pm.card_last4,
                created_at=pm.created_at,
            )

        return OrderResponse(
            id=order.id,
            order_number=order.order_number,
            user_id=order.user_id,
            status=order.status,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            subtotal=f"{order.subtotal:.2f}",
            promo_discount=f"{order.promo_discount:.2f}",
            gift_wrap=order.gift_wrap,
            gift_wrap_cost=f"{order.gift_wrap_cost:.2f}",
            delivery_cost=f"{order.delivery_cost:.2f}",
            gift_card_amount_used=f"{order.gift_card_amount_used:.2f}",
            total=f"{order.total:.2f}",
            shipping_address=AddressSnapshot(
                name=order.shipping_name,
                street=order.shipping_street,
                city=order.shipping_city,
                state=order.shipping_state,
                zip=order.shipping_zip,
                country=order.shipping_country,
                phone=order.shipping_phone,
            ),
            tracking_number=order.tracking_number,
            estimated_delivery_at=order.estimated_delivery_at,
            placed_at=order.placed_at or datetime.now(timezone.utc),
            paid_at=order.paid_at,
            shipped_at=order.shipped_at,
            delivered_at=order.delivered_at,
            cancelled_at=order.cancelled_at,
            created_at=order.created_at or order.placed_at or datetime.now(timezone.utc),
            updated_at=order.updated_at or datetime.now(timezone.utc),
            items=item_responses,
            status_history=history_responses,
            payment=payment_summary,

        )

    async def preview_checkout(
        self,
        user: User,
        preview_in: CheckoutPreviewRequest,
    ) -> CheckoutPreviewResponse:
        cart = await self.cart_repo.get_by_user_id(user.id)
        if not cart or not cart.items:
            raise BusinessRuleException("Your cart is empty.")

        address = await self.address_repo.get_by_id_and_user(preview_in.address_id, user.id)
        if not address:
            raise ResourceNotFoundException("Address", preview_in.address_id)

        delivery = await self.delivery_repo.get_by_id(preview_in.delivery_option_id)
        if not delivery or not delivery.is_active:
            raise ResourceNotFoundException("DeliveryOption", preview_in.delivery_option_id)

        subtotal = Decimal("0.00")
        items_out = []
        for it in cart.items:
            # Check stock
            if it.variant and it.variant.stock is not None and it.quantity > it.variant.stock:
                raise BusinessRuleException(
                    f"Item '{it.product.name}' has insufficient stock (available: {it.variant.stock})."
                )
            u_price = self._compute_item_price(it)
            l_total = (u_price * it.quantity).quantize(Decimal("0.01"))
            subtotal += l_total

            img_url = None
            if it.product and it.product.images:
                primary = next((img.image_url for img in it.product.images if img.is_primary), None)
                img_url = primary or it.product.images[0].image_url

            items_out.append(
                CartItemResponse(
                    id=it.id,
                    product_id=it.product_id,
                    variant_id=it.variant_id,
                    quantity=it.quantity,
                    unit_price=f"{u_price:.2f}",
                    line_total=f"{l_total:.2f}",
                    image_url=img_url,
                )
            )

        promo_discount = self._calculate_discount(cart.promo_code, subtotal)
        gift_wrap_cost = Decimal(str(settings.GIFT_WRAP_COST)).quantize(Decimal("0.01")) if cart.has_gift_wrap else Decimal("0.00")
        delivery_cost = Decimal(str(delivery.price)).quantize(Decimal("0.01"))
        total = max(Decimal("0.00"), subtotal - promo_discount) + gift_wrap_cost + delivery_cost

        return CheckoutPreviewResponse(
            items=items_out,
            subtotal=f"{subtotal:.2f}",
            promo_discount=f"{promo_discount:.2f}",
            gift_wrap=cart.has_gift_wrap,
            gift_wrap_cost=f"{gift_wrap_cost:.2f}",
            delivery_option=DeliveryOptionResponse.model_validate(delivery),
            delivery_cost=f"{delivery_cost:.2f}",
            total=f"{total:.2f}",
        )

    async def place_order(
        self,
        user: User,
        checkout_in: CheckoutPlaceOrderRequest,
        idempotency_key: Optional[str] = None,
    ) -> OrderResponse:
        # 0. Check Idempotency-Key
        if idempotency_key:
            existing_order = await self.order_repo.get_by_idempotency_key(idempotency_key)
            if existing_order:
                return self.build_order_response(existing_order)

        # 1. Fetch and validate cart
        cart = await self.cart_repo.get_by_user_id(user.id)
        if not cart or not cart.items:
            raise BusinessRuleException("Cannot place order with an empty cart.")

        # Address & Delivery validation
        address = await self.address_repo.get_by_id_and_user(checkout_in.address_id, user.id)
        if not address:
            raise ResourceNotFoundException("Address", checkout_in.address_id)

        delivery = await self.delivery_repo.get_by_id(checkout_in.delivery_option_id)
        if not delivery or not delivery.is_active:
            raise ResourceNotFoundException("DeliveryOption", checkout_in.delivery_option_id)

        # Step 1: SELECT FOR UPDATE on variants to guarantee atomic concurrency
        variant_ids = [it.variant_id for it in cart.items if it.variant_id is not None]
        variants_by_id = {}
        if variant_ids:
            v_stmt = (
                select(ProductVariant)
                .where(ProductVariant.id.in_(variant_ids))
                .with_for_update()
            )
            v_result = await self.session.execute(v_stmt)
            for v in v_result.scalars().all():
                variants_by_id[v.id] = v

        # Validate stock
        for it in cart.items:
            if it.variant_id:
                variant = variants_by_id.get(it.variant_id)
                if not variant or not variant.is_active:
                    raise BusinessRuleException(f"A product variant in your cart is no longer available.")
                if variant.stock < it.quantity:
                    raise BusinessRuleException(
                        f"Insufficient stock for '{it.product.name if it.product else 'Product'}'. "
                        f"Requested: {it.quantity}, available: {variant.stock}."
                    )

        # Step 2: Recompute totals server-side
        subtotal = Decimal("0.00")
        items_data = []
        product_ids_to_invalidate = set()

        for it in cart.items:
            unit_price = self._compute_item_price(it)
            line_total = (unit_price * it.quantity).quantize(Decimal("0.01"))
            subtotal += line_total
            product_ids_to_invalidate.add(str(it.product_id))

            img_url = None
            if it.product and it.product.images:
                primary = next((img.image_url for img in it.product.images if img.is_primary), None)
                img_url = primary or it.product.images[0].image_url

            variant_label = None
            sku = None
            if it.variant:
                parts = [p for p in [it.variant.size, it.variant.color] if p]
                variant_label = " / ".join(parts) if parts else None
                sku = it.variant.sku

            items_data.append({
                "product_id": it.product_id,
                "variant_id": it.variant_id,
                "seller_id": it.product.seller_id if it.product else None,
                "product_name": it.product.name if it.product else "Product",
                "variant_label": variant_label,
                "sku": sku,
                "image_url": img_url,
                "unit_price": unit_price,
                "quantity": it.quantity,
                "line_total": line_total,
                "fulfillment_status": FulfillmentStatus.PENDING,
            })

        promo = cart.promo_code
        promo_discount = Decimal("0.00")
        if promo:
            # Validate promo
            now = datetime.now(timezone.utc)
            if (
                promo.is_active
                and (not promo.starts_at or promo.starts_at <= now)
                and (not promo.expires_at or promo.expires_at > now)
                and (promo.usage_limit is None or promo.used_count < promo.usage_limit)
                and (subtotal >= Decimal(str(promo.min_order_amount or 0)))
            ):
                user_count = await self.promo_repo.get_user_redemption_count(user.id, promo.id)
                if user_count < promo.per_user_limit:
                    promo_discount = self._calculate_discount(promo, subtotal)

        gift_wrap_cost = Decimal(str(settings.GIFT_WRAP_COST)).quantize(Decimal("0.01")) if cart.has_gift_wrap else Decimal("0.00")
        delivery_cost = Decimal(str(delivery.price)).quantize(Decimal("0.01"))
        total = max(Decimal("0.00"), subtotal - promo_discount) + gift_wrap_cost + delivery_cost

        # Step 3: Handle Gift Card deduction if specified
        gift_card_amount_used = Decimal("0.00")
        gift_card: Optional[GiftCard] = None
        if checkout_in.gift_card:
            gift_card = await self.gift_card_repo.get_by_code(checkout_in.gift_card.number)
            if not gift_card or not verify_pin(checkout_in.gift_card.pin, gift_card.pin_hash):
                raise BusinessRuleException("Invalid gift card number or PIN.")
            if not gift_card.is_active:
                raise BusinessRuleException("Gift card is inactive.")
            now = datetime.now(timezone.utc)
            if gift_card.expires_at and gift_card.expires_at < now:
                raise BusinessRuleException("Gift card has expired.")

            gift_card_amount_used = min(gift_card.balance, total).quantize(Decimal("0.01"))
            if checkout_in.payment_method == PaymentMethod.GIFT_CARD and gift_card_amount_used < total:
                raise BusinessRuleException(
                    f"Gift card balance (${gift_card.balance:.2f}) does not fully cover the order total (${total:.2f})."
                )

        remaining_to_pay = (total - gift_card_amount_used).quantize(Decimal("0.01"))

        # Step 4: Process Payment
        order_status = OrderStatus.PENDING
        payment_status = PaymentStatus.PENDING
        payment_record_data = None
        now = datetime.now(timezone.utc)

        if checkout_in.payment_method == PaymentMethod.CARD:
            if not checkout_in.payment_token:
                raise BusinessRuleException("Payment token is required for card checkout.")

            charge_result = await payment_gateway.charge(
                amount=remaining_to_pay,
                currency="USD",
                token=checkout_in.payment_token,
                description=f"Order by user {user.email}",
            )
            if not charge_result.success:
                raise BusinessRuleException(f"Payment failed: {charge_result.error_message}")

            order_status = OrderStatus.PAID
            payment_status = PaymentStatus.PAID
            payment_record_data = {
                "provider": charge_result.provider,
                "provider_ref": charge_result.provider_ref,
                "amount": remaining_to_pay,
                "currency": "USD",
                "status": PaymentStatus.PAID,
                "card_brand": charge_result.card_brand,
                "card_last4": charge_result.card_last4,
            }

            # If user selected save_card
            if checkout_in.save_card:
                await self.saved_pm_repo.create({
                    "user_id": user.id,
                    "provider_token": checkout_in.payment_token,
                    "brand": charge_result.card_brand or "Visa",
                    "last4": charge_result.card_last4 or "4242",
                    "exp_month": 12,
                    "exp_year": 2030,
                    "is_default": False,
                })

        elif checkout_in.payment_method == PaymentMethod.COD:
            order_status = OrderStatus.PENDING
            payment_status = PaymentStatus.PENDING
            payment_record_data = {
                "provider": "manual_cod",
                "provider_ref": "cod",
                "amount": total,
                "currency": "USD",
                "status": PaymentStatus.PENDING,
            }

        elif checkout_in.payment_method == PaymentMethod.GIFT_CARD:
            order_status = OrderStatus.PAID
            payment_status = PaymentStatus.PAID

        # Step 5: Create Order
        order_number = self.generate_order_number()
        order_data = {
            "order_number": order_number,
            "user_id": user.id,
            "status": order_status,
            "payment_method": checkout_in.payment_method,
            "payment_status": payment_status,
            "subtotal": subtotal,
            "promo_code_id": promo.id if promo else None,
            "promo_discount": promo_discount,
            "gift_wrap": cart.has_gift_wrap,
            "gift_wrap_cost": gift_wrap_cost,
            "delivery_option_id": delivery.id,
            "delivery_cost": delivery_cost,
            "gift_card_amount_used": gift_card_amount_used,
            "total": total,
            "shipping_name": address.name,
            "shipping_street": address.street,
            "shipping_city": address.city,
            "shipping_state": address.state,
            "shipping_zip": address.zip,
            "shipping_country": address.country,
            "shipping_phone": address.phone,
            "idempotency_key": idempotency_key,
            "placed_at": now,
            "paid_at": now if payment_status == PaymentStatus.PAID else None,
        }

        order = await self.order_repo.create(order_data, items_data)

        # Record Status History
        await self.order_repo.add_status_history(
            order_id=order.id,
            from_status=None,
            to_status=order_status.value,
            changed_by=user.id,
            note="Order placed by customer",
        )

        # Record Payment
        if payment_record_data:
            payment_record_data["order_id"] = order.id
            await self.order_repo.add_payment(payment_record_data)

        # Deduct Gift Card balance if used
        if gift_card and gift_card_amount_used > 0:
            await self.gift_card_repo.deduct_balance(
                card=gift_card,
                amount=gift_card_amount_used,
                order_id=order.id,
            )

        # Write Promo Redemption if used
        if promo and promo_discount > 0:
            await self.promo_repo.create_redemption(
                promo_id=promo.id,
                user_id=user.id,
                order_id=order.id,
            )

        # Step 6: Decrement stock
        for it in cart.items:
            if it.variant_id:
                variant = variants_by_id[it.variant_id]
                variant.stock = max(0, variant.stock - it.quantity)

        # Clear cart
        await self.cart_repo.clear(cart)
        cart.promo_code_id = None
        cart.has_gift_wrap = False

        await self.session.commit()

        # Invalidate product caches
        for pid in product_ids_to_invalidate:
            await redis_client.invalidate_product_caches(pid)

        logger.info(f"Order placed: {order.order_number} for user {user.id}, total: ${total:.2f}")

        # Return fresh loaded order
        saved_order = await self.order_repo.get_by_id(order.id)
        return self.build_order_response(saved_order)

    async def get_order_by_id(self, order_id: uuid.UUID, current_user: User) -> OrderResponse:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        # Owner, Admin, or Seller check
        if current_user.role in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
            return self.build_order_response(order)

        if current_user.role == UserRole.SELLER:
            seller_items = [it for it in order.items if it.seller_id == current_user.id]
            if not seller_items:
                raise AuthorizationException("You do not have permission to view this order.")
            return self.build_order_response(order, scoped_seller_id=current_user.id)

        if order.user_id != current_user.id:
            raise AuthorizationException("You do not have permission to view this order.")

        return self.build_order_response(order)

    async def cancel_order(self, order_id: uuid.UUID, user: User) -> OrderResponse:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        if order.user_id != user.id and user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
            raise AuthorizationException("You do not have permission to cancel this order.")

        if order.status not in [OrderStatus.PENDING, OrderStatus.PAID, OrderStatus.PROCESSING]:
            raise BusinessRuleException(f"Order cannot be cancelled in status '{order.status.value}'.")

        # Restock variants
        variant_ids = [it.variant_id for it in order.items if it.variant_id]
        if variant_ids:
            v_stmt = (
                select(ProductVariant)
                .where(ProductVariant.id.in_(variant_ids))
                .with_for_update()
            )
            v_res = await self.session.execute(v_stmt)
            v_map = {v.id: v for v in v_res.scalars().all()}
            for it in order.items:
                if it.variant_id and it.variant_id in v_map:
                    v_map[it.variant_id].stock += it.quantity

        # Refund gift card if used
        if order.gift_card_amount_used > 0 and order.gift_card_id:
            gc = await self.gift_card_repo.get_by_id(order.gift_card_id)
            if gc:
                await self.gift_card_repo.refund_balance(gc, order.gift_card_amount_used, order.id)

        # Refund card payment if charged
        if order.payments and len(order.payments) > 0:
            pm = order.payments[0]
            if pm.status == PaymentStatus.PAID and pm.provider_ref:
                await payment_gateway.refund(pm.provider_ref, pm.amount, reason="Customer cancelled")
                pm.status = PaymentStatus.REFUNDED

        updated = await self.order_repo.update_status(
            order=order,
            new_status=OrderStatus.CANCELLED,
            changed_by=user.id,
            note="Order cancelled by user" if order.user_id == user.id else "Order cancelled by admin",
        )

        for it in order.items:
            if it.product_id:
                await redis_client.invalidate_product_caches(str(it.product_id))

        return self.build_order_response(updated)

    async def list_my_orders(
        self,
        user: User,
        page: int = 1,
        page_size: int = 20,
        status: Optional[OrderStatus] = None,
    ) -> OrderListResponse:
        items, total = await self.order_repo.list_by_user(user.id, page=page, page_size=page_size, status=status)
        pages = math.ceil(total / page_size) if total > 0 else 0
        return OrderListResponse(
            items=[self.build_order_response(o) for o in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def list_admin_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        payment_status: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> OrderListResponse:
        items, total = await self.order_repo.list_admin(
            page=page,
            page_size=page_size,
            status=status,
            payment_status=payment_status,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        pages = math.ceil(total / page_size) if total > 0 else 0
        return OrderListResponse(
            items=[self.build_order_response(o) for o in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def admin_update_order_status(
        self,
        order_id: uuid.UUID,
        status_in: OrderStatusUpdateRequest,
        admin_user: User,
    ) -> OrderResponse:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        # Validate allowed transitions
        # Allowed:
        # PENDING -> PAID, PROCESSING, CANCELLED
        # PAID -> PROCESSING, SHIPPED, REFUNDED, CANCELLED
        # PROCESSING -> SHIPPED, CANCELLED, REFUNDED
        # SHIPPED -> DELIVERED, CANCELLED, REFUNDED
        # DELIVERED -> REFUNDED
        # CANCELLED -> terminal
        # REFUNDED -> terminal
        if order.status in [OrderStatus.CANCELLED, OrderStatus.REFUNDED]:
            raise BusinessRuleException(f"Order is already {order.status.value} and cannot change status.")

        updated = await self.order_repo.update_status(
            order=order,
            new_status=status_in.status,
            changed_by=admin_user.id,
            note=status_in.note,
            tracking_number=status_in.tracking_number,
        )
        return self.build_order_response(updated)

    async def admin_refund_order(self, order_id: uuid.UUID, admin_user: User) -> OrderResponse:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        if order.status == OrderStatus.REFUNDED:
            raise BusinessRuleException("Order has already been refunded.")

        # Restock variants
        for it in order.items:
            if it.variant:
                it.variant.stock += it.quantity

        # Process gateway refund
        if order.payments and len(order.payments) > 0:
            pm = order.payments[0]
            if pm.status == PaymentStatus.PAID and pm.provider_ref:
                await payment_gateway.refund(pm.provider_ref, pm.amount, reason="Admin refund")
                pm.status = PaymentStatus.REFUNDED

        # Restock gift card
        if order.gift_card_amount_used > 0 and order.gift_card_id:
            gc = await self.gift_card_repo.get_by_id(order.gift_card_id)
            if gc:
                await self.gift_card_repo.refund_balance(gc, order.gift_card_amount_used, order.id)

        updated = await self.order_repo.update_status(
            order=order,
            new_status=OrderStatus.REFUNDED,
            changed_by=admin_user.id,
            note="Refund processed by administrator",
        )
        return self.build_order_response(updated)

    async def list_seller_orders(
        self,
        seller_user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> OrderListResponse:
        items, total = await self.order_repo.list_seller_orders(
            seller_id=seller_user.id,
            page=page,
            page_size=page_size,
        )
        pages = math.ceil(total / page_size) if total > 0 else 0
        return OrderListResponse(
            items=[self.build_order_response(o, scoped_seller_id=seller_user.id) for o in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def update_seller_item_status(
        self,
        order_id: uuid.UUID,
        item_id: uuid.UUID,
        status_in: SellerItemStatusUpdateRequest,
        seller_user: User,
    ) -> OrderItemResponse:
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            raise ResourceNotFoundException("Order", order_id)

        target_item = next((it for it in order.items if it.id == item_id and it.seller_id == seller_user.id), None)
        if not target_item:
            raise ResourceNotFoundException("Order item for this seller", item_id)

        target_item.fulfillment_status = status_in.fulfillment_status
        await self.session.commit()

        return OrderItemResponse(
            id=target_item.id,
            order_id=target_item.order_id,
            product_id=target_item.product_id,
            variant_id=target_item.variant_id,
            seller_id=target_item.seller_id,
            product_name=target_item.product_name,
            variant_label=target_item.variant_label,
            sku=target_item.sku,
            image_url=target_item.image_url,
            unit_price=f"{target_item.unit_price:.2f}",
            quantity=target_item.quantity,
            line_total=f"{target_item.line_total:.2f}",
            fulfillment_status=target_item.fulfillment_status,
        )
