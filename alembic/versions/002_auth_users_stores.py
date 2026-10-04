"""002_auth_users_stores

Revision ID: 002_auth_users_stores
Revises: 001_initial_tables
Create Date: 2026-10-01 19:05:00.000000

Adds:
- users table with UserRole enum
- refresh_sessions table for secure refresh token tracking
- stores table for seller private stores (1 seller = 1 store)
- products.seller_id FK nullable column
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_auth_users_stores'
down_revision: Union[str, None] = '001_initial_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. UserRole enum type in PostgreSQL
    # ------------------------------------------------------------------
    user_role_enum = postgresql.ENUM(
        'SUPER_ADMIN', 'ADMIN', 'SELLER', 'CUSTOMER',
        name='user_role',
        create_type=True,
    )
    user_role_enum.create(op.get_bind())

    # ------------------------------------------------------------------
    # 2. users table
    # ------------------------------------------------------------------
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('role', sa.String(length=50), server_default='CUSTOMER', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_role', 'users', ['role'], unique=False)
    op.create_index('ix_users_is_active', 'users', ['is_active'], unique=False)

    # ------------------------------------------------------------------
    # 3. refresh_sessions table
    # ------------------------------------------------------------------
    op.create_table(
        'refresh_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'replaced_by_session_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('refresh_sessions.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('ip_address', sa.String(length=100), nullable=True),
    )
    op.create_index('ix_refresh_sessions_user_id', 'refresh_sessions', ['user_id'], unique=False)
    op.create_index('ix_refresh_sessions_token_hash', 'refresh_sessions', ['token_hash'], unique=False)
    op.create_index('ix_refresh_sessions_expires_at', 'refresh_sessions', ['expires_at'], unique=False)

    # ------------------------------------------------------------------
    # 4. stores table
    # ------------------------------------------------------------------
    op.create_table(
        'stores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'seller_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('banner_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_stores_seller_id', 'stores', ['seller_id'], unique=True)
    op.create_index('ix_stores_slug', 'stores', ['slug'], unique=True)
    op.create_index('ix_stores_is_active', 'stores', ['is_active'], unique=False)

    # ------------------------------------------------------------------
    # 5. Add seller_id to products (nullable — existing products = platform-owned)
    # ------------------------------------------------------------------
    op.add_column(
        'products',
        sa.Column(
            'seller_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.create_index('ix_products_seller_id', 'products', ['seller_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_products_seller_id', table_name='products')
    op.drop_column('products', 'seller_id')

    op.drop_table('stores')
    op.drop_table('refresh_sessions')
    op.drop_table('users')

    # Drop the enum type
    user_role_enum = postgresql.ENUM(
        'SUPER_ADMIN', 'ADMIN', 'SELLER', 'CUSTOMER',
        name='user_role',
        create_type=False,
    )
    user_role_enum.drop(op.get_bind())
