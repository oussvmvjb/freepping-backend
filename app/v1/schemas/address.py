import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AddressType


class AddressBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Recipient full name")
    street: str = Field(..., min_length=1, max_length=255, description="Street address including apt/suite")
    city: str = Field(..., min_length=1, max_length=100, description="City")
    state: str = Field(..., min_length=1, max_length=100, description="State or province")
    zip: str = Field(..., min_length=1, max_length=20, description="Postal / ZIP code")
    country: str = Field(default="US", min_length=2, max_length=100, description="Country")
    phone: str = Field(..., min_length=3, max_length=30, description="Contact phone number")
    type: AddressType = Field(default=AddressType.HOME, description="Address type: home, office, other")
    is_default: bool = Field(default=False, description="Whether this is the user default address")


class AddressCreate(AddressBase):
    pass


class AddressUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    street: Optional[str] = Field(None, min_length=1, max_length=255)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=1, max_length=100)
    zip: Optional[str] = Field(None, min_length=1, max_length=20)
    country: Optional[str] = Field(None, min_length=2, max_length=100)
    phone: Optional[str] = Field(None, min_length=3, max_length=30)
    type: Optional[AddressType] = None
    is_default: Optional[bool] = None


class AddressResponse(AddressBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
