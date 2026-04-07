from datetime import datetime
from uuid import UUID

from app.schemas.base import OrmBase


class PaymentMethodResponse(OrmBase):
    id: UUID
    provider: str
    card_last4: str | None
    card_type: str | None
    title: str | None
    is_default: bool
    created_at: datetime
