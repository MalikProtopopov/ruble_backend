from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr
from app.schemas.base import OrmBase


class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserBrief(OrmBase):
    id: UUID
    email: str
    name: str | None
    role: str
    is_new: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserTokenResponse(TokenResponse):
    user: UserBrief


class AdminBrief(OrmBase):
    id: UUID
    email: str
    name: str | None


class AdminTokenResponse(TokenResponse):
    admin: AdminBrief


class OTPSentResponse(BaseModel):
    message: str = "OTP код отправлен"
    expires_in_seconds: int = 600
