"""
Seed script for extended e-commerce features:
- Promo codes (FREPPING10, STREET25)
- Delivery options (STANDARD, EXPRESS, SAME_DAY)
- Sample gift card (FRP-GC-TEST-2026 with PIN 1234)
"""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sys
import os

# Add parent directory to path so app modules can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.enums import DiscountType
from app.core.security import hash_pin
from app.db.models.delivery_option import DeliveryOption
from app.db.models.gift_card import GiftCard
from app.db.models.promo_code import PromoCode
from app.db.session import AsyncSessionLocal
from sqlalchemy import select


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        print("🌱 Seeding extended features...")

        # ── 1. Promo Codes ────────────────────────────────────────────────────
        promo_data = [
            {
                "code": "FREPPING10",
                "description": "10% off your entire order with no minimum spend",
                "discount_type": DiscountType.PERCENT,
                "discount_value": Decimal("10.00"),
                "min_order_amount": Decimal("0.00"),
                "max_discount_amount": Decimal("50.00"),
                "usage_limit": 1000,
                "per_user_limit": 1,
                "is_active": True,
            },
            {
                "code": "STREET25",
                "description": "25% off street style collection for orders over $150",
                "discount_type": DiscountType.PERCENT,
                "discount_value": Decimal("25.00"),
                "min_order_amount": Decimal("150.00"),
                "max_discount_amount": Decimal("100.00"),
                "usage_limit": 500,
                "per_user_limit": 1,
                "is_active": True,
            },
        ]

        for p_info in promo_data:
            existing = await session.execute(
                select(PromoCode).where(PromoCode.code == p_info["code"])
            )
            if not existing.scalar_one_or_none():
                promo = PromoCode(**p_info)
                session.add(promo)
                print(f"  [+] Created PromoCode: {p_info['code']}")
            else:
                print(f"  [.] PromoCode already exists: {p_info['code']}")

        # ── 2. Delivery Options ───────────────────────────────────────────────
        delivery_data = [
            {
                "code": "STANDARD",
                "title": "Standard Shipping",
                "description": "Economical delivery via standard ground carrier",
                "badge": "Free",
                "icon": "truck",
                "price": Decimal("0.00"),
                "estimated_days_min": 3,
                "estimated_days_max": 5,
                "estimated_label": "3-5 business days",
                "sort_order": 1,
                "is_active": True,
            },
            {
                "code": "EXPRESS",
                "title": "Express Delivery",
                "description": "Fast priority delivery direct to your doorstep",
                "badge": "Popular",
                "icon": "zap",
                "price": Decimal("15.00"),
                "estimated_days_min": 1,
                "estimated_days_max": 2,
                "estimated_label": "1-2 business days",
                "sort_order": 2,
                "is_active": True,
            },
            {
                "code": "SAME_DAY",
                "title": "Same-Day Courier",
                "description": "Available in select metropolitan regions",
                "badge": "Fastest",
                "icon": "clock",
                "price": Decimal("25.00"),
                "estimated_days_min": 0,
                "estimated_days_max": 1,
                "estimated_label": "Today within 4 hours",
                "sort_order": 3,
                "is_active": True,
            },
        ]

        for d_info in delivery_data:
            existing = await session.execute(
                select(DeliveryOption).where(DeliveryOption.code == d_info["code"])
            )
            if not existing.scalar_one_or_none():
                opt = DeliveryOption(**d_info)
                session.add(opt)
                print(f"  [+] Created DeliveryOption: {d_info['code']}")
            else:
                print(f"  [.] DeliveryOption already exists: {d_info['code']}")

        # ── 3. Sample Gift Card ───────────────────────────────────────────────
        gc_code = "FRP-GC-TEST-2026"
        existing_gc = await session.execute(
            select(GiftCard).where(GiftCard.code == gc_code)
        )
        if not existing_gc.scalar_one_or_none():
            gc = GiftCard(
                code=gc_code,
                pin_hash=hash_pin("1234"),
                initial_balance=Decimal("100.00"),
                balance=Decimal("100.00"),
                currency="USD",
                is_active=True,
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            )
            session.add(gc)
            print(f"  [+] Created GiftCard: {gc_code} (PIN: 1234, Balance: $100.00)")
        else:
            print(f"  [.] GiftCard already exists: {gc_code}")

        await session.commit()
        print("✅ Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
