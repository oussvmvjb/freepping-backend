from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, require_seller
from app.db.models.user import User
from app.db.session import get_db
from app.services.store_service import StoreService
from app.v1.schemas.store import StoreCreate, StoreResponse, StoreUpdate

router = APIRouter()


@router.post(
    "",
    response_model=StoreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create seller private store",
    description="Creates a new private store for the authenticated SELLER. One store per seller allowed.",
)
async def create_store(
    store_in: StoreCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller),
) -> StoreResponse:
    service = StoreService(db)
    store = await service.create_store(current_user, store_in)
    return StoreResponse.model_validate(store)


@router.get(
    "/me",
    response_model=StoreResponse,
    summary="Get my store",
    description="Returns the authenticated seller's store management data.",
)
async def get_my_store(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller),
) -> StoreResponse:
    service = StoreService(db)
    store = await service.get_my_store(current_user)
    return StoreResponse.model_validate(store)


@router.patch(
    "/me",
    response_model=StoreResponse,
    summary="Update my store",
    description="Updates the authenticated seller's store. Only the store owner may update it.",
)
async def update_my_store(
    store_in: StoreUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller),
) -> StoreResponse:
    service = StoreService(db)
    store = await service.update_my_store(current_user, store_in)
    return StoreResponse.model_validate(store)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate my store",
    description="Soft-deactivates the authenticated seller's store.",
)
async def deactivate_my_store(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_seller),
) -> None:
    service = StoreService(db)
    await service.deactivate_my_store(current_user)


@router.get(
    "/{slug}",
    response_model=StoreResponse,
    summary="Browse public store by slug",
    description="Public endpoint. Returns active store by slug for customers to browse.",
)
async def get_store_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> StoreResponse:
    service = StoreService(db)
    store = await service.get_by_slug(slug)
    return StoreResponse.model_validate(store)
