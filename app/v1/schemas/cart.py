import uuid
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.v1.schemas.product import ProductResponse
from app.v1.schemas.product_variant import ProductVariantResponse
from app.v1.schemas.promo_code import PromoCodeResponse


class CartItemAdd(BaseModel):
    product_id: uuid.UUID = Field(..., description="Target product ID")
    variant_id: Optional[uuid.UUID] = Field(None, description="Optional variant ID (size/color)")
    quantity: int = Field(default=1, ge=1, description="Quantity to add")


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1, description="New quantity for the cart item")


class CartItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: Optional[uuid.UUID] = None
    quantity: int
    unit_price: str = Field(..., description="Unit price as decimal string")
    line_total: str = Field(..., description="Line total (unit_price * quantity) as decimal string")
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None
    image_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApplyPromoRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Promo code to apply to current cart")


class GiftWrapRequest(BaseModel):
    enabled: bool = Field(..., description="Whether to enable gift wrapping for this cart")


class CartResponse(BaseModel):
    id: uuid.UUID
    has_gift_wrap: bool
    items: List[CartItemResponse] = []
    subtotal: str = Field(..., description="Sum of all item line totals")
    promo_discount: str = Field("0.00", description="Discount from applied promo code")
    gift_wrap_cost: str = Field("0.00", description="Gift wrapping cost")
    delivery_cost: str = Field("0.00", description="Estimated delivery cost (default 0.00 in cart)")
    total: str = Field(..., description="Final payable amount")
    applied_promo: Optional[PromoCodeResponse] = None

    model_config = ConfigDict(from_attributes=True)
