from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class ImpactResponse(BaseModel):
    total_donated_kopecks: int
    streak_days: int
    donations_count: int
    streak_includes_skipped: bool = True


class AchievementResponse(OrmBase):
    id: UUID
    code: str
    title: str
    description: str | None
    icon_url: str | None
    earned_at: datetime | None = None
