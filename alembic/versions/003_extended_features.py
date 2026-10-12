"""003_extended_features

Revision ID: 003_extended_features
Revises: 002_auth_users_stores
Create Date: 2026-10-12 18:30:00.000000

Adds:
- products.likes_count column
- product_likes table
- promo_codes and promo_redemptions tables
- carts and cart_items tables
- addresses table
- delivery_options table
- orders, order_items, order_status_history tables
- payments and saved_payment_methods tables
- gift_cards and gift_card_transactions tables
- CHECK constraints on quantity, balance, and stock
- Indexes on user_id, product_id, status, created_at, order_number
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_extended_features'
down_revision: Union[str, None] = '002_auth_users_stores'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Products update: likes_count ───────────────────────────────────────
    op.add_column(
        'products',
        sa.Column('likes_count', sa.Integer(), nullable=False, server_default='0')
    )

    # ── 2. Product Likes ──────────────────────────────────────────────────────
    op.create_table(
        'product_likes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'product_id', name='uq_product_likes_user_product')
    )
    op.create_index('ix_product_likes_product_id', 'product_likes', ['product_id'])
    op.create_index('ix_product_likes_user_id', 'product_likes', ['user_id'])

    # ── 3. Promo Codes & Redemptions ──────────────────────────────────────────
    op.create_table(
        'promo_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('discount_type', sa.String(20), nullable=False),
        sa.Column('discount_value', sa.Numeric(10, 2), nullable=False),
        sa.Column('min_order_amount', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('max_discount_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('per_user_limit', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_promo_codes_code', 'promo_codes', ['code'])

    op.create_table(
        'promo_redemptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('promo_code_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('promo_codes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_promo_redemptions_promo_code_id', 'promo_redemptions', ['promo_code_id'])
    op.create_index('ix_promo_redemptions_user_id', 'promo_redemptions', ['user_id'])

    # ── 4. Carts & Cart Items ─────────────────────────────────────────────────
    op.create_table(
        'carts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('promo_code_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('promo_codes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('has_gift_wrap', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_carts_user_id', 'carts', ['user_id'])

    op.create_table(
        'cart_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cart_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('carts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('variant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('product_variants.id', ondelete='CASCADE'), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('quantity >= 1', name='chk_cart_items_quantity'),
        sa.UniqueConstraint('cart_id', 'product_id', 'variant_id', name='uq_cart_items_cart_product_variant'),
    )
    op.create_index('ix_cart_items_cart_id', 'cart_items', ['cart_id'])

    # ── 5. Addresses ──────────────────────────────────────────────────────────
    op.create_table(
        'addresses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('street', sa.String(255), nullable=False),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('state', sa.String(100), nullable=False),
        sa.Column('zip', sa.String(20), nullable=False),
        sa.Column('country', sa.String(100), nullable=False, server_default='US'),
        sa.Column('phone', sa.String(30), nullable=False),
        sa.Column('type', sa.String(20), nullable=False, server_default='home'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_addresses_user_id', 'addresses', ['user_id'])

    # ── 6. Delivery Options ───────────────────────────────────────────────────
    op.create_table(
        'delivery_options',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('badge', sa.String(50), nullable=True),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('price', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('estimated_days_min', sa.Integer(), nullable=True),
        sa.Column('estimated_days_max', sa.Integer(), nullable=True),
        sa.Column('estimated_label', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_delivery_options_code', 'delivery_options', ['code'])

    # ── 7. Orders ─────────────────────────────────────────────────────────────
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_number', sa.String(50), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('payment_method', sa.String(20), nullable=False, server_default='CARD'),
        sa.Column('payment_status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('promo_code_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('promo_codes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('promo_discount', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('gift_wrap', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('gift_wrap_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('delivery_option_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('delivery_options.id', ondelete='SET NULL'), nullable=True),
        sa.Column('delivery_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('gift_card_amount_used', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('total', sa.Numeric(10, 2), nullable=False),
        sa.Column('shipping_name', sa.String(120), nullable=False),
        sa.Column('shipping_street', sa.String(255), nullable=False),
        sa.Column('shipping_city', sa.String(100), nullable=False),
        sa.Column('shipping_state', sa.String(100), nullable=False),
        sa.Column('shipping_zip', sa.String(20), nullable=False),
        sa.Column('shipping_country', sa.String(100), nullable=False, server_default='US'),
        sa.Column('shipping_phone', sa.String(30), nullable=False),
        sa.Column('idempotency_key', sa.String(100), nullable=True, unique=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('estimated_delivery_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('placed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_orders_order_number', 'orders', ['order_number'])
    op.create_index('ix_orders_user_id', 'orders', ['user_id'])
    op.create_index('ix_orders_status', 'orders', ['status'])
    op.create_index('ix_orders_created_at', 'orders', ['created_at'])

    # ── 8. Order Items ────────────────────────────────────────────────────────
    op.create_table(
        'order_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='SET NULL'), nullable=True),
        sa.Column('variant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True),
        sa.Column('seller_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('variant_label', sa.String(100), nullable=True),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('image_url', sa.String(500), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('line_total', sa.Numeric(10, 2), nullable=False),
        sa.Column('fulfillment_status', sa.String(20), nullable=False, server_default='UNFULFILLED'),
        sa.CheckConstraint('quantity >= 1', name='chk_order_items_quantity'),
    )
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])
    op.create_index('ix_order_items_seller_id', 'order_items', ['seller_id'])

    # ── 9. Order Status History ───────────────────────────────────────────────
    op.create_table(
        'order_status_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_status', sa.String(20), nullable=True),
        sa.Column('to_status', sa.String(20), nullable=False),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_order_status_history_order_id', 'order_status_history', ['order_id'])

    # ── 10. Payments ──────────────────────────────────────────────────────────
    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_ref', sa.String(100), nullable=True),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('card_brand', sa.String(50), nullable=True),
        sa.Column('card_last4', sa.String(4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_payments_order_id', 'payments', ['order_id'])

    # ── 11. Saved Payment Methods ─────────────────────────────────────────────
    op.create_table(
        'saved_payment_methods',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_token', sa.String(255), nullable=False),
        sa.Column('brand', sa.String(50), nullable=False),
        sa.Column('last4', sa.String(4), nullable=False),
        sa.Column('exp_month', sa.Integer(), nullable=False),
        sa.Column('exp_year', sa.Integer(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_saved_payment_methods_user_id', 'saved_payment_methods', ['user_id'])

    # ── 12. Gift Cards & Transactions ─────────────────────────────────────────
    op.create_table(
        'gift_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('pin_hash', sa.String(255), nullable=False),
        sa.Column('initial_balance', sa.Numeric(10, 2), nullable=False),
        sa.Column('balance', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('balance >= 0', name='chk_gift_cards_balance'),
    )
    op.create_index('ix_gift_cards_code', 'gift_cards', ['code'])

    op.create_table(
        'gift_card_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('gift_card_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('gift_cards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('balance_after', sa.Numeric(10, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_gift_card_transactions_gift_card_id', 'gift_card_transactions', ['gift_card_id'])

    # ── 13. Check constraint on product_variants.stock >= 0 ───────────────────
    op.create_check_constraint(
        'chk_product_variants_stock',
        'product_variants',
        'stock >= 0'
    )


def downgrade() -> None:
    op.drop_constraint('chk_product_variants_stock', 'product_variants', type_='check')
    op.drop_table('gift_card_transactions')
    op.drop_table('gift_cards')
    op.drop_table('saved_payment_methods')
    op.drop_table('payments')
    op.drop_table('order_status_history')
    op.drop_table('order_items')
    op.drop_table('orders')
    op.drop_table('delivery_options')
    op.drop_table('addresses')
    op.drop_table('cart_items')
    op.drop_table('carts')
    op.drop_table('promo_redemptions')
    op.drop_table('promo_codes')
    op.drop_table('product_likes')
    op.drop_column('products', 'likes_count')
