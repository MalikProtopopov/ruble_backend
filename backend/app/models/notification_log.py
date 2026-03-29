from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, desc, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, NotificationStatus, UUIDMixin


class NotificationLog(Base, UUIDMixin):
    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("idx_notification_logs_user", "user_id", desc("created_at")),
        Index("idx_notification_logs_type", "notification_type", desc("created_at")),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    push_token: Mapped[str | None] = mapped_column(String)
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notification_status", create_type=True),
        nullable=False,
    )
    provider_response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
