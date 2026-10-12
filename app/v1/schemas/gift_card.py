import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class GiftCardCheckRequest(BaseModel):
    number: str = Field(..., min_length=4, max_length=50, description="Gift card code number")
    pin: str = Field(..., min_length=4, max_length=10, description="Gift card security PIN")


class GiftCardCheckResponse(BaseModel):
    code: str
    balance: str = Field(..., description="Available gift card balance")
    currency: str = Field("USD", description="Currency")
    is_active: bool
    expires_at: Optional[datetime] = None


class GiftCardCreateAdmin(BaseModel):
    initial_balance: Decimal = Field(..., gt=0, description="Initial balance loaded on the gift card")
    currency: str = Field(default="USD", max_length=3, description="Currency code")
    expires_at: Optional[datetime] = Field(None, description="Expiration date/time if any")


class GiftCardUpdateAdmin(BaseModel):
    is_active: Optional[bool] = Field(None, description="Activate or deactivate the card")


class GiftCardResponse(BaseModel):
    id: uuid.UUID
    code: str
    initial_balance: str
    balance: str
    currency: str
    is_active: bool
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GiftCardCreatedAdminResponse(GiftCardResponse):
    pin: str = Field(..., description="Plain-text PIN, returned only ONCE at generation time")


class GiftCardListResponse(BaseModel):
    items: List[GiftCardResponse]
    page: int
    page_size: int
    total: int
    pages: int
