from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class RefreshToken(Base, UUIDMixin):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND admin_id IS NULL) OR (user_id IS NULL AND admin_id IS NOT NULL)",
            name="ck_refresh_tokens_owner",
        ),
        Index("idx_refresh_tokens_hash", "token_hash", unique=True),
        Index("idx_refresh_tokens_user", "user_id",
              postgresql_where="user_id IS NOT NULL"),
        Index("idx_refresh_tokens_admin", "admin_id",
              postgresql_where="admin_id IS NOT NULL"),
        Index("idx_refresh_tokens_expires", "expires_at",
              postgresql_where="is_used = false AND is_revoked = false"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"),
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
