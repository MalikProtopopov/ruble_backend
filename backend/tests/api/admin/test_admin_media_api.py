"""Tests for /api/v1/admin/media endpoints."""

import uuid

import pytest
from sqlalchemy import select

from app.models import MediaAsset
from app.models.base import MediaAssetType
from tests.conftest import create_campaign

pytestmark = pytest.mark.asyncio


async def test_upload_multipart_requires_fields(client, admin_headers):
    resp = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        json={},
    )
    assert resp.status_code == 422


async def test_upload_success_creates_row(client, db, admin_headers, monkeypatch):
    def fake_put_object(**kwargs):
        return None

    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        fake_put_object,
    )

    files = {"file": ("clip.mp4", b"\x00" * 200, "video/mp4")}
    data = {"type": "video"}
    resp = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert "key" in body
    assert body["key"].startswith("videos/")
    assert body["url"].endswith(body["key"])
    assert body["filename"] == "clip.mp4"
    assert body["content_type"] == "video/mp4"

    result = await db.execute(select(MediaAsset).where(MediaAsset.id == uuid.UUID(body["id"])))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.type == MediaAssetType.video
    assert row.s3_key == body["key"]


async def test_upload_audio_success(client, db, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )

    files = {"file": ("thanks.mp3", b"\x00" * 200, "audio/mpeg")}
    data = {"type": "audio"}
    resp = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"].startswith("audio/")
    assert body["content_type"] == "audio/mpeg"

    result = await db.execute(select(MediaAsset).where(MediaAsset.id == uuid.UUID(body["id"])))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.type == MediaAssetType.audio


async def test_upload_audio_invalid_mime(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )
    resp = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files={"file": ("x.wav", b"\x00" * 100, "audio/wav")},
        data={"type": "audio"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_FILE_FORMAT"


async def test_list_media_filter_audio(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )
    up = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files={"file": ("a.mp3", b"\x00" * 200, "audio/mpeg")},
        data={"type": "audio"},
    )
    assert up.status_code == 200
    aid = up.json()["id"]

    resp = await client.get(
        "/api/v1/admin/media",
        headers=admin_headers,
        params={"type": "audio"},
    )
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert all(x["type"] == "audio" for x in items)
    assert any(x["id"] == aid for x in items)


async def test_list_media_empty(client, admin_headers):
    resp = await client.get("/api/v1/admin/media", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["data"] == []


async def test_list_media_after_upload(client, db, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )
    files = {"file": ("doc.pdf", b"%PDF-1.4 minimal", "application/pdf")}
    data = {"type": "document"}
    up = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files=files,
        data=data,
    )
    assert up.status_code == 200
    mid = up.json()["id"]

    resp = await client.get("/api/v1/admin/media", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1
    assert any(x["id"] == mid for x in items)


async def test_get_media_404(client, admin_headers):
    resp = await client.get(
        f"/api/v1/admin/media/{uuid.uuid4()}",
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_get_media_detail(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )
    up = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files={"file": ("a.mp4", b"\x00" * 200, "video/mp4")},
        data={"type": "video"},
    )
    mid = up.json()["id"]

    resp = await client.get(f"/api/v1/admin/media/{mid}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == mid
    assert body["download_url"] == body["url"]


async def test_download_redirect(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )
    up = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files={"file": ("b.mp4", b"\x00" * 200, "video/mp4")},
        data={"type": "video"},
    )
    mid = up.json()["id"]
    expected_url = up.json()["url"]

    resp = await client.get(
        f"/api/v1/admin/media/{mid}/download",
        headers=admin_headers,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == expected_url


async def test_patch_campaign_resolves_video_media_asset_id(
    client, db, admin_headers, foundation, monkeypatch,
):
    monkeypatch.setattr(
        "app.api.v1.admin.media.s3_client.put_object",
        lambda **kw: None,
    )
    up = await client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files={"file": ("c.mp4", b"\x00" * 200, "video/mp4")},
        data={"type": "video"},
    )
    asset_id = up.json()["id"]
    public_url = up.json()["url"]

    campaign = await create_campaign(db, foundation)

    resp = await client.patch(
        f"/api/v1/admin/campaigns/{campaign.id}",
        headers=admin_headers,
        json={"video_media_asset_id": asset_id},
    )
    assert resp.status_code == 200
    assert resp.json()["video_url"] == public_url
