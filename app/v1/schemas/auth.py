from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.v1.schemas.user import UserResponse


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User unique email address")
    password: str = Field(..., min_length=8, description="Password (at least 8 characters)")
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="Account password")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, description="Raw refresh JWT")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, description="Raw refresh JWT to invalidate")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    user: UserResponse
