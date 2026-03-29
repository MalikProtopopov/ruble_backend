"""Tests for /api/v1/admin/achievements/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models import Achievement
from app.models.base import AchievementConditionType

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/achievements"


# ---- GET /api/v1/admin/achievements/ ----


async def test_list_achievements(client, db, admin_headers):
    resp = await client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert isinstance(body["data"], list)


# ---- POST /api/v1/admin/achievements/ ----


async def test_create_achievement(client, db, admin_headers):
    resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "code": "FIRST_DONATION",
            "title": "Первый шаг",
            "description": "Сделай первое пожертвование",
            "condition_type": "donations_count",
            "condition_value": 1,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == "FIRST_DONATION"
    assert body["title"] == "Первый шаг"
    assert body["condition_type"] == "donations_count"
    assert body["condition_value"] == 1
    assert body["is_active"] is True


async def test_create_achievement_duplicate_code(client, db, admin_headers):
    ach = Achievement(
        id=uuid7(),
        code="DUP_CODE",
        title="Test",
        condition_type=AchievementConditionType.donations_count,
        condition_value=1,
    )
    db.add(ach)
    await db.flush()

    resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "code": "DUP_CODE",
            "title": "Another",
            "condition_type": "donations_count",
            "condition_value": 2,
        },
    )
    assert resp.status_code == 409


# ---- PATCH /api/v1/admin/achievements/{id} ----


async def test_update_achievement(client, db, admin_headers):
    # Create first
    create_resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "code": "TO_UPDATE",
            "title": "Original Title",
            "condition_type": "streak_days",
            "condition_value": 7,
        },
    )
    assert create_resp.status_code == 201
    achievement_id = create_resp.json()["id"]

    # Update
    resp = await client.patch(
        f"{BASE}/{achievement_id}",
        headers=admin_headers,
        json={"title": "Updated Title", "is_active": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Updated Title"
    assert body["is_active"] is False


async def test_update_achievement_not_found(client, db, admin_headers):
    fake_id = uuid7()
    resp = await client.patch(
        f"{BASE}/{fake_id}",
        headers=admin_headers,
        json={"title": "Nope"},
    )
    assert resp.status_code == 404
