from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_rate_limit, get_current_active_user
from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.services.promo_service import PromoService
from app.v1.schemas.promo_code import (
    PromoCodeResponse,
    PromoValidateRequest,
    PromoValidateResponse,
)

router = APIRouter()


@router.post(
    "/validate",
    response_model=PromoValidateResponse,
    summary="Validate promo code",
    description="Validates a promo code against current user cart and returns expected discount breakdown.",
    dependencies=[Depends(check_rate_limit("promo_validate", settings.RATE_LIMIT_PROMO_VALIDATE_PER_MINUTE))],
)
async def validate_promo(
    validate_in: PromoValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PromoValidateResponse:
    service = PromoService(db)
    return await service.validate_for_cart(current_user, validate_in.code)


@router.get(
    "/active",
    response_model=List[PromoCodeResponse],
    summary="Get active public offers",
    description="Public endpoint. Returns currently active and unexpired promo codes for the promotional banner.",
)
async def get_active_promos(
    db: AsyncSession = Depends(get_db),
) -> List[PromoCodeResponse]:
    service = PromoService(db)
    return await service.list_active_promos()
