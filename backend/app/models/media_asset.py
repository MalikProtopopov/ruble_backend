"""Uploaded media metadata (S3/MinIO) for admin library."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MediaAssetType, UUIDMixin


class MediaAsset(Base, UUIDMixin):
    __tablename__ = "media_assets"
    __table_args__ = (Index("idx_media_assets_created_at", "created_at"),)

    s3_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    public_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    type: Mapped[MediaAssetType] = mapped_column(
        SAEnum(MediaAssetType, name="media_asset_type", create_type=True),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    uploaded_by = relationship("Admin", foreign_keys=[uploaded_by_admin_id])
