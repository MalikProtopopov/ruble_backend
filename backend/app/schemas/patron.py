from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class CreatePaymentLinkRequest(BaseModel):
    campaign_id: UUID
    amount_kopecks: int


class PaymentLinkResponse(OrmBase):
    id: UUID
    campaign_id: UUID
    campaign_title: str | None = None
    amount_kopecks: int
    payment_url: str
    expires_at: datetime
    status: str
    created_at: datetime
