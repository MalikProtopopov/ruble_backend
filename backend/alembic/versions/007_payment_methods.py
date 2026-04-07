"""Saved payment methods.

Revision ID: 007_payment_methods
Revises: 006_anonymous_users
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007_payment_methods"
down_revision: Union[str, None] = "006_anonymous_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_methods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False, server_default="yookassa"),
        sa.Column("provider_pm_id", sa.String(128), nullable=False),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("card_type", sa.String(32), nullable=True),
        sa.Column("title", sa.String(64), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_payment_methods_user",
        "payment_methods",
        ["user_id"],
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "idx_payment_methods_provider",
        "payment_methods",
        ["provider", "provider_pm_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # Index used by donation cooldown / list-with-user-data queries.
    op.create_index(
        "idx_donations_user_campaign_created",
        "donations",
        ["user_id", "campaign_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("status = 'success' OR status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("idx_donations_user_campaign_created", table_name="donations")
    op.drop_index("idx_payment_methods_provider", table_name="payment_methods")
    op.drop_index("idx_payment_methods_user", table_name="payment_methods")
    op.drop_table("payment_methods")
