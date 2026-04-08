"""Tests for admin payment method maintenance endpoints + reconcile cron."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import Donation, PaymentMethod, User
from app.models.base import DonationStatus, uuid7
from app.services.payment_method import (
    backfill_fingerprints_from_yookassa,
    build_card_fingerprint,
    dedupe_payment_methods,
)
from tests.conftest import create_campaign, create_foundation, create_user

pytestmark = pytest.mark.asyncio


async def _make_pm(db, user, *, provider_pm_id, fingerprint=None, is_default=True, last4="4477"):
    pm = PaymentMethod(
        id=uuid7(),
        user_id=user.id,
        provider="yookassa",
        provider_pm_id=provider_pm_id,
        card_last4=last4,
        card_type="MasterCard",
        is_default=is_default,
        card_fingerprint=fingerprint,
    )
    db.add(pm)
    await db.flush()
    return pm


# ---------------------------------------------------------------------------
# backfill_fingerprints_from_yookassa
# ---------------------------------------------------------------------------


async def test_backfill_fingerprints_fills_from_yookassa_response(db):
    user = await create_user(db)
    pm = await _make_pm(db, user, provider_pm_id="3167aa45-test", fingerprint=None)

    fake_payload = {
        "payment_method": {
            "card": {
                "first6": "555555",
                "last4": "4477",
                "expiry_month": "12",
                "expiry_year": "2034",
                "card_type": "MasterCard",
            },
        },
    }
    expected_fp = build_card_fingerprint(
        first6="555555", last4="4477", exp_month="12", exp_year="2034"
    )

    with patch(
        "app.services.yookassa.yookassa_client.get_payment",
        new=AsyncMock(return_value=fake_payload),
    ) as mock_get:
        result = await backfill_fingerprints_from_yookassa(db)

    mock_get.assert_awaited_once_with("3167aa45-test")
    assert result["scanned"] == 1
    assert result["filled"] == 1
    assert result["failed"] == 0

    await db.refresh(pm)
    assert pm.card_fingerprint == expected_fp
    assert pm.card_type == "MasterCard"


async def test_backfill_fingerprints_skips_already_filled(db):
    user = await create_user(db)
    fp = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="01", exp_year="2030"
    )
    await _make_pm(db, user, provider_pm_id="x", fingerprint=fp)

    with patch(
        "app.services.yookassa.yookassa_client.get_payment",
        new=AsyncMock(),
    ) as mock_get:
        result = await backfill_fingerprints_from_yookassa(db)

    mock_get.assert_not_called()
    assert result["scanned"] == 0


async def test_backfill_fingerprints_records_yookassa_errors(db):
    user = await create_user(db)
    pm = await _make_pm(db, user, provider_pm_id="broken", fingerprint=None)

    with patch(
        "app.services.yookassa.yookassa_client.get_payment",
        new=AsyncMock(side_effect=RuntimeError("YooKassa 503")),
    ):
        result = await backfill_fingerprints_from_yookassa(db)

    assert result["filled"] == 0
    assert result["failed"] == 1
    assert result["failed_items"][0]["pm_id"] == str(pm.id)
    await db.refresh(pm)
    assert pm.card_fingerprint is None


async def test_backfill_fingerprints_handles_missing_card_data(db):
    """YooKassa returns the payment but without card details (e.g. SBP)."""
    user = await create_user(db)
    pm = await _make_pm(db, user, provider_pm_id="sbp-1", fingerprint=None)

    with patch(
        "app.services.yookassa.yookassa_client.get_payment",
        new=AsyncMock(return_value={"payment_method": {"type": "sbp"}}),
    ):
        result = await backfill_fingerprints_from_yookassa(db)

    assert result["filled"] == 0
    assert result["failed"] == 1
    await db.refresh(pm)
    assert pm.card_fingerprint is None


# ---------------------------------------------------------------------------
# dedupe_payment_methods
# ---------------------------------------------------------------------------


async def test_dedupe_keeps_newest_soft_deletes_older(db):
    user = await create_user(db)
    fp = build_card_fingerprint(
        first6="555555", last4="4477", exp_month="12", exp_year="2034"
    )
    older = await _make_pm(db, user, provider_pm_id="old", fingerprint=fp, is_default=True)
    newer = await _make_pm(db, user, provider_pm_id="new", fingerprint=fp, is_default=False)
    # Force a clear time gap so dedupe can deterministically pick "newest".
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(PaymentMethod)
        .where(PaymentMethod.id == older.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await db.flush()

    result = await dedupe_payment_methods(db)
    assert result["soft_deleted"] == 1
    assert result["affected_users"] == 1

    await db.refresh(older)
    await db.refresh(newer)
    assert older.is_deleted is True
    assert older.is_default is False
    assert newer.is_deleted is False
    # The newest survivor should now carry the default flag.
    assert newer.is_default is True


async def test_dedupe_idempotent(db):
    user = await create_user(db)
    fp = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="01", exp_year="2030"
    )
    older = await _make_pm(db, user, provider_pm_id="a", fingerprint=fp, is_default=True)
    await _make_pm(db, user, provider_pm_id="b", fingerprint=fp, is_default=False)
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(PaymentMethod)
        .where(PaymentMethod.id == older.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await db.flush()

    r1 = await dedupe_payment_methods(db)
    r2 = await dedupe_payment_methods(db)
    assert r1["soft_deleted"] == 1
    assert r2["soft_deleted"] == 0


async def test_dedupe_does_not_touch_distinct_cards(db):
    user = await create_user(db)
    fp1 = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="01", exp_year="2030"
    )
    fp2 = build_card_fingerprint(
        first6="555555", last4="4477", exp_month="12", exp_year="2034"
    )
    pm1 = await _make_pm(db, user, provider_pm_id="a", fingerprint=fp1, last4="1111", is_default=True)
    pm2 = await _make_pm(db, user, provider_pm_id="b", fingerprint=fp2, last4="4477", is_default=False)

    result = await dedupe_payment_methods(db)
    assert result["soft_deleted"] == 0
    await db.refresh(pm1)
    await db.refresh(pm2)
    assert pm1.is_deleted is False
    assert pm2.is_deleted is False


async def test_dedupe_isolates_per_user(db):
    """Same fingerprint on TWO different users must NOT cross-affect."""
    user_a = await create_user(db, email="a@x.test")
    user_b = await create_user(db, email="b@x.test")
    fp = build_card_fingerprint(
        first6="555555", last4="4477", exp_month="12", exp_year="2034"
    )
    pm_a = await _make_pm(db, user_a, provider_pm_id="a", fingerprint=fp)
    pm_b = await _make_pm(db, user_b, provider_pm_id="b", fingerprint=fp)

    result = await dedupe_payment_methods(db)
    assert result["soft_deleted"] == 0
    await db.refresh(pm_a)
    await db.refresh(pm_b)
    assert pm_a.is_deleted is False
    assert pm_b.is_deleted is False


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


async def test_admin_backfill_fingerprints_endpoint(client, db, admin_headers):
    user = await create_user(db)
    await _make_pm(db, user, provider_pm_id="api-pm", fingerprint=None)

    with patch(
        "app.services.yookassa.yookassa_client.get_payment",
        new=AsyncMock(return_value={
            "payment_method": {
                "card": {
                    "first6": "555555", "last4": "4477",
                    "expiry_month": "12", "expiry_year": "2034",
                    "card_type": "MasterCard",
                }
            }
        }),
    ):
        resp = await client.post(
            "/api/v1/admin/payment-methods/backfill-fingerprints",
            headers=admin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filled"] == 1


async def test_admin_dedupe_endpoint(client, db, admin_headers):
    user = await create_user(db)
    fp = build_card_fingerprint(
        first6="555555", last4="4477", exp_month="12", exp_year="2034"
    )
    older = await _make_pm(db, user, provider_pm_id="x1", fingerprint=fp, is_default=True)
    await _make_pm(db, user, provider_pm_id="x2", fingerprint=fp, is_default=False)
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(PaymentMethod)
        .where(PaymentMethod.id == older.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await db.flush()

    resp = await client.post(
        "/api/v1/admin/payment-methods/dedupe", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["soft_deleted"] == 1


async def test_admin_endpoints_require_admin(client):
    r1 = await client.post("/api/v1/admin/payment-methods/backfill-fingerprints")
    r2 = await client.post("/api/v1/admin/payment-methods/dedupe")
    assert r1.status_code == 401
    assert r2.status_code == 401


# ---------------------------------------------------------------------------
# Reconcile pending donations cron
# ---------------------------------------------------------------------------


async def test_reconcile_marks_succeeded_donation_via_yookassa(db, monkeypatch):
    """Donation pending in our DB but YooKassa says succeeded → run handler."""
    from contextlib import asynccontextmanager

    from app.tasks import reconcile_pending_donations as task_mod

    user = await create_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)

    donation = Donation(
        id=uuid7(),
        user_id=user.id,
        campaign_id=campaign.id,
        foundation_id=foundation.id,
        amount_kopecks=10000,
        platform_fee_kopecks=300,
        nco_amount_kopecks=9700,
        idempotence_key=str(uuid7()),
        status=DonationStatus.pending,
        provider_payment_id="yk-payment-1",
    )
    db.add(donation)
    await db.flush()
    # Force created_at into the past so it crosses RECONCILE_MIN_AGE_MINUTES.
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Donation)
        .where(Donation.id == donation.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    )
    await db.flush()
    await db.refresh(donation)

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(task_mod, "async_session_factory", _factory)

    fake_yk_response = {
        "status": "succeeded",
        "metadata": {"type": "donation", "entity_id": str(donation.id)},
        "payment_method": None,
    }
    with patch(
        "app.tasks.reconcile_pending_donations.yookassa_client.get_payment",
        new=AsyncMock(return_value=fake_yk_response),
    ):
        result = await task_mod.reconcile_pending_donations()

    assert result["succeeded"] == 1
    await db.refresh(donation)
    assert donation.status == DonationStatus.success


async def test_reconcile_marks_canceled_donation(db, monkeypatch):
    from contextlib import asynccontextmanager

    from app.tasks import reconcile_pending_donations as task_mod

    user = await create_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)

    donation = Donation(
        id=uuid7(),
        user_id=user.id,
        campaign_id=campaign.id,
        foundation_id=foundation.id,
        amount_kopecks=5000,
        platform_fee_kopecks=150,
        nco_amount_kopecks=4850,
        idempotence_key=str(uuid7()),
        status=DonationStatus.pending,
        provider_payment_id="yk-payment-canceled",
    )
    db.add(donation)
    await db.flush()
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Donation)
        .where(Donation.id == donation.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    )
    await db.flush()

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(task_mod, "async_session_factory", _factory)

    with patch(
        "app.tasks.reconcile_pending_donations.yookassa_client.get_payment",
        new=AsyncMock(return_value={"status": "canceled", "cancellation_details": {"reason": "expired"}}),
    ):
        result = await task_mod.reconcile_pending_donations()

    assert result["failed"] == 1
    await db.refresh(donation)
    assert donation.status == DonationStatus.failed


async def test_reconcile_skips_fresh_donations(db, monkeypatch):
    """A donation < 5 minutes old must be left alone (let webhook do its job)."""
    from contextlib import asynccontextmanager

    from app.tasks import reconcile_pending_donations as task_mod

    user = await create_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)

    donation = Donation(
        id=uuid7(),
        user_id=user.id,
        campaign_id=campaign.id,
        foundation_id=foundation.id,
        amount_kopecks=5000,
        platform_fee_kopecks=150,
        nco_amount_kopecks=4850,
        idempotence_key=str(uuid7()),
        status=DonationStatus.pending,
        provider_payment_id="yk-fresh",
    )
    db.add(donation)
    await db.flush()  # created_at = now()

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(task_mod, "async_session_factory", _factory)

    yk_call = AsyncMock()
    with patch(
        "app.tasks.reconcile_pending_donations.yookassa_client.get_payment",
        new=yk_call,
    ):
        result = await task_mod.reconcile_pending_donations()

    yk_call.assert_not_called()
    assert result["inspected"] == 0
    await db.refresh(donation)
    assert donation.status == DonationStatus.pending


async def test_reconcile_marks_abandoned_after_max_age(db, monkeypatch):
    """Pending > 24h with YooKassa still pending → mark failed locally."""
    from contextlib import asynccontextmanager

    from app.tasks import reconcile_pending_donations as task_mod

    user = await create_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)

    donation = Donation(
        id=uuid7(),
        user_id=user.id,
        campaign_id=campaign.id,
        foundation_id=foundation.id,
        amount_kopecks=5000,
        platform_fee_kopecks=150,
        nco_amount_kopecks=4850,
        idempotence_key=str(uuid7()),
        status=DonationStatus.pending,
        provider_payment_id="yk-stale",
    )
    db.add(donation)
    await db.flush()
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Donation)
        .where(Donation.id == donation.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(days=2))
    )
    await db.flush()

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(task_mod, "async_session_factory", _factory)

    with patch(
        "app.tasks.reconcile_pending_donations.yookassa_client.get_payment",
        new=AsyncMock(return_value={"status": "pending"}),
    ):
        result = await task_mod.reconcile_pending_donations()

    assert result["abandoned"] == 1
    await db.refresh(donation)
    assert donation.status == DonationStatus.failed
