import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DiscountType


class PromoCodeBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, description="Promo voucher code, converted to uppercase")
    description: Optional[str] = Field(None, description="Human readable description")
    discount_type: DiscountType = Field(..., description="Discount calculation type: PERCENT or FIXED")
    discount_value: Decimal = Field(..., gt=0, description="Percentage or fixed currency amount")
    min_order_amount: Decimal = Field(default=Decimal("0.00"), ge=0, description="Minimum order subtotal to qualify")
    max_discount_amount: Optional[Decimal] = Field(None, ge=0, description="Cap for PERCENT discounts")
    usage_limit: Optional[int] = Field(None, ge=1, description="Total redemption limit across all users")
    per_user_limit: int = Field(default=1, ge=1, description="Maximum redemptions per user account")
    starts_at: Optional[datetime] = Field(None, description="Start date/time of validity")
    expires_at: Optional[datetime] = Field(None, description="Expiry date/time")
    is_active: bool = Field(True, description="Whether promo code is active")


class PromoCodeCreate(PromoCodeBase):
    pass


class PromoCodeUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = Field(None, gt=0)
    min_order_amount: Optional[Decimal] = Field(None, ge=0)
    max_discount_amount: Optional[Decimal] = Field(None, ge=0)
    usage_limit: Optional[int] = Field(None, ge=1)
    per_user_limit: Optional[int] = Field(None, ge=1)
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class PromoCodeResponse(PromoCodeBase):
    id: uuid.UUID
    used_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PromoCodeListResponse(BaseModel):
    items: List[PromoCodeResponse]
    page: int
    page_size: int
    total: int
    pages: int


class PromoValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Promo code to validate against current user cart")


class PromoValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_type: str
    discount_value: str
    discount_amount: str
    subtotal: str
    new_subtotal: str
    message: Optional[str] = None
