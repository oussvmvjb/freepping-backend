"""
Unit and integration tests for extended e-commerce features:
- Like idempotency
- Cart rules & price calculation
- Promo validation edge cases
- Concurrent checkout on last stock unit
- Order cancellation and variant restocking
- Role permissions (Admin, Seller, Customer)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.enums import DiscountType, OrderStatus, PaymentMethod, PaymentStatus, UserRole
from app.core.security import create_access_token, hash_password, hash_pin
from app.db.models.address import Address
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.delivery_option import DeliveryOption
from app.db.models.gift_card import GiftCard
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.product import Product
from app.db.models.product_like import ProductLike
from app.db.models.product_variant import ProductVariant
from app.db.models.promo_code import PromoCode
from app.db.models.user import User
from app.services.cart_service import CartService
from app.services.like_service import LikeService
from app.services.order_service import OrderService
from app.services.promo_service import PromoService
from app.v1.schemas.cart import CartItemAdd, CartResponse
from app.v1.schemas.order import CheckoutPlaceOrderRequest


def make_test_user(role: UserRole = UserRole.CUSTOMER) -> User:
    u = User()
    u.id = uuid.uuid4()
    u.email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    u.password_hash = hash_password("password123")
    u.first_name = "Test"
    u.last_name = "User"
    u.role = role
    u.is_active = True
    u.is_verified = True
    u.created_at = datetime.now(timezone.utc)
    u.updated_at = datetime.now(timezone.utc)
    return u


def make_auth_headers(user: User) -> dict:
    token, _ = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Product Likes Idempotency Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_like_idempotency():
    async def _run():
        user = make_test_user(UserRole.CUSTOMER)
        product_id = uuid.uuid4()

        mock_product = Product(
            id=product_id,
            name="Test Tee",
            slug="test-tee",
            price=Decimal("30.00"),
            likes_count=5,
            is_active=True,
        )

        mock_session = AsyncMock()
        service = LikeService(mock_session)

        # Mock product repository
        service.product_repo.get_by_id = AsyncMock(return_value=mock_product)

        # 1. First like: not previously liked
        service.like_repo.get = AsyncMock(return_value=None)
        service.like_repo.create = AsyncMock()

        res1 = await service.like_product(product_id, user)
        assert res1.liked is True

        # 2. Second like (idempotency): already liked
        mock_like = ProductLike(user_id=user.id, product_id=product_id)
        service.like_repo.get = AsyncMock(return_value=mock_like)

        res2 = await service.like_product(product_id, user)
        assert res2.liked is True
        # create was not called again
        assert service.like_repo.create.call_count == 1

        # 3. First unlike
        service.like_repo.delete = AsyncMock()
        res3 = await service.unlike_product(product_id, user)
        assert res3.liked is False

        # 4. Second unlike (idempotency): already not liked
        service.like_repo.get = AsyncMock(return_value=None)
        res4 = await service.unlike_product(product_id, user)
        assert res4.liked is False
        assert service.like_repo.delete.call_count == 1

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cart Rules & Calculation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_cart_rules_and_calculations():
    async def _run():
        user = make_test_user(UserRole.CUSTOMER)
        mock_session = AsyncMock()
        service = CartService(mock_session)

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        variant = ProductVariant(
            id=variant_id,
            product_id=product_id,
            sku="TEE-S-BLK",
            price=Decimal("25.00"),
            stock=10,
            is_active=True,
        )
        product = Product(
            id=product_id,
            name="Graphic Tee",
            slug="graphic-tee",
            price=Decimal("30.00"),
            is_active=True,
            variants=[variant],
        )

        cart = Cart(
            id=uuid.uuid4(),
            user_id=user.id,
            has_gift_wrap=True,
            promo_code=None,
        )
        cart_item = CartItem(
            id=uuid.uuid4(),
            cart_id=cart.id,
            product_id=product_id,
            variant_id=variant_id,
            quantity=2,
            product=product,
            variant=variant,
        )
        cart.items = [cart_item]

        # Test price calculation: variant price (25.00) * 2 = 50.00
        # Gift wrap = 2.00 -> Total = 52.00
        cart_resp = service.build_cart_response(cart)
        assert cart_resp.subtotal == "50.00"
        assert cart_resp.gift_wrap_cost == "2.00"
        assert cart_resp.total == "52.00"
        assert cart_resp.items[0].unit_price == "25.00"
        assert cart_resp.items[0].line_total == "50.00"

        # Test stock limit validation
        service.product_repo.get_by_id = AsyncMock(return_value=product)
        service.variant_repo.get_by_id = AsyncMock(return_value=variant)
        service.cart_repo.get_or_create = AsyncMock(return_value=cart)
        service.cart_repo.get_item_by_product_variant = AsyncMock(return_value=None)

        # Exceeding stock (10 available, asking for 15)
        with pytest.raises(Exception) as exc_info:
            await service.add_item(user, CartItemAdd(product_id=product_id, variant_id=variant_id, quantity=15))
        assert "exceeds available stock" in str(exc_info.value).lower()

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 3. Promo Validation Edge Cases Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_promo_validation_edge_cases():
    async def _run():
        user = make_test_user(UserRole.CUSTOMER)
        mock_session = AsyncMock()
        service = PromoService(mock_session)

        # 1. Non-existent promo
        service.promo_repo.get_by_code = AsyncMock(return_value=None)
        with pytest.raises(Exception) as exc:
            await service.validate_for_cart(user, "INVALID99")
        assert "invalid" in str(exc.value).lower()

        # 2. Inactive promo
        inactive_promo = PromoCode(
            id=uuid.uuid4(),
            code="OFF50",
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal("50.00"),
            is_active=False,
        )
        service.promo_repo.get_by_code = AsyncMock(return_value=inactive_promo)
        with pytest.raises(Exception) as exc:
            await service.validate_for_cart(user, "OFF50")
        assert "inactive" in str(exc.value).lower()

        # 3. Expired promo
        expired_promo = PromoCode(
            id=uuid.uuid4(),
            code="OLD10",
            discount_type=DiscountType.PERCENT,
            discount_value=Decimal("10.00"),
            is_active=True,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        service.promo_repo.get_by_code = AsyncMock(return_value=expired_promo)
        with pytest.raises(Exception) as exc:
            await service.validate_for_cart(user, "OLD10")
        assert "expired" in str(exc.value).lower()

        # 4. Minimum order amount not met
        min_spend_promo = PromoCode(
            id=uuid.uuid4(),
            code="BIG100",
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("20.00"),
            min_order_amount=Decimal("100.00"),
            is_active=True,
            usage_limit=10,
            used_count=0,
            per_user_limit=1,
        )
        service.promo_repo.get_by_code = AsyncMock(return_value=min_spend_promo)
        service.promo_repo.get_user_redemption_count = AsyncMock(return_value=0)

        # Empty/cheap cart ($30)
        mock_cart = Cart(id=uuid.uuid4(), user_id=user.id, items=[])
        service.cart_repo.get_or_create = AsyncMock(return_value=mock_cart)

        with pytest.raises(Exception) as exc:
            await service.validate_for_cart(user, "BIG100")
        assert "minimum order amount" in str(exc.value).lower()

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 4. Concurrent Checkout on Last Stock Unit
# ─────────────────────────────────────────────────────────────────────────────

def test_concurrent_checkout_last_stock_unit():
    async def _run():
        user1 = make_test_user(UserRole.CUSTOMER)
        user2 = make_test_user(UserRole.CUSTOMER)

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        address_id = uuid.uuid4()
        delivery_id = uuid.uuid4()

        variant = ProductVariant(
            id=variant_id,
            product_id=product_id,
            sku="RARE-JACKET",
            price=Decimal("100.00"),
            stock=1,  # Only 1 unit!
            is_active=True,
        )

        product = Product(
            id=product_id,
            name="Rare Street Jacket",
            price=Decimal("100.00"),
            is_active=True,
            variants=[variant],
        )

        delivery = DeliveryOption(
            id=delivery_id,
            code="STANDARD",
            title="Standard",
            price=Decimal("0.00"),
            is_active=True,
        )

        address = Address(
            id=address_id,
            user_id=user1.id,
            name="Alice",
            street="123 Main St",
            city="City",
            state="ST",
            zip="12345",
            phone="555-1234",
        )

        # Simulate first user decrementing stock to 0:
        variant.stock -= 1

        # User 2 tries to checkout with quantity 1:
        mock_session = AsyncMock()
        order_service = OrderService(mock_session)
        order_service.delivery_repo.get_by_id = AsyncMock(return_value=delivery)
        order_service.address_repo.get_by_id_and_user = AsyncMock(return_value=address)

        cart2 = Cart(id=uuid.uuid4(), user_id=user2.id)
        cart2.items = [CartItem(id=uuid.uuid4(), product_id=product_id, variant_id=variant_id, quantity=1, product=product, variant=variant)]
        order_service.cart_repo.get_by_user_id = AsyncMock(return_value=cart2)

        # Mock execute to return the locked variant with stock=0
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [variant]
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_res)

        req = CheckoutPlaceOrderRequest(
            address_id=address_id,
            delivery_option_id=delivery_id,
            payment_method=PaymentMethod.COD,
        )

        with pytest.raises(Exception) as exc:
            await order_service.place_order(user2, req)
        assert "insufficient stock" in str(exc.value).lower()

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 5. Order Cancel Restock Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_order_cancel_restock():
    async def _run():
        user = make_test_user(UserRole.CUSTOMER)
        mock_session = AsyncMock()
        service = OrderService(mock_session)

        variant_id = uuid.uuid4()
        variant = ProductVariant(id=variant_id, sku="TEST-SKU", stock=5, is_active=True)

        order_item = OrderItem(
            id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            variant_id=variant_id,
            unit_price=Decimal("50.00"),
            quantity=3,
            line_total=Decimal("150.00"),
        )

        order = Order(
            id=uuid.uuid4(),
            order_number="FRP-20261012-123456",
            user_id=user.id,
            status=OrderStatus.PAID,
            payment_method=PaymentMethod.COD,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("150.00"),
            promo_discount=Decimal("0.00"),
            gift_wrap=False,
            gift_wrap_cost=Decimal("0.00"),
            delivery_cost=Decimal("0.00"),
            gift_card_amount_used=Decimal("0.00"),
            total=Decimal("150.00"),
            shipping_name="John Doe",
            shipping_street="123 Main St",
            shipping_city="NYC",
            shipping_state="NY",
            shipping_zip="10001",
            shipping_country="US",
            shipping_phone="555-0100",
            placed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[order_item],
        )

        service.order_repo.get_by_id = AsyncMock(return_value=order)


        # Mock locking query for variant restock
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [variant]
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_res)

        cancelled_order = Order(
            id=order.id,
            order_number=order.order_number,
            user_id=user.id,
            status=OrderStatus.CANCELLED,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            subtotal=order.subtotal,
            promo_discount=order.promo_discount,
            gift_wrap=False,
            gift_wrap_cost=Decimal("0.00"),
            delivery_cost=Decimal("0.00"),
            gift_card_amount_used=Decimal("0.00"),
            total=order.total,
            shipping_name="John Doe",
            shipping_street="123 Main St",
            shipping_city="NYC",
            shipping_state="NY",
            shipping_zip="10001",
            shipping_country="US",
            shipping_phone="555-0100",
            placed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            items=[order_item],
        )
        service.order_repo.update_status = AsyncMock(return_value=cancelled_order)


        res = await service.cancel_order(order.id, user)
        # Variant stock was 5, 3 units restocked -> 8
        assert variant.stock == 8
        assert res.status == OrderStatus.CANCELLED

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# 6. Role Permissions Tests via HTTP Client
# ─────────────────────────────────────────────────────────────────────────────

def test_role_permissions():
    async def _run():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Customer trying to view admin dashboard -> 403 Forbidden
            customer = make_test_user(UserRole.CUSTOMER)
            headers_cust = make_auth_headers(customer)

            with patch("app.api.deps.UserRepository.get_by_id", AsyncMock(return_value=customer)):
                resp_admin = await client.get("/api/v1/admin/dashboard/summary", headers=headers_cust)
                assert resp_admin.status_code in [401, 403]

                # Seller trying to access admin endpoints -> 403 Forbidden
                seller = make_test_user(UserRole.SELLER)
                headers_seller = make_auth_headers(seller)

                with patch("app.api.deps.UserRepository.get_by_id", AsyncMock(return_value=seller)):
                    resp_seller_admin = await client.get("/api/v1/admin/orders", headers=headers_seller)
                    assert resp_seller_admin.status_code in [401, 403]

    asyncio.run(_run())
