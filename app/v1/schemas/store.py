import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class StoreBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Store public name")
    slug: str = Field(..., min_length=1, max_length=255, description="Unique store slug for storefront URL")
    description: Optional[str] = Field(None, description="Store description")
    logo_url: Optional[str] = Field(None, description="Logo public image URL")
    banner_url: Optional[str] = Field(None, description="Banner public image URL")


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    is_active: Optional[bool] = None


class StoreResponse(StoreBase):
    id: uuid.UUID
    seller_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
