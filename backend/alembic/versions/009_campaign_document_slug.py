"""CampaignDocument.slug — URL-friendly per-campaign identifier.

Adds a ``slug`` column used by the public document-detail endpoint
(GET /api/v1/campaigns/{id}/documents/{slug}). Existing rows are backfilled
with slugs generated from their title, deduplicated within each campaign.

Revision ID: 009_campaign_doc_slug
Revises: 008_last_seen_fp
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# Kept short — alembic_version.version_num is varchar(32) on existing prod DBs.
revision: str = "009_campaign_doc_slug"
down_revision: Union[str, None] = "008_last_seen_fp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Inlined transliteration map — mirrors app/core/slug.py. Migrations must not
# import app code (it can change), so we keep a self-contained copy here.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    out = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    out = re.sub(r"-{2,}", "-", out)
    return out[:200] or "document"


def upgrade() -> None:
    op.add_column(
        "campaign_documents",
        sa.Column("slug", sa.String(length=255), nullable=True),
    )

    # Backfill existing documents. Slugs are deduplicated per campaign so the
    # unique index created below never collides.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, campaign_id, title FROM campaign_documents "
            "ORDER BY campaign_id, sort_order, created_at"
        )
    ).fetchall()

    used: dict = {}  # campaign_id -> set of slugs already assigned
    for row in rows:
        base = _slugify(row.title)
        seen = used.setdefault(row.campaign_id, set())
        candidate = base
        suffix = 2
        while candidate in seen:
            candidate = f"{base}-{suffix}"
            suffix += 1
        seen.add(candidate)
        bind.execute(
            sa.text("UPDATE campaign_documents SET slug = :slug WHERE id = :id"),
            {"slug": candidate, "id": row.id},
        )

    op.alter_column("campaign_documents", "slug", nullable=False)
    op.create_index(
        "idx_campaign_documents_slug",
        "campaign_documents",
        ["campaign_id", "slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_campaign_documents_slug", table_name="campaign_documents")
    op.drop_column("campaign_documents", "slug")
