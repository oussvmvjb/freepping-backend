import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdateRequest(BaseModel):
    role: UserRole = Field(..., description="Target user role")


class UserStatusUpdateRequest(BaseModel):
    is_active: bool = Field(..., description="Whether user account is active")


class UserListResponse(BaseModel):
    items: List[UserResponse]
    total: int
