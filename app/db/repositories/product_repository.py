import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.category import Category
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.models.product_variant import ProductVariant
from app.v1.schemas.product import ProductCreate, ProductUpdate


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, product_id: uuid.UUID) -> Optional[Product]:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
                selectinload(Product.variants),
            )
            .where(Product.id == product_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Product]:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
                selectinload(Product.variants),
            )
            .where(Product.slug == slug)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        category_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
        is_featured: Optional[bool] = None,
        is_active_only: bool = True,
        seller_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[Product], int]:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.images),
                selectinload(Product.variants),
            )
        )

        if is_active_only:
            stmt = stmt.where(Product.is_active == True)

        if category_id:
            stmt = stmt.where(Product.category_id == category_id)

        if is_featured is not None:
            stmt = stmt.where(Product.is_featured == is_featured)

        if seller_id is not None:
            stmt = stmt.where(Product.seller_id == seller_id)

        if search:
            search_term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(search_term),
                    Product.description.ilike(search_term),
                    Product.material.ilike(search_term),
                )
            )

        # Count total matching products
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count_result = await self.session.execute(count_stmt)
        total = total_count_result.scalar_one()

        # Apply ordering and pagination
        stmt = stmt.order_by(Product.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create(
        self,
        product_in: ProductCreate,
        seller_id: Optional[uuid.UUID] = None
    ) -> Product:
        product = Product(
            category_id=product_in.category_id,
            seller_id=seller_id,
            name=product_in.name,
            slug=product_in.slug,
            description=product_in.description,
            price=product_in.price,
            compare_price=product_in.compare_price,
            material=product_in.material,
            is_active=product_in.is_active,
            is_featured=product_in.is_featured,
        )

        if product_in.images:
            for img in product_in.images:
                product.images.append(
                    ProductImage(
                        image_url=img.image_url,
                        alt_text=img.alt_text,
                        sort_order=img.sort_order,
                        is_primary=img.is_primary,
                    )
                )

        if product_in.variants:
            for var in product_in.variants:
                product.variants.append(
                    ProductVariant(
                        size=var.size,
                        color=var.color,
                        sku=var.sku,
                        stock=var.stock,
                        price=var.price,
                        is_active=var.is_active,
                    )
                )

        self.session.add(product)
        await self.session.commit()
        return await self.get_by_id(product.id)  # Returns fully loaded product

    async def update(self, product: Product, product_in: ProductUpdate) -> Product:
        update_data = product_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(product, field, value)

        await self.session.commit()
        return await self.get_by_id(product.id)

    async def delete(self, product: Product) -> None:
        await self.session.delete(product)
        await self.session.commit()
