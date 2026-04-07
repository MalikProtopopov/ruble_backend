"""Anonymous users: nullable email + device_id + flags.

Revision ID: 006_anonymous_users
Revises: 005_documents
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_anonymous_users"
down_revision: Union[str, None] = "005_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. email becomes nullable
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)

    # 2. drop old unique index, recreate with email IS NOT NULL filter
    op.drop_index("idx_users_email", table_name="users")
    op.create_index(
        "idx_users_email",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND email IS NOT NULL"),
    )

    # 3. new columns
    op.add_column("users", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Backfill: existing users have email → mark them as verified.
    op.execute("UPDATE users SET is_email_verified = true WHERE email IS NOT NULL")

    # 4. unique partial index for device_id
    op.create_index(
        "idx_users_device",
        "users",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND device_id IS NOT NULL"),
    )

    # 5. JSONB default — new key push_on_donation_reminder for new users
    op.alter_column(
        "users",
        "notification_preferences",
        server_default=sa.text(
            "'{\"push_on_payment\": true, \"push_on_campaign_change\": true, "
            "\"push_daily_streak\": false, \"push_campaign_completed\": true, "
            "\"push_on_donation_reminder\": true}'::jsonb"
        ),
    )
    # Backfill existing rows so the new key is present.
    op.execute(
        "UPDATE users SET notification_preferences = "
        "notification_preferences || '{\"push_on_donation_reminder\": true}'::jsonb "
        "WHERE NOT (notification_preferences ? 'push_on_donation_reminder')"
    )


def downgrade() -> None:
    op.drop_index("idx_users_device", table_name="users")
    op.drop_column("users", "is_email_verified")
    op.drop_column("users", "is_anonymous")
    op.drop_column("users", "device_id")

    op.drop_index("idx_users_email", table_name="users")
    op.create_index(
        "idx_users_email",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # Cannot reliably make email NOT NULL again if anonymous users exist; skip.
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)

    op.alter_column(
        "users",
        "notification_preferences",
        server_default=sa.text(
            "'{\"push_on_payment\": true, \"push_on_campaign_change\": true, "
            "\"push_daily_streak\": false, \"push_campaign_completed\": true}'::jsonb"
        ),
    )
