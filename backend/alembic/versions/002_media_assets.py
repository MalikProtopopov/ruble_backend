"""Media assets library for admin uploads.

Revision ID: 002_media_assets
Revises: 001_initial
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_media_assets"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


media_asset_type = postgresql.ENUM("video", "document", name="media_asset_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    media_asset_type.create(bind, checkfirst=True)

    op.create_table(
        "media_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("public_url", sa.String(2048), nullable=False),
        sa.Column("type", media_asset_type, nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("uploaded_by_admin_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by_admin_id"], ["admins.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key"),
    )
    op.create_index("idx_media_assets_created_at", "media_assets", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_media_assets_created_at", table_name="media_assets")
    op.drop_table("media_assets")
    sa.Enum(name="media_asset_type").drop(op.get_bind(), checkfirst=True)
