import datetime as dt
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, desc, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PushPlatform, SoftDeleteMixin, TimestampMixin, UUIDMixin, UserRole


DEFAULT_NOTIFICATION_PREFERENCES = {
    "push_on_payment": True,
    "push_on_campaign_change": True,
    "push_daily_streak": False,
    "push_campaign_completed": True,
    "push_on_donation_reminder": True,
}


class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_email", "email", unique=True,
              postgresql_where="is_deleted = false AND email IS NOT NULL"),
        Index("idx_users_device", "device_id", unique=True,
              postgresql_where="is_deleted = false AND device_id IS NOT NULL"),
        Index("idx_users_role", "role",
              postgresql_where="role = 'patron'"),
        Index("idx_users_streak_push", "next_streak_push_at",
              postgresql_where="next_streak_push_at IS NOT NULL AND is_deleted = false"),
        Index("idx_users_inactive_anonymous", "last_seen_at",
              postgresql_where="is_anonymous = true AND is_deleted = false"),
    )

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String)
    device_id: Mapped[str | None] = mapped_column(String(64))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_type=True),
        nullable=False,
        server_default=UserRole.donor.value,
    )
    push_token: Mapped[str | None] = mapped_column(String)
    push_platform: Mapped[PushPlatform | None] = mapped_column(
        SAEnum(PushPlatform, name="push_platform", create_type=True),
    )
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="Europe/Moscow",
    )
    notification_preferences: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        server_default='{"push_on_payment": true, "push_on_campaign_change": true, "push_daily_streak": false, "push_campaign_completed": true, "push_on_donation_reminder": true}',
    )
    # Streak & impact cache
    current_streak_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_streak_date: Mapped[dt.date | None] = mapped_column(Date)
    total_donated_kopecks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_donations_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_streak_push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Updated on every authenticated request (throttled to once per LAST_SEEN_THROTTLE_MINUTES).
    # Used by the inactive-anonymous-cleanup cron task.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class OTPCode(Base, UUIDMixin):
    __tablename__ = "otp_codes"
    __table_args__ = (
        Index("idx_otp_codes_email", "email", desc("created_at")),
        Index("idx_otp_codes_expires", "expires_at",
              postgresql_where="is_used = false"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
