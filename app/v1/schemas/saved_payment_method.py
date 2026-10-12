import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SavedPaymentMethodResponse(BaseModel):
    id: uuid.UUID
    brand: str = Field(..., description="Card network brand, e.g. Visa, Mastercard")
    last4: str = Field(..., description="Last 4 digits of the card")
    exp_month: int = Field(..., description="Card expiry month")
    exp_year: int = Field(..., description="Card expiry year")
    is_default: bool = Field(..., description="Whether this is the user default payment method")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
