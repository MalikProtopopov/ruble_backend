from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CampaignDonor(Base):
    __tablename__ = "campaign_donors"
    __table_args__ = (
        PrimaryKeyConstraint("campaign_id", "user_id"),
        Index("idx_campaign_donors_user", "user_id"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    first_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
