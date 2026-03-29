from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class AchievementAdminResponse(OrmBase):
    id: UUID
    code: str
    title: str
    description: str | None
    icon_url: str | None
    condition_type: str
    condition_value: int
    is_active: bool
    created_at: datetime


class AchievementCreateRequest(BaseModel):
    code: str
    title: str
    description: str | None = None
    icon_url: str | None = None
    condition_type: str  # streak_days, total_amount_kopecks, donations_count
    condition_value: int


class AchievementUpdateRequest(BaseModel):
    code: str | None = None
    title: str | None = None
    description: str | None = None
    icon_url: str | None = None
    condition_type: str | None = None
    condition_value: int | None = None
    is_active: bool | None = None
