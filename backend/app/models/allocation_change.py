from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, desc, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AllocationChangeReason, Base, UUIDMixin


class AllocationChange(Base, UUIDMixin):
    __tablename__ = "allocation_changes"
    __table_args__ = (
        Index("idx_allocation_changes_subscription", "subscription_id", desc("created_at")),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False,
    )
    from_campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"),
    )
    to_campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"),
    )
    reason: Mapped[AllocationChangeReason] = mapped_column(
        SAEnum(AllocationChangeReason, name="allocation_change_reason", create_type=True),
        nullable=False,
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
