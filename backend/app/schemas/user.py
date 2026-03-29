from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr
from app.schemas.base import OrmBase


class NotificationPreferences(BaseModel):
    push_on_payment: bool = True
    push_on_campaign_change: bool = True
    push_daily_streak: bool = False
    push_campaign_completed: bool = True


class UserProfileResponse(OrmBase):
    id: UUID
    email: str
    phone: str | None
    name: str | None
    avatar_url: str | None
    role: str
    timezone: str
    notification_preferences: NotificationPreferences
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    timezone: str | None = None
    push_token: str | None = None
    push_platform: str | None = None


class UpdateNotificationsRequest(BaseModel):
    push_on_payment: bool | None = None
    push_on_campaign_change: bool | None = None
    push_daily_streak: bool | None = None
    push_campaign_completed: bool | None = None


# --- Admin schemas ---

class AdminUserListItem(OrmBase):
    id: UUID
    email: str
    phone: str | None = None
    name: str | None
    avatar_url: str | None = None
    role: str
    is_active: bool
    current_streak_days: int
    total_donated_kopecks: int
    total_donations_count: int
    created_at: datetime
    updated_at: datetime


class AdminUserSubscriptionBrief(OrmBase):
    id: UUID
    amount_kopecks: int
    billing_period: str
    allocation_strategy: str
    campaign_id: UUID | None = None
    foundation_id: UUID | None = None
    status: str
    next_billing_at: datetime | None
    created_at: datetime


class AdminUserDonationBrief(OrmBase):
    id: UUID
    campaign_id: UUID
    amount_kopecks: int
    status: str
    source: str
    created_at: datetime


class UserRoleResponse(BaseModel):
    id: UUID
    email: str
    role: str


class UserActiveResponse(BaseModel):
    id: UUID
    email: str
    is_active: bool
