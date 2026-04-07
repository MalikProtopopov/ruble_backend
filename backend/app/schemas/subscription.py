from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class CreateSubscriptionRequest(BaseModel):
    amount_kopecks: int  # 100, 300, 500, 1000
    billing_period: str  # weekly, monthly
    allocation_strategy: str  # platform_pool, foundation_pool, specific_campaign
    campaign_id: UUID | None = None
    foundation_id: UUID | None = None


class UpdateSubscriptionRequest(BaseModel):
    amount_kopecks: int | None = None
    allocation_strategy: str | None = None
    campaign_id: UUID | None = None
    foundation_id: UUID | None = None


class SubscriptionResponse(OrmBase):
    id: UUID
    amount_kopecks: int
    billing_period: str
    allocation_strategy: str
    campaign_id: UUID | None
    campaign_title: str | None = None
    foundation_id: UUID | None
    foundation_name: str | None = None
    status: str
    paused_reason: str | None
    paused_at: datetime | None
    next_billing_at: datetime | None
    created_at: datetime


class ActiveSubscriptionResponse(BaseModel):
    has_active: bool
    subscription: SubscriptionResponse | None = None


class BindCardResponse(BaseModel):
    payment_url: str
    confirmation_type: str = "redirect"
    subscription_id: UUID
    amount_kopecks: int
    description: str
