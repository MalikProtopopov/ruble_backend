from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AchievementConditionType, Base, UUIDMixin


class Achievement(Base, UUIDMixin):
    __tablename__ = "achievements"

    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon_url: Mapped[str | None] = mapped_column(String)
    condition_type: Mapped[AchievementConditionType] = mapped_column(
        SAEnum(AchievementConditionType, name="achievement_condition_type", create_type=True),
        nullable=False,
    )
    condition_value: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class UserAchievement(Base, UUIDMixin):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    achievement_id: Mapped[UUID] = mapped_column(
        ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False,
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
