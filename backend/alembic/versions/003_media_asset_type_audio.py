"""Add audio value to media_asset_type enum.

Revision ID: 003_media_asset_type_audio
Revises: 002_media_assets
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003_media_asset_type_audio"
down_revision: Union[str, None] = "002_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE media_asset_type ADD VALUE IF NOT EXISTS 'audio'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely; leave type as-is.
    pass
