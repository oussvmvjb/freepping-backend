import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product_variant import ProductVariant
from app.v1.schemas.product_variant import ProductVariantCreate, ProductVariantUpdate


class ProductVariantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, variant_id: uuid.UUID) -> Optional[ProductVariant]:
        stmt = select(ProductVariant).where(ProductVariant.id == variant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_sku(self, sku: str) -> Optional[ProductVariant]:
        stmt = select(ProductVariant).where(ProductVariant.sku == sku)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_product_id(self, product_id: uuid.UUID) -> List[ProductVariant]:
        stmt = (
            select(ProductVariant)
            .where(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.sku.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, product_id: uuid.UUID, variant_in: ProductVariantCreate) -> ProductVariant:
        variant = ProductVariant(
            product_id=product_id,
            size=variant_in.size,
            color=variant_in.color,
            sku=variant_in.sku,
            stock=variant_in.stock,
            price=variant_in.price,
            is_active=variant_in.is_active,
        )
        self.session.add(variant)
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    async def update(self, variant: ProductVariant, variant_in: ProductVariantUpdate) -> ProductVariant:
        update_data = variant_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(variant, field, value)
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    async def delete(self, variant: ProductVariant) -> None:
        await self.session.delete(variant)
        await self.session.commit()
