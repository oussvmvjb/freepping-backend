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


class UserProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100, description="User first name")
    last_name: Optional[str] = Field(None, max_length=100, description="User last name")


class UserChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=6, description="Current account password")
    new_password: str = Field(..., min_length=6, description="New account password")

