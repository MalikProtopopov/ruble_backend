import enum
from datetime import datetime
from uuid import UUID

import uuid_utils
from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid7_stdlib() -> UUID:
    """Generate a UUID v7 and return it as a stdlib uuid.UUID."""
    return UUID(str(uuid_utils.uuid7()))


# Public alias for use across the application
uuid7 = _uuid7_stdlib


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=_uuid7_stdlib,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- PostgreSQL ENUM types ---


class FoundationStatus(str, enum.Enum):
    pending_verification = "pending_verification"
    active = "active"
    suspended = "suspended"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class UserRole(str, enum.Enum):
    donor = "donor"
    patron = "patron"


class PushPlatform(str, enum.Enum):
    fcm = "fcm"
    apns = "apns"


class ThanksContentType(str, enum.Enum):
    video = "video"
    audio = "audio"


class DonationStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    refunded = "refunded"


class DonationSource(str, enum.Enum):
    app = "app"
    patron_link = "patron_link"
    offline = "offline"


class OfflinePaymentMethod(str, enum.Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    other = "other"


class BillingPeriod(str, enum.Enum):
    weekly = "weekly"
    monthly = "monthly"


class AllocationStrategy(str, enum.Enum):
    platform_pool = "platform_pool"
    foundation_pool = "foundation_pool"
    specific_campaign = "specific_campaign"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    cancelled = "cancelled"
    pending_payment_method = "pending_payment_method"


class PausedReason(str, enum.Enum):
    user_request = "user_request"
    no_campaigns = "no_campaigns"
    payment_failed = "payment_failed"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    skipped = "skipped"
    refunded = "refunded"


class SkipReason(str, enum.Enum):
    no_active_campaigns = "no_active_campaigns"


class AllocationChangeReason(str, enum.Enum):
    campaign_completed = "campaign_completed"
    campaign_closed_early = "campaign_closed_early"
    no_campaigns_in_foundation = "no_campaigns_in_foundation"
    no_campaigns_on_platform = "no_campaigns_on_platform"
    manual_by_admin = "manual_by_admin"


class AchievementConditionType(str, enum.Enum):
    streak_days = "streak_days"
    total_amount_kopecks = "total_amount_kopecks"
    donations_count = "donations_count"


class PatronLinkStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    expired = "expired"


class NotificationStatus(str, enum.Enum):
    sent = "sent"
    mock = "mock"
    failed = "failed"


class DocumentStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class MediaAssetType(str, enum.Enum):
    video = "video"
    document = "document"
    audio = "audio"
    image = "image"
