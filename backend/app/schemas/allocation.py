from datetime import datetime
from uuid import UUID
from app.schemas.base import OrmBase


class AllocationLogResponse(OrmBase):
    id: UUID
    subscription_id: UUID
    from_campaign_id: UUID | None
    from_campaign_title: str | None = None
    to_campaign_id: UUID | None
    to_campaign_title: str | None = None
    reason: str
    notified_at: datetime | None
    created_at: datetime
