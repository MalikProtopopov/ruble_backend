from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.schemas.base import OrmBase


class FoundationBrief(OrmBase):
    id: UUID
    name: str
    logo_url: str | None


class FoundationBriefWithUrl(FoundationBrief):
    website_url: str | None


class CampaignDocumentResponse(OrmBase):
    id: UUID
    title: str
    file_url: str
    sort_order: int


class ThanksContentBrief(OrmBase):
    id: UUID
    type: str
    media_url: str
    title: str | None
    description: str | None


class LastDonationBrief(OrmBase):
    id: UUID
    amount_kopecks: int
    created_at: datetime
    status: str


class CampaignListItem(OrmBase):
    id: UUID
    foundation_id: UUID
    foundation: FoundationBrief | None = None
    title: str
    description: str | None
    thumbnail_url: str | None
    status: str
    goal_amount: int | None
    collected_amount: int
    donors_count: int
    urgency_level: int
    is_permanent: bool
    ends_at: datetime | None
    created_at: datetime
    # User-specific fields (null for guests / anonymous tokens)
    donated_today: bool | None = None
    has_any_donation: bool | None = None
    last_donation: LastDonationBrief | None = None
    next_available_at: datetime | None = None


class CampaignDetailResponse(CampaignListItem):
    video_url: str | None
    closed_early: bool
    close_note: str | None
    documents: list[CampaignDocumentResponse] = []
    thanks_contents: list[ThanksContentBrief] = []
    cooldown_hours: int = 0


class ShareResponse(BaseModel):
    share_url: str
    title: str
    description: str


# --- Admin schemas ---

class AdminCampaignCreate(BaseModel):
    foundation_id: UUID
    title: str
    description: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    goal_amount: int | None = None
    urgency_level: int = 3
    is_permanent: bool = False
    ends_at: datetime | None = None
    sort_order: int = 0


class AdminCampaignUpdate(BaseModel):
    foundation_id: UUID | None = None
    title: str | None = None
    description: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    video_media_asset_id: UUID | None = None
    thumbnail_media_asset_id: UUID | None = None
    goal_amount: int | None = None
    urgency_level: int | None = None
    is_permanent: bool | None = None
    ends_at: datetime | None = None
    sort_order: int | None = None


class AdminCampaignResponse(OrmBase):
    id: UUID
    foundation_id: UUID
    foundation_name: str | None = None
    title: str
    description: str | None
    video_url: str | None
    thumbnail_url: str | None
    status: str
    goal_amount: int | None
    collected_amount: int
    donors_count: int
    urgency_level: int
    is_permanent: bool
    ends_at: datetime | None
    sort_order: int
    closed_early: bool
    close_note: str | None
    created_at: datetime
    updated_at: datetime


class AdminCampaignDetailResponse(AdminCampaignResponse):
    documents: list[CampaignDocumentResponse] = []
    thanks_contents: list[ThanksContentBrief] = []


class CloseEarlyRequest(BaseModel):
    close_note: str


class ForceReallocResponse(BaseModel):
    reallocated_subscriptions: int


class CampaignDocumentCreate(BaseModel):
    title: str
    file_url: str
    sort_order: int = 0


class ThanksContentCreate(BaseModel):
    type: str  # video, audio
    media_url: str
    title: str | None = None
    description: str | None = None


class ThanksContentUpdate(BaseModel):
    type: str | None = None
    media_url: str | None = None
    title: str | None = None
    description: str | None = None
