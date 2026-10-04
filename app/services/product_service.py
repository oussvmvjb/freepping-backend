import hashlib
import math
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.core.exceptions import (
    AuthorizationException,
    DuplicateResourceException,
    ResourceNotFoundException,
)
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories.category_repository import CategoryRepository
from app.db.repositories.product_repository import ProductRepository
from app.db.repositories.product_variant_repository import ProductVariantRepository
from app.services.redis.redis_client import redis_client
from app.v1.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)


class ProductService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ProductRepository(session)
        self.category_repo = CategoryRepository(session)
        self.variant_repo = ProductVariantRepository(session)

    def _generate_list_cache_key(
        self,
        page: int,
        page_size: int,
        category_id: Optional[uuid.UUID],
        search: Optional[str],
        is_featured: Optional[bool],
        seller_id: Optional[uuid.UUID] = None,
    ) -> str:
        key_raw = f"{page}:{page_size}:{category_id}:{search}:{is_featured}:{seller_id}"
        hash_val = hashlib.md5(key_raw.encode("utf-8")).hexdigest()
        return f"products:list:{hash_val}"

    async def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        category_id: Optional[uuid.UUID] = None,
        search: Optional[str] = None,
        is_featured: Optional[bool] = None,
        seller_id: Optional[uuid.UUID] = None,
    ) -> ProductListResponse:
        cache_key = self._generate_list_cache_key(page, page_size, category_id, search, is_featured, seller_id)
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return ProductListResponse.model_validate(cached)

        items, total = await self.repository.list_products(
            page=page,
            page_size=page_size,
            category_id=category_id,
            search=search,
            is_featured=is_featured,
            is_active_only=True,
            seller_id=seller_id,
        )

        pages = math.ceil(total / page_size) if total > 0 else 0
        response = ProductListResponse(
            items=[ProductResponse.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

        await redis_client.set(
            cache_key,
            response.model_dump(),
            ttl=settings.CACHE_TTL_PRODUCT_LIST
        )
        return response

    async def list_my_products(
        self,
        current_user: User,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductListResponse:
        """Returns paginated products owned by the authenticated seller."""
        items, total = await self.repository.list_products(
            page=page,
            page_size=page_size,
            is_active_only=False,  # Sellers can see their own inactive products
            seller_id=current_user.id,
        )

        pages = math.ceil(total / page_size) if total > 0 else 0
        return ProductListResponse(
            items=[ProductResponse.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages,
        )

    async def get_product(self, product_id: uuid.UUID) -> ProductResponse:
        cache_key = f"products:{product_id}"
        cached = await redis_client.get(cache_key)
        if cached is not None:
            return ProductResponse.model_validate(cached)

        product = await self.repository.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        response = ProductResponse.model_validate(product)
        await redis_client.set(
            cache_key,
            response.model_dump(),
            ttl=settings.CACHE_TTL_PRODUCT_DETAIL
        )
        return response

    async def create_product(
        self,
        product_in: ProductCreate,
        current_user: User,
    ) -> ProductResponse:
        # Check category existence
        category = await self.category_repo.get_by_id(product_in.category_id)
        if not category:
            raise ResourceNotFoundException("Category", product_in.category_id)

        # Check slug uniqueness
        existing_slug = await self.repository.get_by_slug(product_in.slug)
        if existing_slug:
            raise DuplicateResourceException(f"Product with slug '{product_in.slug}' already exists.")

        # Check SKU uniqueness if initial variants are provided
        if product_in.variants:
            for variant in product_in.variants:
                existing_sku = await self.variant_repo.get_by_sku(variant.sku)
                if existing_sku:
                    raise DuplicateResourceException(f"Product variant with SKU '{variant.sku}' already exists.")

        # Determine seller_id
        # For SELLER: always assign current_user.id
        # For ADMIN / SUPER_ADMIN: platform products have seller_id = None
        seller_id = current_user.id if current_user.role == UserRole.SELLER else None

        product = await self.repository.create(product_in, seller_id=seller_id)
        await redis_client.invalidate_product_caches()
        return ProductResponse.model_validate(product)

    def verify_ownership(self, product: Product, current_user: User) -> None:
        """Verifies that the current user has permission to modify/delete the product."""
        if current_user.role in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
            return
        if current_user.role == UserRole.SELLER:
            if product.seller_id != current_user.id:
                raise AuthorizationException("You do not have permission to modify another seller's product.")
            return
        raise AuthorizationException("You do not have permission to modify this product.")

    async def update_product(
        self,
        product_id: uuid.UUID,
        product_in: ProductUpdate,
        current_user: User,
    ) -> ProductResponse:
        product = await self.repository.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        # Enforce seller ownership
        self.verify_ownership(product, current_user)

        if product_in.category_id and product_in.category_id != product.category_id:
            category = await self.category_repo.get_by_id(product_in.category_id)
            if not category:
                raise ResourceNotFoundException("Category", product_in.category_id)

        if product_in.slug and product_in.slug != product.slug:
            existing_slug = await self.repository.get_by_slug(product_in.slug)
            if existing_slug:
                raise DuplicateResourceException(f"Product with slug '{product_in.slug}' already exists.")

        updated = await self.repository.update(product, product_in)
        await redis_client.invalidate_product_caches(str(product_id))
        return ProductResponse.model_validate(updated)

    async def delete_product(self, product_id: uuid.UUID, current_user: User) -> None:
        product = await self.repository.get_by_id(product_id)
        if not product:
            raise ResourceNotFoundException("Product", product_id)

        # Enforce seller ownership
        self.verify_ownership(product, current_user)

        await self.repository.delete(product)
        await redis_client.invalidate_product_caches(str(product_id))
