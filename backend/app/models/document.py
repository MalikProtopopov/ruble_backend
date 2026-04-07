"""Legal/corporate documents (privacy policy, offer, etc.)."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, DocumentStatus, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Document(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_documents_status",
        ),
        CheckConstraint("length(title) >= 1", name="ck_documents_title_len"),
        CheckConstraint("length(slug) >= 2", name="ck_documents_slug_len"),
        Index("idx_documents_slug", "slug", unique=True, postgresql_where="is_deleted = false"),
        Index(
            "idx_documents_published",
            "status",
            postgresql_where="is_deleted = false AND status = 'published'",
        ),
        Index("idx_documents_date", "document_date"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status", create_type=True),
        nullable=False,
        server_default=DocumentStatus.draft.value,
    )
    document_version: Mapped[str | None] = mapped_column(String(50))
    document_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_url: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    def publish(self) -> None:
        from datetime import datetime, timezone

        self.status = DocumentStatus.published
        if self.published_at is None:
            self.published_at = datetime.now(timezone.utc)

    def unpublish(self) -> None:
        self.status = DocumentStatus.draft

    def archive(self) -> None:
        self.status = DocumentStatus.archived
