import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.models.user import User
from app.db.session import get_db
from app.services.category_service import CategoryService
from app.v1.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter()


@router.get(
    "",
    response_model=List[CategoryResponse],
    summary="List categories",
    description="Public endpoint. Retrieve all active product categories. Result is cached in Redis.",
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
) -> List[CategoryResponse]:
    service = CategoryService(db)
    return await service.list_categories()


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get category by ID",
    description="Public endpoint. Retrieve category details by its UUID.",
)
async def get_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    service = CategoryService(db)
    return await service.get_category(category_id)


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create category",
    description="Create a new product category. Requires ADMIN or SUPER_ADMIN.",
)
async def create_category(
    category_in: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CategoryResponse:
    service = CategoryService(db)
    return await service.create_category(category_in)


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update category",
    description="Partially update an existing category. Requires ADMIN or SUPER_ADMIN.",
)
async def update_category(
    category_id: uuid.UUID,
    category_in: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CategoryResponse:
    service = CategoryService(db)
    return await service.update_category(category_id, category_in)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete category",
    description="Delete a category by UUID. Requires ADMIN or SUPER_ADMIN.",
)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    service = CategoryService(db)
    await service.delete_category(category_id)
