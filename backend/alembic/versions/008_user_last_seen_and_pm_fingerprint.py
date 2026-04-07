"""User.last_seen_at + PaymentMethod.card_fingerprint.

Adds infrastructure for the inactive-anonymous-account cleanup task and
for cross-account orphaned-card recovery.

Revision ID: 008_user_last_seen_and_pm_fingerprint
Revises: 007_payment_methods
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_user_last_seen_and_pm_fingerprint"
down_revision: Union[str, None] = "007_payment_methods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # last_seen_at: updated on every authenticated request (throttled), used by
    # the inactive-anonymous-cleanup cron task. Backfill to created_at so existing
    # users are not immediately considered inactive.
    op.add_column(
        "users",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET last_seen_at = created_at WHERE last_seen_at IS NULL")

    # Index used by the cleanup task to find inactive anonymous users efficiently.
    op.create_index(
        "idx_users_inactive_anonymous",
        "users",
        ["last_seen_at"],
        postgresql_where=sa.text("is_anonymous = true AND is_deleted = false"),
    )

    # Card fingerprint: deterministic hash of (first6 + last4 + exp_month + exp_year)
    # built when YooKassa returns the saved payment method. Used by the recovery
    # endpoint to detect orphaned anonymous accounts that hold the same physical card.
    op.add_column(
        "payment_methods",
        sa.Column("card_fingerprint", sa.String(64), nullable=True),
    )
    op.create_index(
        "idx_payment_methods_fingerprint",
        "payment_methods",
        ["card_fingerprint"],
        postgresql_where=sa.text("is_deleted = false AND card_fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_payment_methods_fingerprint", table_name="payment_methods")
    op.drop_column("payment_methods", "card_fingerprint")
    op.drop_index("idx_users_inactive_anonymous", table_name="users")
    op.drop_column("users", "last_seen_at")
