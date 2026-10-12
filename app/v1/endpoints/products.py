from decimal import Decimal
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    check_rate_limit,
    get_current_active_user,
    get_optional_current_user,
    require_seller_or_admin,
)
from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.services.like_service import LikeService
from app.services.product_service import ProductService
from app.v1.schemas.product import (
    ProductCreate,
    ProductLikeToggleResponse,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)

router = APIRouter()


@router.get(
    "",
    response_model=ProductListResponse,
    summary="List products",
    description="Public endpoint with optional auth. Retrieve paginated products with filtering and sorting.",
)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filter by Category UUID"),
    search: Optional[str] = Query(None, description="Search term across name and description"),
    is_featured: Optional[bool] = Query(None, description="Filter by featured status"),
    sort: str = Query("newest", description="Sorting order: newest, price_asc, price_desc, popular, name_asc"),
    min_price: Optional[Decimal] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[Decimal] = Query(None, ge=0, description="Maximum price filter"),
    in_stock_only: bool = Query(False, description="Filter only products with active stock > 0"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> ProductListResponse:
    service = ProductService(db)
    return await service.list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        search=search,
        is_featured=is_featured,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        current_user=current_user,
    )


@router.get(
    "/my",
    response_model=ProductListResponse,
    summary="List my products (seller)",
    description="Returns all products owned by the authenticated seller, including inactive ones.",
)
async def list_my_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller_or_admin),
) -> ProductListResponse:
    service = ProductService(db)
    return await service.list_my_products(current_user, page=page, page_size=page_size)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get product by ID",
    description="Public endpoint with optional auth. Retrieve full product details.",
)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> ProductResponse:
    service = ProductService(db)
    return await service.get_product(product_id, current_user=current_user)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
    description=(
        "Requires SELLER, ADMIN, or SUPER_ADMIN. "
        "SELLER products automatically get seller_id = authenticated user. "
        "ADMIN/SUPER_ADMIN products are platform-managed (seller_id=NULL)."
    ),
)
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller_or_admin),
) -> ProductResponse:
    service = ProductService(db)
    return await service.create_product(product_in, current_user)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update product",
    description=(
        "ADMIN/SUPER_ADMIN may update any product. "
        "SELLER may only update their own products."
    ),
)
async def update_product(
    product_id: uuid.UUID,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller_or_admin),
) -> ProductResponse:
    service = ProductService(db)
    return await service.update_product(product_id, product_in, current_user)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete product",
    description=(
        "ADMIN/SUPER_ADMIN may delete any product. "
        "SELLER may only delete their own products."
    ),
)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller_or_admin),
) -> None:
    service = ProductService(db)
    await service.delete_product(product_id, current_user)


# ── Product Likes (Part 1) ───────────────────────────────────────────────────

@router.post(
    "/{product_id}/like",
    response_model=ProductLikeToggleResponse,
    tags=["Likes"],
    summary="Like product",
    description="Idempotent: adds product to user favorites and increments likes count.",
    dependencies=[Depends(check_rate_limit("like_toggle", settings.RATE_LIMIT_LIKE_PER_MINUTE))],
)
async def like_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProductLikeToggleResponse:
    service = LikeService(db)
    return await service.like_product(product_id, current_user)


@router.delete(
    "/{product_id}/like",
    response_model=ProductLikeToggleResponse,
    tags=["Likes"],
    summary="Unlike product",
    description="Idempotent: removes product from user favorites and decrements likes count.",
    dependencies=[Depends(check_rate_limit("like_toggle", settings.RATE_LIMIT_LIKE_PER_MINUTE))],
)
async def unlike_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProductLikeToggleResponse:
    service = LikeService(db)
    return await service.unlike_product(product_id, current_user)
