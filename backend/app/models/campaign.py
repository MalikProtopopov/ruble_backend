from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, desc, func,
)
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CampaignStatus, ThanksContentType, TimestampMixin, UUIDMixin


class Campaign(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("urgency_level >= 1 AND urgency_level <= 5", name="ck_campaigns_urgency"),
        Index("idx_campaigns_feed",
              desc("urgency_level"), "sort_order", "status",
              postgresql_where="status = 'active'"),
        Index("idx_campaigns_foundation", "foundation_id"),
        Index("idx_campaigns_ends_at", "ends_at",
              postgresql_where="ends_at IS NOT NULL AND status = 'active' AND is_permanent = false"),
    )

    foundation_id: Mapped[UUID] = mapped_column(
        ForeignKey("foundations.id", ondelete="RESTRICT"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String)
    thumbnail_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus, name="campaign_status", create_type=True),
        nullable=False,
        server_default=CampaignStatus.draft.value,
    )
    goal_amount: Mapped[int | None] = mapped_column(Integer)
    collected_amount: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    donors_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    urgency_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    is_permanent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    closed_early: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    close_note: Mapped[str | None] = mapped_column(Text)

    foundation = relationship("Foundation", back_populates="campaigns", lazy="joined")
    documents = relationship("CampaignDocument", back_populates="campaign", lazy="selectin")
    thanks_contents = relationship("ThanksContent", back_populates="campaign", lazy="selectin")


class CampaignDocument(Base, UUIDMixin):
    __tablename__ = "campaign_documents"
    __table_args__ = (
        Index("idx_campaign_documents_campaign", "campaign_id", "sort_order"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    campaign = relationship("Campaign", back_populates="documents")


class ThanksContent(Base, UUIDMixin):
    __tablename__ = "thanks_contents"
    __table_args__ = (
        Index("idx_thanks_contents_campaign", "campaign_id"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False,
    )
    type: Mapped[ThanksContentType] = mapped_column(
        SAEnum(ThanksContentType, name="thanks_content_type", create_type=True),
        nullable=False,
    )
    media_url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    campaign = relationship("Campaign", back_populates="thanks_contents")
