from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class PaymentMethod(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A payment method saved by the user (e.g. tokenized card in YooKassa)."""

    __tablename__ = "payment_methods"
    __table_args__ = (
        Index(
            "idx_payment_methods_user",
            "user_id",
            postgresql_where="is_deleted = false",
        ),
        Index(
            "idx_payment_methods_provider",
            "provider",
            "provider_pm_id",
            unique=True,
            postgresql_where="is_deleted = false",
        ),
        Index(
            "idx_payment_methods_fingerprint",
            "card_fingerprint",
            postgresql_where="is_deleted = false AND card_fingerprint IS NOT NULL",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default="yookassa")
    provider_pm_id: Mapped[str] = mapped_column(String(128), nullable=False)
    card_last4: Mapped[str | None] = mapped_column(String(4))
    card_type: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(64))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # SHA-256 of "first6|last4|exp_month|exp_year". Used to detect the same physical
    # card across orphaned anonymous accounts (recovery endpoint).
    card_fingerprint: Mapped[str | None] = mapped_column(String(64))
