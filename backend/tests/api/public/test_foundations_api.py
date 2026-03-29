"""Tests for /api/v1/foundations/ endpoints."""

import pytest
from app.models.base import uuid7

pytestmark = pytest.mark.asyncio


async def test_get_foundation_public(client, foundation):
    resp = await client.get(f"/api/v1/foundations/{str(foundation.id)}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(foundation.id)
    assert body["name"] == foundation.name
    assert "status" in body


async def test_get_foundation_not_found(client):
    fake_id = str(uuid7())
    resp = await client.get(f"/api/v1/foundations/{fake_id}")
    assert resp.status_code == 404


async def test_get_foundation_has_no_sensitive_fields(client, foundation):
    resp = await client.get(f"/api/v1/foundations/{str(foundation.id)}")
    assert resp.status_code == 200
    body = resp.json()
    assert "inn" not in body
    assert "legal_name" not in body
