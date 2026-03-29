import datetime as dt
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OfflinePaymentMethod, UUIDMixin


class OfflinePayment(Base, UUIDMixin):
    __tablename__ = "offline_payments"
    __table_args__ = (
        CheckConstraint("amount_kopecks > 0", name="ck_offline_payments_amount"),
        Index("idx_offline_payments_campaign", "campaign_id"),
        Index("idx_offline_payments_dedup",
              "campaign_id", "payment_date", "amount_kopecks", "external_reference",
              unique=True,
              postgresql_where="external_reference IS NOT NULL"),
    )

    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False,
    )
    amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[OfflinePaymentMethod] = mapped_column(
        SAEnum(OfflinePaymentMethod, name="offline_payment_method", create_type=True),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    external_reference: Mapped[str | None] = mapped_column(String)
    recorded_by_admin_id: Mapped[UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False,
    )
    payment_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
