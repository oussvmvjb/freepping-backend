from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_rate_limit, get_current_active_user
from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.services.gift_card_service import GiftCardService
from app.v1.schemas.gift_card import (
    GiftCardCheckRequest,
    GiftCardCheckResponse,
)

router = APIRouter()


@router.post(
    "/check",
    response_model=GiftCardCheckResponse,
    summary="Check gift card balance",
    description="Validates a gift card number and security PIN, returning its available balance. Rate limited.",
    dependencies=[Depends(check_rate_limit("gift_card_check", settings.RATE_LIMIT_GIFT_CARD_CHECK_PER_MINUTE))],
)
async def check_gift_card(
    payload: GiftCardCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> GiftCardCheckResponse:
    service = GiftCardService(db)
    return await service.check_balance(payload)
