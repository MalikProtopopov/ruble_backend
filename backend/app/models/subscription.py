from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    AllocationStrategy, Base, BillingPeriod, PausedReason,
    SoftDeleteMixin, SubscriptionStatus, TimestampMixin, UUIDMixin,
)


class Subscription(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "amount_kopecks IN (100, 300, 500, 1000)",
            name="ck_subscriptions_amount",
        ),
        Index("idx_subscriptions_billing", "next_billing_at", "status",
              postgresql_where="status = 'active'"),
        Index("idx_subscriptions_user", "user_id", "status"),
        Index("idx_subscriptions_campaign", "campaign_id",
              postgresql_where="campaign_id IS NOT NULL AND status IN ('active', 'paused')"),
        Index("idx_subscriptions_foundation", "foundation_id",
              postgresql_where="foundation_id IS NOT NULL AND status IN ('active', 'paused')"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_period: Mapped[BillingPeriod] = mapped_column(
        SAEnum(BillingPeriod, name="billing_period", create_type=True),
        nullable=False,
    )
    allocation_strategy: Mapped[AllocationStrategy] = mapped_column(
        SAEnum(AllocationStrategy, name="allocation_strategy", create_type=True),
        nullable=False,
    )
    campaign_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"),
    )
    foundation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("foundations.id", ondelete="SET NULL"),
    )
    payment_method_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status", create_type=True),
        nullable=False,
        server_default=SubscriptionStatus.pending_payment_method.value,
    )
    paused_reason: Mapped[PausedReason | None] = mapped_column(
        SAEnum(PausedReason, name="paused_reason", create_type=True),
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_billing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transactions = relationship("Transaction", back_populates="subscription", lazy="dynamic")
