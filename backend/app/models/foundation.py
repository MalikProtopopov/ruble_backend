from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, FoundationStatus, TimestampMixin, UUIDMixin


class Foundation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "foundations"
    __table_args__ = (
        Index("idx_foundations_inn", "inn", unique=True),
        Index("idx_foundations_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(500), nullable=False)
    inn: Mapped[str] = mapped_column(String(12), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String)
    website_url: Mapped[str | None] = mapped_column(String)
    status: Mapped[FoundationStatus] = mapped_column(
        SAEnum(FoundationStatus, name="foundation_status", create_type=True),
        nullable=False,
        server_default=FoundationStatus.pending_verification.value,
    )
    yookassa_shop_id: Mapped[str | None] = mapped_column(String)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaigns = relationship("Campaign", back_populates="foundation", lazy="selectin")
