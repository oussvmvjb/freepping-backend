import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.v1.schemas.category import CategoryResponse
from app.v1.schemas.product_variant import ProductVariantCreate, ProductVariantResponse


# --- Product Image Schemas ---

class ProductImageBase(BaseModel):
    image_url: str = Field(..., description="Image public URL")
    alt_text: Optional[str] = Field(None, max_length=255, description="Image accessibility alt text")
    sort_order: int = Field(0, description="Display order sequence")
    is_primary: bool = Field(False, description="Whether this is the hero/primary image")


class ProductImageCreate(ProductImageBase):
    pass


class ProductImageResponse(ProductImageBase):
    id: uuid.UUID
    product_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Product Schemas ---

class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Product title")
    slug: str = Field(..., min_length=1, max_length=255, description="Unique product slug")
    description: Optional[str] = Field(None, description="Detailed product description")
    price: Decimal = Field(..., ge=0, description="Selling price")
    compare_price: Optional[Decimal] = Field(None, ge=0, description="Original strike-through price")
    material: Optional[str] = Field(None, max_length=255, description="Fabric or construction material")
    is_active: bool = Field(True, description="Whether product is active and visible")
    is_featured: bool = Field(False, description="Whether product appears in featured showcases")
    category_id: uuid.UUID = Field(..., description="Foreign key to Category")


class ProductCreate(ProductBase):
    images: Optional[List[ProductImageCreate]] = Field(default=[], description="Initial product gallery images")
    variants: Optional[List[ProductVariantCreate]] = Field(default=[], description="Initial product variants (sizes/colors/SKUs)")


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    compare_price: Optional[Decimal] = Field(None, ge=0)
    material: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    category_id: Optional[uuid.UUID] = None


class ProductResponse(ProductBase):
    id: uuid.UUID
    seller_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    category: Optional[CategoryResponse] = None
    images: List[ProductImageResponse] = []
    variants: List[ProductVariantResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    page: int
    page_size: int
    total: int
    pages: int
