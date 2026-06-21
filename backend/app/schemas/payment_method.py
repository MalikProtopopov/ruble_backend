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


class CardSaveRequest(BaseModel):
    """Optional body for POST /payment-methods.

    Mobile SDK flow: pass `payment_token` from the YooKassa SDK (tokenize a card
    with savePaymentMethod). When omitted, the redirect flow is used and a
    `payment_url` is returned instead.
    """

    payment_token: str | None = None


class CardSaveResponse(BaseModel):
    """Response for POST /payment-methods — kicks off card binding via YooKassa.

    Redirect flow: the client opens `payment_url`, the user confirms a nominal 1₽
    charge. SDK flow (payment_token): `payment_url` is null (or a 3DS URL the SDK
    handles). Either way the card is persisted on `payment.succeeded` and the
    charge is refunded; the saved method then appears in GET /payment-methods.
    """

    payment_url: str | None = None
    confirmation_type: str = "redirect"
    amount_kopecks: int


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
