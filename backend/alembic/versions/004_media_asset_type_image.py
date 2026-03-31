"""Add image value to media_asset_type enum.

Revision ID: 004_media_asset_type_image
Revises: 003_media_asset_type_audio
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004_media_asset_type_image"
down_revision: Union[str, None] = "003_media_asset_type_audio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE media_asset_type ADD VALUE IF NOT EXISTS 'image'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely; leave type as-is.
    pass
