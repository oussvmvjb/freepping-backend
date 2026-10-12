import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    FulfillmentStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from app.v1.schemas.delivery_option import DeliveryOptionResponse
from app.v1.schemas.cart import CartItemResponse


class AddressSnapshot(BaseModel):
    name: str = Field(..., description="Recipient full name")
    street: str = Field(..., description="Street address")
    city: str = Field(..., description="City")
    state: str = Field(..., description="State or province")
    zip: str = Field(..., description="Postal/ZIP code")
    country: str = Field(default="US", description="Country")
    phone: str = Field(..., description="Phone number")


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    product_id: Optional[uuid.UUID] = None
    variant_id: Optional[uuid.UUID] = None
    seller_id: Optional[uuid.UUID] = None
    product_name: str
    variant_label: Optional[str] = None
    sku: Optional[str] = None
    image_url: Optional[str] = None
    unit_price: str
    quantity: int
    line_total: str
    fulfillment_status: Optional[FulfillmentStatus] = None

    model_config = ConfigDict(from_attributes=True)


class OrderStatusHistoryResponse(BaseModel):
    id: uuid.UUID
    from_status: Optional[OrderStatus] = None
    to_status: OrderStatus
    changed_by: Optional[uuid.UUID] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentSummaryResponse(BaseModel):
    id: uuid.UUID
    provider: str
    provider_ref: Optional[str] = None
    amount: str
    currency: str
    status: PaymentStatus
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str
    user_id: uuid.UUID
    status: OrderStatus
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    subtotal: str
    promo_discount: str
    gift_wrap: bool
    gift_wrap_cost: str
    delivery_cost: str
    gift_card_amount_used: str
    total: str
    shipping_address: AddressSnapshot
    tracking_number: Optional[str] = None
    estimated_delivery_at: Optional[datetime] = None
    placed_at: datetime
    paid_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []
    status_history: List[OrderStatusHistoryResponse] = []
    payment: Optional[PaymentSummaryResponse] = None

    model_config = ConfigDict(from_attributes=True)


class OrderListResponse(BaseModel):
    items: List[OrderResponse]
    page: int
    page_size: int
    total: int
    pages: int


class CheckoutPreviewRequest(BaseModel):
    address_id: uuid.UUID = Field(..., description="Selected shipping address ID")
    delivery_option_id: uuid.UUID = Field(..., description="Selected delivery option ID")


class CheckoutPreviewResponse(BaseModel):
    items: List[CartItemResponse]
    subtotal: str
    promo_discount: str
    gift_wrap: bool
    gift_wrap_cost: str
    delivery_option: DeliveryOptionResponse
    delivery_cost: str
    total: str


class GiftCardPaymentInput(BaseModel):
    number: str = Field(..., min_length=4, max_length=50, description="Gift card code number")
    pin: str = Field(..., min_length=4, max_length=10, description="Gift card PIN")


class CheckoutPlaceOrderRequest(BaseModel):
    address_id: uuid.UUID = Field(..., description="Selected shipping address ID")
    delivery_option_id: uuid.UUID = Field(..., description="Selected delivery option ID")
    payment_method: PaymentMethod = Field(..., description="Payment method: CARD, COD, GIFT_CARD")
    payment_token: Optional[str] = Field(None, description="Payment gateway token (for CARD payment)")
    save_card: Optional[bool] = Field(default=False, description="Whether to tokenize and save card for future purchases")
    gift_card: Optional[GiftCardPaymentInput] = Field(None, description="Optional gift card payment details")


class OrderStatusUpdateRequest(BaseModel):
    status: OrderStatus = Field(..., description="Target order status")
    note: Optional[str] = Field(None, description="Optional administrative change note")
    tracking_number: Optional[str] = Field(None, description="Carrier tracking number (when transitioning to SHIPPED)")


class SellerItemStatusUpdateRequest(BaseModel):
    fulfillment_status: FulfillmentStatus = Field(..., description="New fulfillment status for this item")
