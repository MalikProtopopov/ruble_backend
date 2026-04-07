from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.base import OrmBase


class PaymentMethodResponse(OrmBase):
    id: UUID
    provider: str
    card_last4: str | None
    card_type: str | None
    title: str | None
    is_default: bool
    created_at: datetime


class OrphanedAccountPreview(BaseModel):
    """Preview of an orphaned anonymous account that holds the same physical card.

    Returned by `GET /payment-methods/{pm_id}/orphans` so the mobile app can show
    "we found N rubles of donations and an active subscription on a previous
    installation, restore them?" before triggering the merge.
    """

    user_id: UUID
    donations_count: int
    subscriptions_count: int
    active_subscriptions_count: int
    total_donated_kopecks: int
    last_seen_at: datetime | None


class RecoveryResult(BaseModel):
    """Result of `POST /payment-methods/{pm_id}/recover`."""

    merged_user_ids: list[UUID]
    donations_transferred: int
    subscriptions_transferred: int
    total_donated_kopecks_transferred: int
