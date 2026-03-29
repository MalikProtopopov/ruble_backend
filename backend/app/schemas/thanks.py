from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class UserContribution(BaseModel):
    total_donated_kopecks: int
    donations_count: int
    first_donation_at: datetime | None = None
    last_donation_at: datetime | None = None


class ThanksResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_title: str
    foundation_id: UUID
    foundation_name: str
    type: str
    media_url: str
    title: str | None
    description: str | None
    user_contribution: UserContribution


class UnseenThanksItem(BaseModel):
    id: UUID
    campaign_id: UUID
    campaign_title: str
    foundation_name: str
    type: str
    media_url: str
    title: str | None
    description: str | None
    user_contribution: UserContribution
    created_at: datetime
