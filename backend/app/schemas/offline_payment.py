from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class OfflinePaymentCreate(BaseModel):
    amount_kopecks: int
    payment_method: str  # cash, bank_transfer, other
    description: str | None = None
    external_reference: str | None = None
    payment_date: date


class OfflinePaymentResponse(OrmBase):
    id: UUID
    campaign_id: UUID
    amount_kopecks: int
    payment_method: str
    description: str | None
    external_reference: str | None
    payment_date: date
    recorded_by_admin_id: UUID
    created_at: datetime
