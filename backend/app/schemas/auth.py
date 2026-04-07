from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from app.schemas.base import OrmBase


class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    code: str


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    push_token: str | None = None
    push_platform: str | None = None  # "fcm" | "apns"
    timezone: str | None = None


class LinkEmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str
    allow_merge: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserBrief(OrmBase):
    id: UUID
    email: str | None = None
    name: str | None = None
    role: str
    is_new: bool = False
    is_anonymous: bool = False
    is_email_verified: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserTokenResponse(TokenResponse):
    user: UserBrief


class LinkEmailTokenResponse(UserTokenResponse):
    merged: bool = False


class AdminBrief(OrmBase):
    id: UUID
    email: str
    name: str | None


class AdminTokenResponse(TokenResponse):
    admin: AdminBrief


class OTPSentResponse(BaseModel):
    message: str = "OTP код отправлен"
    expires_in_seconds: int = 600
