"""CampaignDocument: Markdown body + excerpt, and nullable file_url.

Adds in-app readable text to campaign documents:
- ``content``  — full document body as Markdown (rendered in the app).
- ``excerpt``  — short plain-text preview for the documents list.
- ``file_url`` becomes NULLABLE so a document can be text-only (no PDF).

Revision ID: 010_campaign_doc_content
Revises: 009_campaign_doc_slug
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# Kept short — alembic_version.version_num is varchar(32) on existing prod DBs.
revision: str = "010_campaign_doc_content"
down_revision: Union[str, None] = "009_campaign_doc_slug"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "campaign_documents",
        sa.Column("excerpt", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "campaign_documents",
        sa.Column("content", sa.Text(), nullable=True),
    )
    op.alter_column(
        "campaign_documents", "file_url",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # Drop text-only docs before re-imposing NOT NULL on file_url.
    op.execute("DELETE FROM campaign_documents WHERE file_url IS NULL")
    op.alter_column(
        "campaign_documents", "file_url",
        existing_type=sa.String(),
        nullable=False,
    )
    op.drop_column("campaign_documents", "content")
    op.drop_column("campaign_documents", "excerpt")
