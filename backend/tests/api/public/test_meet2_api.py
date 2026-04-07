"""Tests for the meet2 backend changes:

- POST /auth/device-register
- POST /auth/link-email/verify-otp (link + merge)
- Donation cooldown (429)
- GET /campaigns with per-user fields and sort
- GET /campaigns/today
- GET /subscriptions/active
- GET/DELETE/POST /payment-methods + saved-card donation
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select

from app.models import OTPCode, PaymentMethod, User
from app.models.base import (
    AllocationStrategy,
    BillingPeriod,
    DonationStatus,
    SubscriptionStatus,
    uuid7,
)
from tests.conftest import (
    auth_header,
    create_campaign,
    create_donation,
    create_foundation,
    create_subscription,
    create_user,
    _make_access_token,
)

_ph = PasswordHasher()
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# device-register
# ---------------------------------------------------------------------------


async def test_device_register_creates_anonymous_user(client, db):
    device_id = f"dev-{uuid7().hex}"
    resp = await client.post(
        "/api/v1/auth/device-register",
        json={"device_id": device_id, "timezone": "Europe/Moscow"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["is_anonymous"] is True
    assert body["user"]["is_email_verified"] is False
    assert body["user"]["email"] is None
    assert body["user"]["is_new"] is True


async def test_device_register_is_idempotent(client, db):
    device_id = f"dev-{uuid7().hex}"
    r1 = await client.post(
        "/api/v1/auth/device-register",
        json={"device_id": device_id},
    )
    r2 = await client.post(
        "/api/v1/auth/device-register",
        json={"device_id": device_id},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["user"]["id"] == r2.json()["user"]["id"]
    assert r2.json()["user"]["is_new"] is False


async def test_device_register_short_device_id_rejected(client):
    resp = await client.post(
        "/api/v1/auth/device-register",
        json={"device_id": "short"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# link-email / merge
# ---------------------------------------------------------------------------


async def _create_otp(db, email: str, code: str = "654321"):
    otp = OTPCode(
        id=uuid7(),
        email=email,
        code_hash=_ph.hash(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(otp)
    await db.flush()
    return otp


async def test_link_email_attaches_to_anonymous_user(client, db):
    # 1. anonymous user via device-register
    device_id = f"dev-{uuid7().hex}"
    reg = await client.post("/api/v1/auth/device-register", json={"device_id": device_id})
    token = reg.json()["access_token"]

    email = f"link-{uuid7().hex[:6]}@test.com"
    await _create_otp(db, email, "111111")

    resp = await client.post(
        "/api/v1/auth/link-email/verify-otp",
        json={"email": email, "code": "111111"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merged"] is False
    assert body["user"]["email"] == email
    assert body["user"]["is_anonymous"] is False
    assert body["user"]["is_email_verified"] is True


async def test_link_email_existing_email_requires_explicit_merge(client, db):
    # Pre-existing real user
    target = await create_user(db, email="taken@meet2.example.com")

    # New anonymous device
    device_id = f"dev-{uuid7().hex}"
    reg = await client.post("/api/v1/auth/device-register", json={"device_id": device_id})
    token = reg.json()["access_token"]

    await _create_otp(db, "taken@meet2.example.com", "222222")

    # Without allow_merge — must fail
    resp = await client.post(
        "/api/v1/auth/link-email/verify-otp",
        json={"email": "taken@meet2.example.com", "code": "222222"},
        headers=auth_header(token),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "EMAIL_ALREADY_LINKED"
    assert body["error"]["details"]["target_user_id"] == str(target.id)


async def test_link_email_merge_transfers_donations(client, db, foundation):
    # 1. Pre-existing real user with one donation
    target = await create_user(db, email="merge-target@meet2.example.com")
    campaign = await create_campaign(db, foundation)
    target_donation = await create_donation(db, target, campaign, amount_kopecks=5000)

    # 2. Anonymous device with its own donation
    device_id = f"dev-{uuid7().hex}"
    reg = await client.post("/api/v1/auth/device-register", json={"device_id": device_id})
    src_id = reg.json()["user"]["id"]
    token = reg.json()["access_token"]

    src_user_result = await db.execute(select(User).where(User.id == src_id))
    src = src_user_result.scalar_one()
    src_donation = await create_donation(db, src, campaign, amount_kopecks=3000)

    # 3. Send OTP, link with allow_merge=true
    await _create_otp(db, "merge-target@meet2.example.com", "333333")
    resp = await client.post(
        "/api/v1/auth/link-email/verify-otp",
        json={
            "email": "merge-target@meet2.example.com",
            "code": "333333",
            "allow_merge": True,
        },
        headers=auth_header(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["merged"] is True
    assert body["user"]["id"] == str(target.id)

    # 4. Both donations now belong to target.
    from app.models import Donation

    after = await db.execute(
        select(Donation).where(Donation.id.in_([src_donation.id, target_donation.id]))
    )
    rows = list(after.scalars().all())
    assert {str(d.user_id) for d in rows} == {str(target.id)}

    # 5. Source user is soft-deleted.
    await db.refresh(src)
    assert src.is_deleted is True
    assert src.is_active is False
    assert src.device_id is None


# ---------------------------------------------------------------------------
# Donation cooldown
# ---------------------------------------------------------------------------


async def test_donation_cooldown_blocks_repeat(client, db, user, donor_headers, campaign):
    # First donation succeeds.
    r1 = await client.post(
        "/api/v1/donations",
        json={"campaign_id": str(campaign.id), "amount_kopecks": 5000},
        headers=donor_headers,
    )
    assert r1.status_code == 201

    # Second donation immediately after — must hit cooldown.
    r2 = await client.post(
        "/api/v1/donations",
        json={"campaign_id": str(campaign.id), "amount_kopecks": 5000},
        headers=donor_headers,
    )
    assert r2.status_code == 429
    body = r2.json()
    assert body["error"]["code"] == "DONATION_COOLDOWN"
    details = body["error"]["details"]
    assert details["retry_after"] > 0
    assert "next_available_at" in details


async def test_donation_cooldown_allows_after_window(client, db, user, donor_headers, campaign):
    """An old success donation does not block a new one."""
    old = await create_donation(db, user, campaign, status=DonationStatus.success)
    # Move it into the past beyond cooldown
    old.created_at = datetime.now(timezone.utc) - timedelta(hours=24)
    await db.flush()

    resp = await client.post(
        "/api/v1/donations",
        json={"campaign_id": str(campaign.id), "amount_kopecks": 5000},
        headers=donor_headers,
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Campaigns with per-user fields
# ---------------------------------------------------------------------------


async def test_campaigns_list_anonymous_no_user_fields(client, db, campaign):
    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 200
    body = resp.json()
    item = next(c for c in body["data"] if c["id"] == str(campaign.id))
    assert item["donated_today"] is None
    assert item["last_donation"] is None
    assert item["next_available_at"] is None


async def test_campaigns_list_authorized_with_donation(client, db, user, donor_headers, campaign):
    await create_donation(db, user, campaign, status=DonationStatus.success)

    resp = await client.get("/api/v1/campaigns", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    item = next(c for c in body["data"] if c["id"] == str(campaign.id))
    assert item["donated_today"] is True
    assert item["has_any_donation"] is True
    assert item["last_donation"] is not None
    assert item["last_donation"]["status"] == "success"
    # next_available_at should be set (cooldown not yet passed)
    assert item["next_available_at"] is not None


async def test_campaigns_list_sort_helped_today(client, db, user, donor_headers, foundation):
    helped = await create_campaign(db, foundation, title="Helped today", urgency_level=1)
    other = await create_campaign(db, foundation, title="Untouched", urgency_level=5)
    await create_donation(db, user, helped, status=DonationStatus.success)

    resp = await client.get(
        "/api/v1/campaigns?sort=helped_today",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    items = resp.json()["data"]
    # Helped campaign must rank above the other one despite lower urgency.
    helped_idx = next(i for i, c in enumerate(items) if c["id"] == str(helped.id))
    other_idx = next(i for i, c in enumerate(items) if c["id"] == str(other.id))
    assert helped_idx < other_idx


async def test_campaigns_today_returns_three(client, db, foundation, donor_headers):
    for i in range(5):
        await create_campaign(db, foundation, title=f"Camp {i}", urgency_level=5 - (i % 5))

    resp = await client.get("/api/v1/campaigns/today", headers=donor_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) <= 3


# ---------------------------------------------------------------------------
# /subscriptions/active
# ---------------------------------------------------------------------------


async def test_subscriptions_active_none(client, db, donor_headers):
    resp = await client.get("/api/v1/subscriptions/active", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_active"] is False
    assert body["subscription"] is None


async def test_subscriptions_active_returns_active_one(client, db, user, donor_headers):
    await create_subscription(db, user, status=SubscriptionStatus.active)
    resp = await client.get("/api/v1/subscriptions/active", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_active"] is True
    assert body["subscription"] is not None


# ---------------------------------------------------------------------------
# Saved payment methods
# ---------------------------------------------------------------------------


async def _create_pm(db, user, *, is_default=True, last4="4242"):
    pm = PaymentMethod(
        id=uuid7(),
        user_id=user.id,
        provider="yookassa",
        provider_pm_id=f"pm-{uuid7().hex}",
        card_last4=last4,
        card_type="visa",
        is_default=is_default,
    )
    db.add(pm)
    await db.flush()
    return pm


async def test_payment_methods_list_empty(client, donor_headers):
    resp = await client.get("/api/v1/payment-methods", headers=donor_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_payment_methods_list_returns_user_cards_only(client, db, user, donor_headers):
    other = await create_user(db, email="other-pm@test.com")
    await _create_pm(db, user, last4="1111")
    await _create_pm(db, other, last4="9999", is_default=False)

    resp = await client.get("/api/v1/payment-methods", headers=donor_headers)
    items = resp.json()
    assert len(items) == 1
    assert items[0]["card_last4"] == "1111"


async def test_payment_methods_set_default(client, db, user, donor_headers):
    pm1 = await _create_pm(db, user, is_default=True, last4="1111")
    pm2 = await _create_pm(db, user, is_default=False, last4="2222")

    resp = await client.post(
        f"/api/v1/payment-methods/{pm2.id}/set-default",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    await db.refresh(pm1)
    await db.refresh(pm2)
    assert pm2.is_default is True
    assert pm1.is_default is False


async def test_payment_methods_delete_promotes_another(client, db, user, donor_headers):
    pm1 = await _create_pm(db, user, is_default=True, last4="1111")
    pm2 = await _create_pm(db, user, is_default=False, last4="2222")

    resp = await client.delete(
        f"/api/v1/payment-methods/{pm1.id}",
        headers=donor_headers,
    )
    assert resp.status_code == 204
    await db.refresh(pm2)
    assert pm2.is_default is True


async def test_donation_with_saved_payment_method(client, db, user, donor_headers, campaign):
    pm = await _create_pm(db, user, last4="4242")
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": str(campaign.id),
            "amount_kopecks": 5000,
            "payment_method_id": str(pm.id),
        },
        headers=donor_headers,
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Profile productisation
# ---------------------------------------------------------------------------


async def test_profile_returns_meet2_flags(client, db, user, donor_headers):
    resp = await client.get("/api/v1/me", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "is_anonymous" in body
    assert "is_email_verified" in body
    assert "donation_cooldown_hours" in body
    assert body["donation_cooldown_hours"] >= 1
    assert "push_on_donation_reminder" in body["notification_preferences"]


async def test_profile_for_anonymous_user(client, db):
    device_id = f"dev-{uuid7().hex}"
    reg = await client.post("/api/v1/auth/device-register", json={"device_id": device_id})
    token = reg.json()["access_token"]
    resp = await client.get("/api/v1/me", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_anonymous"] is True
    assert body["email"] is None


# ---------------------------------------------------------------------------
# Campaign detail per-user fields
# ---------------------------------------------------------------------------


async def test_campaign_detail_anonymous_no_user_fields(client, campaign):
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["donated_today"] is None
    assert body["last_donation"] is None
    assert body["cooldown_hours"] >= 1


async def test_campaign_detail_authorized_with_donation(client, db, user, donor_headers, campaign):
    await create_donation(db, user, campaign, status=DonationStatus.success)
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=donor_headers)
    body = resp.json()
    assert body["donated_today"] is True
    assert body["has_any_donation"] is True
    assert body["last_donation"] is not None
    assert body["next_available_at"] is not None


# ---------------------------------------------------------------------------
# Merge preview details
# ---------------------------------------------------------------------------


async def test_link_email_conflict_returns_merge_preview(client, db, foundation):
    target = await create_user(db, email="preview-target@meet2.example.com")

    device_id = f"dev-{uuid7().hex}"
    reg = await client.post("/api/v1/auth/device-register", json={"device_id": device_id})
    token = reg.json()["access_token"]
    src_id = reg.json()["user"]["id"]

    # Anonymous user makes one donation so the preview shows non-zero counts.
    src_user = (await db.execute(select(User).where(User.id == src_id))).scalar_one()
    campaign = await create_campaign(db, foundation)
    await create_donation(db, src_user, campaign, amount_kopecks=7000)
    src_user.total_donated_kopecks = 7000
    await db.flush()

    await _create_otp(db, "preview-target@meet2.example.com", "444444")
    resp = await client.post(
        "/api/v1/auth/link-email/verify-otp",
        json={"email": "preview-target@meet2.example.com", "code": "444444"},
        headers=auth_header(token),
    )
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert details["target_user_id"] == str(target.id)
    assert details["source_donations_count"] == 1
    assert details["source_total_donated_kopecks"] == 7000


async def test_donation_with_other_users_payment_method_404(client, db, donor_headers, campaign):
    other = await create_user(db, email="other-pm-2@test.com")
    pm = await _create_pm(db, other)
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": str(campaign.id),
            "amount_kopecks": 5000,
            "payment_method_id": str(pm.id),
        },
        headers=donor_headers,
    )
    assert resp.status_code == 404
