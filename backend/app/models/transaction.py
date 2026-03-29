from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, desc
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base, SkipReason, TimestampMixin, TransactionStatus, UUIDMixin,
)


class Transaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_subscription", "subscription_id", desc("created_at")),
        Index("idx_transactions_retry", "next_retry_at", "status",
              postgresql_where="status = 'failed' AND next_retry_at IS NOT NULL"),
        Index("idx_transactions_idempotence", "idempotence_key", unique=True),
        Index("idx_transactions_provider", "provider_payment_id", unique=True,
              postgresql_where="provider_payment_id IS NOT NULL"),
        Index("idx_transactions_campaign", "campaign_id", "status",
              postgresql_where="status = 'success'"),
        Index("idx_transactions_foundation", "foundation_id", "status"),
    )

    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False,
    )
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"),
    )
    foundation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("foundations.id", ondelete="SET NULL"),
    )
    amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    nco_amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    acquiring_fee_kopecks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    provider_payment_id: Mapped[str | None] = mapped_column(String)
    idempotence_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status", create_type=True),
        nullable=False,
        server_default=TransactionStatus.pending.value,
    )
    skipped_reason: Mapped[SkipReason | None] = mapped_column(
        SAEnum(SkipReason, name="skip_reason", create_type=True),
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subscription = relationship("Subscription", back_populates="transactions")
