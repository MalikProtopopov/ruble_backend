from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class PayoutCreateRequest(BaseModel):
    foundation_id: UUID
    amount_kopecks: int
    period_from: date
    period_to: date
    transfer_reference: str | None = None
    note: str | None = None


class PayoutResponse(OrmBase):
    id: UUID
    foundation_id: UUID
    foundation_name: str | None = None
    amount_kopecks: int
    period_from: date
    period_to: date
    transfer_reference: str | None
    note: str | None
    created_by_admin_id: UUID
    created_at: datetime


class FoundationBalance(BaseModel):
    foundation_id: UUID
    foundation_name: str
    total_nco_kopecks: int
    total_paid_kopecks: int
    due_kopecks: int
