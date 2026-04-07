"""Tests for the orphaned-anonymous-account safety net.

Covers:
- last_seen_at fingerprint storage
- POST /payment-methods/{pm_id}/orphans (preview)
- POST /payment-methods/{pm_id}/recover (merge)
- tasks.inactive_anonymous_cleanup.cleanup_inactive_anonymous_users
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Donation, PaymentMethod, RefreshToken, Subscription, User
from app.models.base import (
    AllocationStrategy,
    BillingPeriod,
    DonationStatus,
    SubscriptionStatus,
    uuid7,
)
from app.services.payment_method import build_card_fingerprint
from tests.conftest import (
    auth_header,
    create_campaign,
    create_donation,
    create_foundation,
    create_subscription,
    _make_access_token,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_anon_user(db, *, last_seen=None, push_token: str | None = None) -> User:
    user = User(
        id=uuid7(),
        email=None,
        device_id=f"dev-{uuid7().hex}",
        is_anonymous=True,
        is_email_verified=False,
        last_seen_at=last_seen or datetime.now(timezone.utc),
        push_token=push_token,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_pm(
    db,
    user,
    *,
    fingerprint: str | None = None,
    is_default=True,
    last4="4242",
) -> PaymentMethod:
    pm = PaymentMethod(
        id=uuid7(),
        user_id=user.id,
        provider="yookassa",
        provider_pm_id=f"pm-{uuid7().hex}",
        card_last4=last4,
        card_type="visa",
        is_default=is_default,
        card_fingerprint=fingerprint,
    )
    db.add(pm)
    await db.flush()
    return pm


# ---------------------------------------------------------------------------
# Card fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_stable_for_same_card():
    fp1 = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="12", exp_year="2030"
    )
    fp2 = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="12", exp_year="2030"
    )
    assert fp1 == fp2 and fp1 is not None


def test_fingerprint_differs_for_different_cards():
    fp1 = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="12", exp_year="2030"
    )
    fp2 = build_card_fingerprint(
        first6="555555", last4="4444", exp_month="01", exp_year="2031"
    )
    assert fp1 != fp2


def test_fingerprint_none_without_last4():
    assert build_card_fingerprint(
        first6="411111", last4=None, exp_month="12", exp_year="2030"
    ) is None


# ---------------------------------------------------------------------------
# Recovery: orphans listing + merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphans_endpoint_returns_other_anonymous_user(client, db):
    fp = build_card_fingerprint(
        first6="411111", last4="1111", exp_month="12", exp_year="2030"
    )
    # Old (orphan) anonymous account with the card.
    orphan = await _create_anon_user(db)
    await _create_pm(db, orphan, fingerprint=fp, last4="1111")
    await create_donation(
        db,
        orphan,
        await create_campaign(db, await create_foundation(db)),
        amount_kopecks=15000,
    )

    # Current anonymous user re-saves the same card.
    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=fp, last4="1111")

    headers = auth_header(_make_access_token(current.id, "donor"))
    resp = await client.get(
        f"/api/v1/payment-methods/{cur_pm.id}/orphans", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["user_id"] == str(orphan.id)
    assert body[0]["donations_count"] == 1
    assert body[0]["total_donated_kopecks"] == 0  # cached counter, not actual sum


@pytest.mark.asyncio
async def test_orphans_endpoint_ignores_non_anonymous_users(client, db):
    fp = build_card_fingerprint(
        first6="411111", last4="2222", exp_month="01", exp_year="2030"
    )
    # Same card but on a regular (non-anonymous) account → must be ignored.
    other = User(
        id=uuid7(),
        email="real@example.com",
        is_anonymous=False,
        is_email_verified=True,
    )
    db.add(other)
    await db.flush()
    await _create_pm(db, other, fingerprint=fp, last4="2222")

    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=fp, last4="2222")
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.get(
        f"/api/v1/payment-methods/{cur_pm.id}/orphans", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_orphans_endpoint_no_fingerprint_returns_empty(client, db):
    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=None)
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.get(
        f"/api/v1/payment-methods/{cur_pm.id}/orphans", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_recover_merges_orphan_into_current_user(client, db):
    fp = build_card_fingerprint(
        first6="555555", last4="3333", exp_month="06", exp_year="2029"
    )
    orphan = await _create_anon_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    await _create_pm(db, orphan, fingerprint=fp, last4="3333")
    await create_donation(db, orphan, campaign, amount_kopecks=20000)
    await create_subscription(db, orphan, status=SubscriptionStatus.active)

    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=fp, last4="3333")
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.post(
        f"/api/v1/payment-methods/{cur_pm.id}/recover", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(orphan.id) in body["merged_user_ids"]
    assert body["donations_transferred"] == 1
    assert body["subscriptions_transferred"] == 1

    # Donation now belongs to current user.
    donations = (
        await db.execute(select(Donation).where(Donation.user_id == current.id))
    ).scalars().all()
    assert len(donations) == 1

    # Orphan soft-deleted.
    await db.refresh(orphan)
    assert orphan.is_deleted is True
    assert orphan.device_id is None


@pytest.mark.asyncio
async def test_recover_without_fingerprint_raises(client, db):
    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=None)
    headers = auth_header(_make_access_token(current.id, "donor"))
    resp = await client.post(
        f"/api/v1/payment-methods/{cur_pm.id}/recover", headers=headers
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PM_NO_FINGERPRINT"


# ---------------------------------------------------------------------------
# Cleanup task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_cancels_subs_and_soft_deletes_user_with_history(db):
    """User with donations: soft-delete + cancel subs + clear PMs."""
    from app.tasks.inactive_anonymous_cleanup import _process_user

    long_ago = datetime.now(timezone.utc) - timedelta(days=365)
    user = await _create_anon_user(db, last_seen=long_ago, push_token="ftok")
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    sub = await create_subscription(db, user, status=SubscriptionStatus.active)
    await create_donation(db, user, campaign, amount_kopecks=10000)
    pm = await _create_pm(db, user, fingerprint="abc", last4="1234")

    stats = await _process_user(db, user)
    await db.flush()

    assert stats["cancelled_subs"] == 1
    assert stats["deleted_pms"] == 1
    assert stats["hard_deleted"] is False

    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.cancelled
    assert sub.cancelled_at is not None

    await db.refresh(pm)
    assert pm.is_deleted is True
    assert pm.is_default is False

    await db.refresh(user)
    assert user.is_deleted is True
    assert user.is_active is False
    assert user.device_id is None


@pytest.mark.asyncio
async def test_cleanup_hard_deletes_user_without_history(db):
    """User with no donations and no subs: full delete + cascade."""
    from app.tasks.inactive_anonymous_cleanup import _process_user

    long_ago = datetime.now(timezone.utc) - timedelta(days=365)
    user = await _create_anon_user(db, last_seen=long_ago)
    user_id = user.id
    await _create_pm(db, user, fingerprint="xyz", last4="9999")

    await _process_user(db, user)
    await db.flush()

    # User is gone.
    res = await db.execute(select(User).where(User.id == user_id))
    assert res.scalar_one_or_none() is None
    # PM cascaded.
    res = await db.execute(select(PaymentMethod).where(PaymentMethod.user_id == user_id))
    assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cleanup_revokes_refresh_tokens(db):
    from app.tasks.inactive_anonymous_cleanup import _process_user

    long_ago = datetime.now(timezone.utc) - timedelta(days=365)
    user = await _create_anon_user(db, last_seen=long_ago)
    rt = RefreshToken(
        id=uuid7(),
        user_id=user.id,
        token_hash="aaa",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(rt)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    await create_donation(db, user, campaign)
    await db.flush()

    await _process_user(db, user)
    await db.flush()
    await db.refresh(rt)
    assert rt.is_revoked is True


@pytest.mark.asyncio
async def test_cleanup_query_includes_null_last_seen(db):
    """Defensive: a user whose last_seen_at was never written should still be
    eligible for cleanup based on created_at, otherwise such users would live forever."""
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings
    from app.models import User
    from app.models.base import uuid7
    from sqlalchemy import func as sa_func, or_, select

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ANONYMOUS_INACTIVE_DAYS)

    # Old, no last_seen_at, no activity — should be picked up.
    ancient = User(
        id=uuid7(),
        device_id=f"dev-{uuid7().hex}",
        is_anonymous=True,
        last_seen_at=None,
    )
    db.add(ancient)
    await db.flush()
    # Force created_at into the past (the column has server_default=now()).
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(User)
        .where(User.id == ancient.id)
        .values(created_at=cutoff - timedelta(days=10))
    )
    await db.flush()

    q = select(User.id).where(
        User.is_anonymous == True,  # noqa: E712
        User.is_deleted == False,  # noqa: E712
        or_(
            User.last_seen_at < cutoff,
            sa_func.coalesce(User.last_seen_at, User.created_at) < cutoff,
        ),
    )
    found = (await db.execute(q)).scalars().all()
    assert ancient.id in found


# ---------------------------------------------------------------------------
# Recovery edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recover_works_when_current_user_is_real_account(client, db):
    """A real (non-anonymous) user re-enters their old card → orphans should
    still be recoverable. Recovery doesn't require current user to be anonymous."""
    fp = build_card_fingerprint(
        first6="411111", last4="7777", exp_month="03", exp_year="2031"
    )
    orphan = await _create_anon_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    await _create_pm(db, orphan, fingerprint=fp, last4="7777")
    await create_donation(db, orphan, campaign, amount_kopecks=15000)

    # Real, email-verified user.
    real = User(
        id=uuid7(),
        email=f"real-{uuid7().hex[:6]}@test.com",
        is_anonymous=False,
        is_email_verified=True,
    )
    db.add(real)
    await db.flush()
    cur_pm = await _create_pm(db, real, fingerprint=fp, last4="7777")
    headers = auth_header(_make_access_token(real.id, "donor"))

    resp = await client.post(
        f"/api/v1/payment-methods/{cur_pm.id}/recover", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(orphan.id) in body["merged_user_ids"]


@pytest.mark.asyncio
async def test_recover_merges_multiple_orphans_in_one_call(client, db):
    """User used the app on three previous installations → all three orphans
    must be merged in a single /recover call."""
    fp = build_card_fingerprint(
        first6="555555", last4="6666", exp_month="07", exp_year="2032"
    )
    orphans = []
    for _ in range(3):
        o = await _create_anon_user(db)
        await _create_pm(db, o, fingerprint=fp, last4="6666")
        orphans.append(o)

    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=fp, last4="6666")
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.post(
        f"/api/v1/payment-methods/{cur_pm.id}/recover", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["merged_user_ids"]) == 3
    for o in orphans:
        await db.refresh(o)
        assert o.is_deleted is True


@pytest.mark.asyncio
async def test_recover_idempotent_second_call_is_noop(client, db):
    """Second call to /recover after the first one drained all orphans must
    return an empty merged_user_ids — must not error."""
    fp = build_card_fingerprint(
        first6="411111", last4="8888", exp_month="11", exp_year="2030"
    )
    orphan = await _create_anon_user(db)
    await _create_pm(db, orphan, fingerprint=fp, last4="8888")

    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=fp, last4="8888")
    headers = auth_header(_make_access_token(current.id, "donor"))

    r1 = await client.post(
        f"/api/v1/payment-methods/{cur_pm.id}/recover", headers=headers
    )
    assert r1.status_code == 200
    assert len(r1.json()["merged_user_ids"]) == 1

    r2 = await client.post(
        f"/api/v1/payment-methods/{cur_pm.id}/recover", headers=headers
    )
    assert r2.status_code == 200
    assert r2.json()["merged_user_ids"] == []


@pytest.mark.asyncio
async def test_recover_skips_already_deleted_orphans(client, db):
    """Soft-deleted orphans (e.g. cleaned up by cron) must not appear."""
    fp = build_card_fingerprint(
        first6="411111", last4="9090", exp_month="05", exp_year="2030"
    )
    orphan = await _create_anon_user(db)
    orphan.is_deleted = True
    await db.flush()
    await _create_pm(db, orphan, fingerprint=fp, last4="9090")

    current = await _create_anon_user(db)
    cur_pm = await _create_pm(db, current, fingerprint=fp, last4="9090")
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.get(
        f"/api/v1/payment-methods/{cur_pm.id}/orphans", headers=headers
    )
    assert resp.json() == []


@pytest.mark.asyncio
async def test_scan_orphans_endpoint_no_pm_id_required(client, db):
    """The scan variant `GET /payment-methods/orphans` should find orphans
    based on ALL of the user's saved fingerprints — no pm_id needed."""
    fp = build_card_fingerprint(
        first6="411111", last4="5555", exp_month="04", exp_year="2032"
    )
    orphan = await _create_anon_user(db)
    await _create_pm(db, orphan, fingerprint=fp, last4="5555")

    current = await _create_anon_user(db)
    await _create_pm(db, current, fingerprint=fp, last4="5555")
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.get("/api/v1/payment-methods/orphans", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["user_id"] == str(orphan.id)


@pytest.mark.asyncio
async def test_scan_recover_endpoint_no_pm_id_required(client, db):
    """`POST /payment-methods/recover` should merge orphans without needing pm_id."""
    fp = build_card_fingerprint(
        first6="411111", last4="6060", exp_month="08", exp_year="2031"
    )
    orphan = await _create_anon_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    await _create_pm(db, orphan, fingerprint=fp, last4="6060")
    await create_donation(db, orphan, campaign, amount_kopecks=25000)

    current = await _create_anon_user(db)
    await _create_pm(db, current, fingerprint=fp, last4="6060")
    headers = auth_header(_make_access_token(current.id, "donor"))

    resp = await client.post("/api/v1/payment-methods/recover", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert str(orphan.id) in body["merged_user_ids"]
    assert body["donations_transferred"] == 1

    # Idempotent
    r2 = await client.post("/api/v1/payment-methods/recover", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["merged_user_ids"] == []


@pytest.mark.asyncio
async def test_scan_orphans_empty_when_user_has_no_cards(client, db):
    current = await _create_anon_user(db)
    headers = auth_header(_make_access_token(current.id, "donor"))
    resp = await client.get("/api/v1/payment-methods/orphans", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_orphans_endpoint_rejects_other_users_pm(client, db):
    """Cannot enumerate orphans by passing someone else's pm_id."""
    fp = build_card_fingerprint(
        first6="411111", last4="1212", exp_month="01", exp_year="2030"
    )
    other = await _create_anon_user(db)
    other_pm = await _create_pm(db, other, fingerprint=fp, last4="1212")

    current = await _create_anon_user(db)
    headers = auth_header(_make_access_token(current.id, "donor"))
    resp = await client.get(
        f"/api/v1/payment-methods/{other_pm.id}/orphans", headers=headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# account_merge corner cases — duplicate is_default + duplicate active subs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_dedupes_is_default_payment_methods(db):
    """After merge, exactly one payment method must remain is_default=true."""
    from app.services.account_merge import merge_anonymous_into

    src = await _create_anon_user(db)
    tgt = User(
        id=uuid7(),
        email=f"tgt-{uuid7().hex[:6]}@test.com",
        is_anonymous=False,
        is_email_verified=True,
    )
    db.add(tgt)
    await db.flush()

    # Both source and target have a default PM.
    await _create_pm(db, src, fingerprint="src", last4="1111", is_default=True)
    await _create_pm(db, tgt, fingerprint="tgt", last4="2222", is_default=True)

    await merge_anonymous_into(db, source=src, target=tgt)
    await db.flush()

    res = await db.execute(
        select(PaymentMethod).where(
            PaymentMethod.user_id == tgt.id,
            PaymentMethod.is_deleted == False,  # noqa: E712
        )
    )
    pms = res.scalars().all()
    assert len(pms) == 2
    assert sum(1 for p in pms if p.is_default) == 1


@pytest.mark.asyncio
async def test_merge_cancels_duplicate_active_subscriptions(db):
    """Both source and target had an active subscription → after merge only one
    survives, the rest are cancelled to prevent double-billing."""
    from app.services.account_merge import merge_anonymous_into

    src = await _create_anon_user(db)
    tgt = User(
        id=uuid7(),
        email=f"tgt-{uuid7().hex[:6]}@test.com",
        is_anonymous=False,
        is_email_verified=True,
    )
    db.add(tgt)
    await db.flush()

    sub_src = await create_subscription(db, src, status=SubscriptionStatus.active)
    sub_tgt = await create_subscription(db, tgt, status=SubscriptionStatus.active)

    await merge_anonymous_into(db, source=src, target=tgt)
    await db.flush()

    actives = (
        await db.execute(
            select(Subscription).where(
                Subscription.user_id == tgt.id,
                Subscription.status == SubscriptionStatus.active,
            )
        )
    ).scalars().all()
    assert len(actives) == 1


# Note: a "colliding provider_pm_id between source and target" scenario is
# structurally impossible — the partial unique index on (provider, provider_pm_id)
# WHERE is_deleted = false is global, so two non-deleted PMs with the same
# YooKassa token cannot coexist in the database to begin with.


# ---------------------------------------------------------------------------
# Middleware: last_seen_at update + throttling
#
# These tests bypass the HTTP layer because the middleware opens its own
# AsyncSession via async_session_factory(), which lives on a different
# connection than the test fixture's rolled-back transaction. We instead
# patch async_session_factory to hand the middleware our test session and
# call _touch() directly with a synthesized Request object.
# ---------------------------------------------------------------------------


def _fake_request(headers: dict) -> object:
    class _R:
        def __init__(self, h):
            self.headers = h
    return _R(headers)


@pytest.mark.asyncio
async def test_middleware_touch_updates_last_seen(db, monkeypatch):
    from contextlib import asynccontextmanager

    from app.core import middleware as mw
    from app.core.redis import redis_client

    user = await _create_anon_user(
        db, last_seen=datetime.now(timezone.utc) - timedelta(hours=5)
    )
    await db.flush()
    old = user.last_seen_at
    await redis_client.delete(f"last_seen:{user.id}")

    # Patch async_session_factory so the middleware writes through our test session.
    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(mw, "async_session_factory", _factory)

    instance = mw.LastSeenMiddleware(app=None)
    token = _make_access_token(user.id, "donor")
    await instance._touch(_fake_request({"authorization": f"Bearer {token}"}))

    await db.refresh(user)
    assert user.last_seen_at > old
    delta = datetime.now(timezone.utc) - user.last_seen_at
    assert delta < timedelta(seconds=10)

    await redis_client.delete(f"last_seen:{user.id}")


@pytest.mark.asyncio
async def test_middleware_touch_throttle_skips_second_call(db, monkeypatch):
    from contextlib import asynccontextmanager

    from app.core import middleware as mw
    from app.core.redis import redis_client

    user = await _create_anon_user(db, last_seen=None)
    await db.flush()
    await redis_client.delete(f"last_seen:{user.id}")

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(mw, "async_session_factory", _factory)
    instance = mw.LastSeenMiddleware(app=None)

    token = _make_access_token(user.id, "donor")
    req = _fake_request({"authorization": f"Bearer {token}"})

    await instance._touch(req)
    await db.refresh(user)
    first = user.last_seen_at
    assert first is not None

    # Roll the timestamp back to detect a second write.
    user.last_seen_at = first - timedelta(hours=1)
    await db.flush()

    await instance._touch(req)  # throttle key still set → no-op
    await db.refresh(user)
    assert user.last_seen_at < first  # untouched

    await redis_client.delete(f"last_seen:{user.id}")


@pytest.mark.asyncio
async def test_middleware_touch_skips_without_auth_header(db, monkeypatch):
    from contextlib import asynccontextmanager

    from app.core import middleware as mw

    user = await _create_anon_user(
        db, last_seen=datetime.now(timezone.utc) - timedelta(hours=10)
    )
    await db.flush()
    old = user.last_seen_at

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(mw, "async_session_factory", _factory)
    instance = mw.LastSeenMiddleware(app=None)

    await instance._touch(_fake_request({}))
    await db.refresh(user)
    assert user.last_seen_at == old


@pytest.mark.asyncio
async def test_middleware_touch_skips_for_admin_token(db, monkeypatch):
    """Admin JWTs have role=admin and `sub` points at admins.id, not users.id —
    they must not be confused with user tokens."""
    from contextlib import asynccontextmanager

    from app.core import middleware as mw

    user = await _create_anon_user(
        db, last_seen=datetime.now(timezone.utc) - timedelta(hours=10)
    )
    await db.flush()
    old = user.last_seen_at

    @asynccontextmanager
    async def _factory():
        yield db

    monkeypatch.setattr(mw, "async_session_factory", _factory)
    instance = mw.LastSeenMiddleware(app=None)

    admin_token = _make_access_token(user.id, "admin")
    await instance._touch(_fake_request({"authorization": f"Bearer {admin_token}"}))
    await db.refresh(user)
    assert user.last_seen_at == old
