import datetime as dt
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, desc, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class PayoutRecord(Base, UUIDMixin):
    __tablename__ = "payout_records"
    __table_args__ = (
        CheckConstraint("amount_kopecks > 0", name="ck_payout_records_amount"),
        Index("idx_payout_records_foundation", "foundation_id", desc("created_at")),
    )

    foundation_id: Mapped[UUID] = mapped_column(
        ForeignKey("foundations.id", ondelete="RESTRICT"), nullable=False,
    )
    amount_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)
    period_from: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_to: Mapped[dt.date] = mapped_column(Date, nullable=False)
    transfer_reference: Mapped[str | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)
    created_by_admin_id: Mapped[UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
