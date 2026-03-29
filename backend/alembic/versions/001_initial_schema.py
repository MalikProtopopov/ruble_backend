"""Initial schema — 20 tables, all ENUMs, all indexes.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- ENUM types ---

foundation_status = postgresql.ENUM(
    "pending_verification", "active", "suspended",
    name="foundation_status", create_type=False,
)
campaign_status = postgresql.ENUM(
    "draft", "active", "paused", "completed", "archived",
    name="campaign_status", create_type=False,
)
user_role = postgresql.ENUM("donor", "patron", name="user_role", create_type=False)
push_platform = postgresql.ENUM("fcm", "apns", name="push_platform", create_type=False)
thanks_content_type = postgresql.ENUM("video", "audio", name="thanks_content_type", create_type=False)
donation_status = postgresql.ENUM(
    "pending", "success", "failed", "refunded",
    name="donation_status", create_type=False,
)
donation_source = postgresql.ENUM(
    "app", "patron_link", "offline",
    name="donation_source", create_type=False,
)
offline_payment_method = postgresql.ENUM(
    "cash", "bank_transfer", "other",
    name="offline_payment_method", create_type=False,
)
billing_period = postgresql.ENUM("weekly", "monthly", name="billing_period", create_type=False)
allocation_strategy = postgresql.ENUM(
    "platform_pool", "foundation_pool", "specific_campaign",
    name="allocation_strategy", create_type=False,
)
subscription_status = postgresql.ENUM(
    "active", "paused", "cancelled", "pending_payment_method",
    name="subscription_status", create_type=False,
)
paused_reason = postgresql.ENUM(
    "user_request", "no_campaigns", "payment_failed",
    name="paused_reason", create_type=False,
)
transaction_status = postgresql.ENUM(
    "pending", "success", "failed", "skipped", "refunded",
    name="transaction_status", create_type=False,
)
skip_reason = postgresql.ENUM("no_active_campaigns", name="skip_reason", create_type=False)
allocation_change_reason = postgresql.ENUM(
    "campaign_completed", "campaign_closed_early",
    "no_campaigns_in_foundation", "no_campaigns_on_platform",
    "manual_by_admin",
    name="allocation_change_reason", create_type=False,
)
achievement_condition_type = postgresql.ENUM(
    "streak_days", "total_amount_kopecks", "donations_count",
    name="achievement_condition_type", create_type=False,
)
patron_link_status = postgresql.ENUM(
    "pending", "paid", "expired",
    name="patron_link_status", create_type=False,
)
notification_status = postgresql.ENUM(
    "sent", "mock", "failed",
    name="notification_status", create_type=False,
)


def upgrade() -> None:
    # --- Create ENUM types ---
    for e in [
        foundation_status, campaign_status, user_role, push_platform,
        thanks_content_type, donation_status, donation_source,
        offline_payment_method, billing_period, allocation_strategy,
        subscription_status, paused_reason, transaction_status, skip_reason,
        allocation_change_reason, achievement_condition_type,
        patron_link_status, notification_status,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    # ===== Independent tables (no FK to other app tables) =====

    op.create_table(
        "foundations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(500), nullable=False),
        sa.Column("inn", sa.String(12), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("logo_url", sa.String()),
        sa.Column("website_url", sa.String()),
        sa.Column("status", foundation_status, nullable=False, server_default="pending_verification"),
        sa.Column("yookassa_shop_id", sa.String()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_foundations_inn", "foundations", ["inn"], unique=True)
    op.create_index("idx_foundations_status", "foundations", ["status"])

    op.create_table(
        "admins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "achievements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("icon_url", sa.String()),
        sa.Column("condition_type", achievement_condition_type, nullable=False),
        sa.Column("condition_value", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("name", sa.String(100)),
        sa.Column("avatar_url", sa.String()),
        sa.Column("role", user_role, nullable=False, server_default="donor"),
        sa.Column("push_token", sa.String()),
        sa.Column("push_platform", push_platform),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Europe/Moscow"),
        sa.Column("notification_preferences", postgresql.JSONB(),
                   server_default='{"push_on_payment": true, "push_on_campaign_change": true, "push_daily_streak": false, "push_campaign_completed": true}',
                   nullable=False),
        sa.Column("current_streak_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_streak_date", sa.Date()),
        sa.Column("total_donated_kopecks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_donations_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_streak_push_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True,
                     postgresql_where=sa.text("is_deleted = false"))
    op.create_index("idx_users_role", "users", ["role"],
                     postgresql_where=sa.text("role = 'patron'"))
    op.create_index("idx_users_streak_push", "users", ["next_streak_push_at"],
                     postgresql_where=sa.text("next_streak_push_at IS NOT NULL AND is_deleted = false"))

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_otp_codes_email", "otp_codes", ["email", sa.text("created_at DESC")])
    op.create_index("idx_otp_codes_expires", "otp_codes", ["expires_at"],
                     postgresql_where=sa.text("is_used = false"))

    # ===== Tables depending on foundations, admins, users =====

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("admin_id", sa.UUID(), sa.ForeignKey("admins.id", ondelete="CASCADE")),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND admin_id IS NULL) OR (user_id IS NULL AND admin_id IS NOT NULL)",
            name="ck_refresh_tokens_owner",
        ),
    )
    op.create_index("idx_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"],
                     postgresql_where=sa.text("user_id IS NOT NULL"))
    op.create_index("idx_refresh_tokens_admin", "refresh_tokens", ["admin_id"],
                     postgresql_where=sa.text("admin_id IS NOT NULL"))
    op.create_index("idx_refresh_tokens_expires", "refresh_tokens", ["expires_at"],
                     postgresql_where=sa.text("is_used = false AND is_revoked = false"))

    op.create_table(
        "user_achievements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_id", sa.UUID(), sa.ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("foundation_id", sa.UUID(), sa.ForeignKey("foundations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("video_url", sa.String()),
        sa.Column("thumbnail_url", sa.String()),
        sa.Column("status", campaign_status, nullable=False, server_default="draft"),
        sa.Column("goal_amount", sa.Integer()),
        sa.Column("collected_amount", sa.Integer(), server_default="0", nullable=False),
        sa.Column("donors_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("urgency_level", sa.Integer(), server_default="3", nullable=False),
        sa.Column("is_permanent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("closed_early", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("close_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("urgency_level >= 1 AND urgency_level <= 5", name="ck_campaigns_urgency"),
    )
    op.create_index("idx_campaigns_feed", "campaigns",
                     [sa.text("urgency_level DESC"), "sort_order", "status"],
                     postgresql_where=sa.text("status = 'active'"))
    op.create_index("idx_campaigns_foundation", "campaigns", ["foundation_id"])
    op.create_index("idx_campaigns_ends_at", "campaigns", ["ends_at"],
                     postgresql_where=sa.text("ends_at IS NOT NULL AND status = 'active' AND is_permanent = false"))

    op.create_table(
        "notification_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("push_token", sa.String()),
        sa.Column("notification_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB()),
        sa.Column("status", notification_status, nullable=False),
        sa.Column("provider_response", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_notification_logs_user", "notification_logs", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_notification_logs_type", "notification_logs", ["notification_type", sa.text("created_at DESC")])

    op.create_table(
        "payout_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("foundation_id", sa.UUID(), sa.ForeignKey("foundations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("transfer_reference", sa.String()),
        sa.Column("note", sa.Text()),
        sa.Column("created_by_admin_id", sa.UUID(), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_kopecks > 0", name="ck_payout_records_amount"),
    )
    op.create_index("idx_payout_records_foundation", "payout_records", ["foundation_id", sa.text("created_at DESC")])

    # ===== Tables depending on campaigns =====

    op.create_table(
        "campaign_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_url", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_campaign_documents_campaign", "campaign_documents", ["campaign_id", "sort_order"])

    op.create_table(
        "campaign_donors",
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("campaign_id", "user_id"),
    )
    op.create_index("idx_campaign_donors_user", "campaign_donors", ["user_id"])

    op.create_table(
        "thanks_contents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", thanks_content_type, nullable=False),
        sa.Column("media_url", sa.String(), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_thanks_contents_campaign", "thanks_contents", ["campaign_id"])

    op.create_table(
        "donations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("foundation_id", sa.UUID(), sa.ForeignKey("foundations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("platform_fee_kopecks", sa.Integer(), nullable=False),
        sa.Column("acquiring_fee_kopecks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("nco_amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("provider_payment_id", sa.String()),
        sa.Column("idempotence_key", sa.String(), nullable=False),
        sa.Column("payment_url", sa.String()),
        sa.Column("status", donation_status, nullable=False, server_default="pending"),
        sa.Column("source", donation_source, nullable=False, server_default="app"),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_kopecks >= 100", name="ck_donations_min_amount"),
    )
    op.create_index("idx_donations_user", "donations", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_donations_campaign", "donations", ["campaign_id", "status"])
    op.create_index("idx_donations_idempotence", "donations", ["idempotence_key"], unique=True)
    op.create_index("idx_donations_provider", "donations", ["provider_payment_id"], unique=True,
                     postgresql_where=sa.text("provider_payment_id IS NOT NULL"))

    op.create_table(
        "offline_payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("payment_method", offline_payment_method, nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("external_reference", sa.String()),
        sa.Column("recorded_by_admin_id", sa.UUID(), sa.ForeignKey("admins.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_kopecks > 0", name="ck_offline_payments_amount"),
    )
    op.create_index("idx_offline_payments_campaign", "offline_payments", ["campaign_id"])
    op.create_index("idx_offline_payments_dedup", "offline_payments",
                     ["campaign_id", "payment_date", "amount_kopecks", "external_reference"],
                     unique=True,
                     postgresql_where=sa.text("external_reference IS NOT NULL"))

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("billing_period", billing_period, nullable=False),
        sa.Column("allocation_strategy", allocation_strategy, nullable=False),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("foundation_id", sa.UUID(), sa.ForeignKey("foundations.id", ondelete="SET NULL")),
        sa.Column("payment_method_id", sa.String()),
        sa.Column("status", subscription_status, nullable=False, server_default="pending_payment_method"),
        sa.Column("paused_reason", paused_reason),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("next_billing_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_kopecks IN (100, 300, 500, 1000)", name="ck_subscriptions_amount"),
    )
    op.create_index("idx_subscriptions_billing", "subscriptions", ["next_billing_at", "status"],
                     postgresql_where=sa.text("status = 'active'"))
    op.create_index("idx_subscriptions_user", "subscriptions", ["user_id", "status"])
    op.create_index("idx_subscriptions_campaign", "subscriptions", ["campaign_id"],
                     postgresql_where=sa.text("campaign_id IS NOT NULL AND status IN ('active', 'paused')"))
    op.create_index("idx_subscriptions_foundation", "subscriptions", ["foundation_id"],
                     postgresql_where=sa.text("foundation_id IS NOT NULL AND status IN ('active', 'paused')"))

    # ===== Tables depending on campaigns + subscriptions =====

    op.create_table(
        "transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), sa.ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("foundation_id", sa.UUID(), sa.ForeignKey("foundations.id", ondelete="SET NULL")),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("platform_fee_kopecks", sa.Integer(), nullable=False),
        sa.Column("nco_amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("acquiring_fee_kopecks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_payment_id", sa.String()),
        sa.Column("idempotence_key", sa.String(), nullable=False),
        sa.Column("status", transaction_status, nullable=False, server_default="pending"),
        sa.Column("skipped_reason", skip_reason),
        sa.Column("cancellation_reason", sa.String()),
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_transactions_subscription", "transactions", ["subscription_id", sa.text("created_at DESC")])
    op.create_index("idx_transactions_retry", "transactions", ["next_retry_at", "status"],
                     postgresql_where=sa.text("status = 'failed' AND next_retry_at IS NOT NULL"))
    op.create_index("idx_transactions_idempotence", "transactions", ["idempotence_key"], unique=True)
    op.create_index("idx_transactions_provider", "transactions", ["provider_payment_id"], unique=True,
                     postgresql_where=sa.text("provider_payment_id IS NOT NULL"))
    op.create_index("idx_transactions_campaign", "transactions", ["campaign_id", "status"],
                     postgresql_where=sa.text("status = 'success'"))
    op.create_index("idx_transactions_foundation", "transactions", ["foundation_id", "status"])

    op.create_table(
        "allocation_changes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("to_campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("reason", allocation_change_reason, nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_allocation_changes_subscription", "allocation_changes", ["subscription_id", sa.text("created_at DESC")])

    # ===== Tables depending on donations =====

    op.create_table(
        "patron_payment_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), sa.ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("donation_id", sa.UUID(), sa.ForeignKey("donations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("payment_url", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", patron_link_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_patron_links_campaign", "patron_payment_links", ["campaign_id", "status"])
    op.create_index("idx_patron_links_user", "patron_payment_links", ["created_by_user_id"])
    op.create_index("idx_patron_links_expires", "patron_payment_links", ["expires_at"],
                     postgresql_where=sa.text("status = 'pending'"))

    # ===== Tables depending on thanks_contents =====

    op.create_table(
        "thanks_content_shown",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thanks_content_id", sa.UUID(), sa.ForeignKey("thanks_contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String()),
        sa.Column("shown_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "thanks_content_id", name="idx_thanks_shown_unique"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("thanks_content_shown")
    op.drop_table("patron_payment_links")
    op.drop_table("allocation_changes")
    op.drop_table("transactions")
    op.drop_table("subscriptions")
    op.drop_table("offline_payments")
    op.drop_table("donations")
    op.drop_table("thanks_contents")
    op.drop_table("campaign_donors")
    op.drop_table("campaign_documents")
    op.drop_table("payout_records")
    op.drop_table("notification_logs")
    op.drop_table("campaigns")
    op.drop_table("refresh_tokens")
    op.drop_table("user_achievements")
    op.drop_table("otp_codes")
    op.drop_table("users")
    op.drop_table("achievements")
    op.drop_table("admins")
    op.drop_table("foundations")

    # Drop ENUM types
    for name in [
        "notification_status", "patron_link_status",
        "achievement_condition_type", "allocation_change_reason",
        "skip_reason", "transaction_status", "paused_reason",
        "subscription_status", "allocation_strategy", "billing_period",
        "offline_payment_method", "donation_source", "donation_status",
        "thanks_content_type", "push_platform", "user_role",
        "campaign_status", "foundation_status",
    ]:
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
