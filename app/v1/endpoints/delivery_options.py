from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.delivery_option_service import DeliveryOptionService
from app.v1.schemas.delivery_option import DeliveryOptionResponse

router = APIRouter()


@router.get(
    "",
    response_model=List[DeliveryOptionResponse],
    summary="List active delivery options",
    description="Public endpoint. Returns active shipping methods, cached in Redis.",
)
async def list_delivery_options(
    db: AsyncSession = Depends(get_db),
) -> List[DeliveryOptionResponse]:
    service = DeliveryOptionService(db)
    return await service.list_active()
