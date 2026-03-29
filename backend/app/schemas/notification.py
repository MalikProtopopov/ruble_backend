from datetime import datetime
from uuid import UUID
from app.schemas.base import OrmBase


class NotificationLogResponse(OrmBase):
    id: UUID
    user_id: UUID | None
    push_token: str | None = None
    notification_type: str
    title: str
    body: str
    data: dict | None = None
    status: str
    provider_response: str | None = None
    created_at: datetime
