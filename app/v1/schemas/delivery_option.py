import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeliveryOptionBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, description="Unique code, e.g. STANDARD, EXPRESS")
    title: str = Field(..., min_length=1, max_length=100, description="Display title")
    description: Optional[str] = Field(None, description="Detailed shipping description")
    badge: Optional[str] = Field(None, max_length=50, description="Badge text, e.g. Free, Popular")
    icon: Optional[str] = Field(None, max_length=50, description="Icon identifier")
    price: Decimal = Field(default=Decimal("0.00"), ge=0, description="Shipping price")
    estimated_days_min: Optional[int] = Field(None, ge=0, description="Minimum estimated transit days")
    estimated_days_max: Optional[int] = Field(None, ge=0, description="Maximum estimated transit days")
    estimated_label: Optional[str] = Field(None, max_length=100, description="Human friendly transit time e.g. '2-3 days'")
    is_active: bool = Field(default=True, description="Whether delivery option is selectable")
    sort_order: int = Field(default=0, description="Display sequence order")


class DeliveryOptionCreate(DeliveryOptionBase):
    pass


class DeliveryOptionUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    badge: Optional[str] = Field(None, max_length=50)
    icon: Optional[str] = Field(None, max_length=50)
    price: Optional[Decimal] = Field(None, ge=0)
    estimated_days_min: Optional[int] = Field(None, ge=0)
    estimated_days_max: Optional[int] = Field(None, ge=0)
    estimated_label: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class DeliveryOptionResponse(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    description: Optional[str] = None
    badge: Optional[str] = None
    icon: Optional[str] = None
    price: str = Field(..., description="Delivery price as decimal string")
    estimated_days_min: Optional[int] = None
    estimated_days_max: Optional[int] = None
    estimated_label: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("price", mode="before")
    @classmethod
    def convert_price_to_str(cls, v):
        if isinstance(v, Decimal):
            return f"{v:.2f}"
        if v is not None:
            return str(v)
        return v
