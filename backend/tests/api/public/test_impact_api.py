"""Tests for /api/v1/impact/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models import Achievement, UserAchievement
from app.models.base import AchievementConditionType

pytestmark = pytest.mark.asyncio


# ---- GET /api/v1/impact/ ----


async def test_get_impact(client, db, user, donor_headers):
    # Set cached impact fields on the user
    user.total_donated_kopecks = 50000
    user.current_streak_days = 7
    user.total_donations_count = 12
    await db.flush()

    resp = await client.get("/api/v1/impact", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_donated_kopecks"] == 50000
    assert body["streak_days"] == 7
    assert body["donations_count"] == 12


async def test_get_impact_unauthorized(client):
    resp = await client.get("/api/v1/impact")
    assert resp.status_code == 401


# ---- GET /api/v1/impact/achievements ----


async def test_get_achievements(client, db, user, donor_headers):
    ach = Achievement(
        id=uuid7(),
        code="STREAK_7",
        title="7-day streak",
        condition_type=AchievementConditionType.streak_days,
        condition_value=7,
        is_active=True,
    )
    db.add(ach)
    await db.flush()

    resp = await client.get("/api/v1/impact/achievements", headers=donor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    item = [a for a in data if a["code"] == "STREAK_7"][0]
    assert item["earned_at"] is None


async def test_get_achievements_with_earned(client, db, user, donor_headers):
    ach = Achievement(
        id=uuid7(),
        code="FIRST_DONATION",
        title="First step",
        condition_type=AchievementConditionType.donations_count,
        condition_value=1,
        is_active=True,
    )
    db.add(ach)
    await db.flush()

    ua = UserAchievement(id=uuid7(), user_id=user.id, achievement_id=ach.id)
    db.add(ua)
    await db.flush()

    resp = await client.get("/api/v1/impact/achievements", headers=donor_headers)
    assert resp.status_code == 200
    data = resp.json()
    earned = [a for a in data if a["code"] == "FIRST_DONATION"]
    assert len(earned) == 1
    assert earned[0]["earned_at"] is not None
