from datetime import datetime
from uuid import UUID
from app.schemas.base import OrmBase


class TransactionListItem(OrmBase):
    id: UUID
    subscription_id: UUID
    campaign_id: UUID | None
    campaign_title: str | None = None
    campaign_status: str | None = None
    campaign_thumbnail_url: str | None = None
    foundation_name: str | None = None
    amount_kopecks: int
    status: str
    skipped_reason: str | None
    created_at: datetime


class TransactionDetailResponse(OrmBase):
    id: UUID
    subscription_id: UUID
    campaign_id: UUID | None
    campaign_title: str | None = None
    campaign_status: str | None = None
    campaign_thumbnail_url: str | None = None
    foundation_id: UUID | None
    foundation_name: str | None = None
    foundation_logo_url: str | None = None
    amount_kopecks: int
    platform_fee_kopecks: int
    nco_amount_kopecks: int
    status: str
    skipped_reason: str | None
    cancellation_reason: str | None
    attempt_number: int
    next_retry_at: datetime | None = None
    created_at: datetime
