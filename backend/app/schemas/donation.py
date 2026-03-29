from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr
from app.schemas.base import OrmBase


class CreateDonationRequest(BaseModel):
    campaign_id: UUID
    amount_kopecks: int
    email: EmailStr | None = None  # Required if no Bearer token


class DonationResponse(OrmBase):
    id: UUID
    campaign_id: UUID
    amount_kopecks: int
    status: str
    source: str
    payment_url: str | None
    created_at: datetime


class DonationListItem(OrmBase):
    id: UUID
    campaign_id: UUID
    campaign_title: str | None = None
    amount_kopecks: int
    status: str
    source: str
    created_at: datetime


class DonationDetailResponse(OrmBase):
    id: UUID
    campaign_id: UUID
    campaign_title: str | None = None
    foundation_id: UUID
    foundation_name: str | None = None
    amount_kopecks: int
    status: str
    source: str
    payment_url: str | None
    created_at: datetime
