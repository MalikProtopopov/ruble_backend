from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, desc
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base, DonationSource, DonationStatus, SoftDeleteMixin, TimestampMixin, UUIDMixin,
)


class Donation(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "donations"
    __table_args__ = (
        CheckConstraint("amount_kopecks >= 100", name="ck_donations_min_amount"),
        Index("idx_donations_user", "user_id", desc("created_at")),
        Index("idx_donations_campaign", "campaign_id", "status"),
        Index("idx_donations_idempotence", "idempotence_key", unique=True),
        Index("idx_donations_provider", "provider_payment_id", unique=True,
              postgresql_where="provider_payment_id IS NOT NULL"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False,
    )
    foundation_id: Mapped[UUID] = mapped_column(
        ForeignKey("foundations.id", ondelete="RESTRICT"), nullable=False,
    )
    amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    acquiring_fee_kopecks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    nco_amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String)
    idempotence_key: Mapped[str] = mapped_column(String, nullable=False)
    payment_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[DonationStatus] = mapped_column(
        SAEnum(DonationStatus, name="donation_status", create_type=True),
        nullable=False,
        server_default=DonationStatus.pending.value,
    )
    source: Mapped[DonationSource] = mapped_column(
        SAEnum(DonationSource, name="donation_source", create_type=True),
        nullable=False,
        server_default=DonationSource.app.value,
    )
