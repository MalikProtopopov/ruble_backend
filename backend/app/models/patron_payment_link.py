from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PatronLinkStatus, UUIDMixin


class PatronPaymentLink(Base, UUIDMixin):
    __tablename__ = "patron_payment_links"
    __table_args__ = (
        Index("idx_patron_links_campaign", "campaign_id", "status"),
        Index("idx_patron_links_user", "created_by_user_id"),
        Index("idx_patron_links_expires", "expires_at",
              postgresql_where="status = 'pending'"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    donation_id: Mapped[UUID] = mapped_column(
        ForeignKey("donations.id", ondelete="RESTRICT"), nullable=False,
    )
    payment_url: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PatronLinkStatus] = mapped_column(
        SAEnum(PatronLinkStatus, name="patron_link_status", create_type=True),
        nullable=False,
        server_default=PatronLinkStatus.pending.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
