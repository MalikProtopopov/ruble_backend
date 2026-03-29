from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ThanksContentShown(Base, UUIDMixin):
    __tablename__ = "thanks_content_shown"
    __table_args__ = (
        UniqueConstraint("user_id", "thanks_content_id", name="idx_thanks_shown_unique"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    thanks_content_id: Mapped[UUID] = mapped_column(
        ForeignKey("thanks_contents.id", ondelete="CASCADE"), nullable=False,
    )
    device_id: Mapped[str | None] = mapped_column(String)
    shown_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
