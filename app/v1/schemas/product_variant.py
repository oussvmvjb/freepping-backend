import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ProductVariantBase(BaseModel):
    size: Optional[str] = Field(None, max_length=50, description="Size, e.g. S, M, L, XL, 32")
    color: Optional[str] = Field(None, max_length=100, description="Color name or hex code")
    sku: str = Field(..., min_length=1, max_length=100, description="Unique Stock Keeping Unit")
    stock: int = Field(0, ge=0, description="Available inventory quantity")
    price: Optional[Decimal] = Field(None, ge=0, description="Optional override price; if null uses product base price")
    is_active: bool = Field(True, description="Whether variant is available for purchase")


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    size: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=100)
    sku: Optional[str] = Field(None, min_length=1, max_length=100)
    stock: Optional[int] = Field(None, ge=0)
    price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ProductVariantResponse(ProductVariantBase):
    id: uuid.UUID
    product_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
