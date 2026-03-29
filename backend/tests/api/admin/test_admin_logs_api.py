"""Tests for /api/v1/admin/logs/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models import AllocationChange, NotificationLog
from app.models.base import AllocationChangeReason, NotificationStatus
from tests.conftest import create_subscription

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/logs"


# ---- GET /api/v1/admin/logs/allocation-logs ----


async def test_list_allocation_logs(client, db, admin_headers, user, foundation, campaign):
    sub = await create_subscription(db, user)
    change = AllocationChange(
        id=uuid7(),
        subscription_id=sub.id,
        from_campaign_id=None,
        to_campaign_id=campaign.id,
        reason=AllocationChangeReason.campaign_completed,
    )
    db.add(change)
    await db.flush()

    resp = await client.get(f"{BASE}/allocation-logs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) >= 1
    assert body["data"][0]["reason"] == "campaign_completed"


async def test_list_allocation_logs_filter(client, db, admin_headers, user, foundation, campaign):
    sub = await create_subscription(db, user)
    change = AllocationChange(
        id=uuid7(),
        subscription_id=sub.id,
        from_campaign_id=None,
        to_campaign_id=campaign.id,
        reason=AllocationChangeReason.manual_by_admin,
    )
    db.add(change)
    await db.flush()

    resp = await client.get(
        f"{BASE}/allocation-logs",
        headers=admin_headers,
        params={"subscription_id": str(sub.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    for item in body["data"]:
        assert item["subscription_id"] == str(sub.id)


# ---- GET /api/v1/admin/logs/notification-logs ----


async def test_list_notification_logs(client, db, admin_headers, user):
    log = NotificationLog(
        id=uuid7(),
        user_id=user.id,
        notification_type="donation_success",
        title="Спасибо!",
        body="Ваше пожертвование прошло успешно",
        status=NotificationStatus.sent,
    )
    db.add(log)
    await db.flush()

    resp = await client.get(f"{BASE}/notification-logs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) >= 1


async def test_list_notification_logs_filter(client, db, admin_headers, user):
    log = NotificationLog(
        id=uuid7(),
        user_id=user.id,
        notification_type="subscription_reminder",
        title="Напоминание",
        body="Скоро списание подписки",
        status=NotificationStatus.mock,
    )
    db.add(log)
    await db.flush()

    resp = await client.get(
        f"{BASE}/notification-logs",
        headers=admin_headers,
        params={"notification_type": "subscription_reminder"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    for item in body["data"]:
        assert item["notification_type"] == "subscription_reminder"
