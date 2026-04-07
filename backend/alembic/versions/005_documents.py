"""Create documents table.

Revision ID: 005_documents
Revises: 004_media_asset_type_image
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_documents"
down_revision: Union[str, None] = "004_media_asset_type_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type
    document_status = sa.Enum("draft", "published", "archived", name="document_status")
    document_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("excerpt", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "archived", name="document_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("document_version", sa.String(50), nullable=True),
        sa.Column("document_date", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_documents_status"),
        sa.CheckConstraint("length(title) >= 1", name="ck_documents_title_len"),
        sa.CheckConstraint("length(slug) >= 2", name="ck_documents_slug_len"),
    )

    op.create_index(
        "idx_documents_slug",
        "documents",
        ["slug"],
        unique=True,
        postgresql_where="is_deleted = false",
    )
    op.create_index(
        "idx_documents_published",
        "documents",
        ["status"],
        postgresql_where="is_deleted = false AND status = 'published'",
    )
    op.create_index("idx_documents_date", "documents", ["document_date"])


def downgrade() -> None:
    op.drop_index("idx_documents_date", table_name="documents")
    op.drop_index("idx_documents_published", table_name="documents")
    op.drop_index("idx_documents_slug", table_name="documents")
    op.drop_table("documents")
    sa.Enum(name="document_status").drop(op.get_bind(), checkfirst=True)
