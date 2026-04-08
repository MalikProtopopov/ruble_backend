"""Tests for video thumbnail generation + auto-fill + backfill endpoint.

ffmpeg and boto3 are mocked — we don't run real video processing in CI.
"""

from unittest.mock import patch

import pytest

from app.models import Campaign
from app.models.base import CampaignStatus, uuid7
from app.services.video_thumbnail import _extract_s3_key_from_url
from tests.conftest import create_campaign, create_foundation

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# _extract_s3_key_from_url — pure function, no mocks
# ---------------------------------------------------------------------------


def test_extract_s3_key_strips_public_prefix():
    from app.core.config import settings

    url = f"{settings.S3_PUBLIC_URL.rstrip('/')}/videos/abc123.mp4"
    assert _extract_s3_key_from_url(url) == "videos/abc123.mp4"


def test_extract_s3_key_fallback_to_marker():
    """Legacy URL with a different host but a recognisable prefix segment."""
    url = "https://other-cdn.example.com/some/path/videos/legacy.mp4"
    assert _extract_s3_key_from_url(url) == "videos/legacy.mp4"


def test_extract_s3_key_returns_none_on_empty():
    assert _extract_s3_key_from_url("") is None
    assert _extract_s3_key_from_url(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# generate_thumbnail_for_video_url — service-level with mocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_thumbnail_happy_path():
    from app.services import video_thumbnail as svc

    fake_jpeg = b"\xff\xd8\xff\xe0fake-jpeg"
    with patch.object(svc, "extract_first_frame_jpeg", return_value=fake_jpeg) as mock_ex, \
         patch.object(svc, "upload_thumbnail_jpeg", return_value=("thumbnails/abc.jpg", "https://cdn/thumbnails/abc.jpg")) as mock_up:
        url = await svc.generate_thumbnail_for_video_url(
            f"{__import__('app').core.config.settings.S3_PUBLIC_URL.rstrip('/')}/videos/foo.mp4"
        )

    assert url == "https://cdn/thumbnails/abc.jpg"
    mock_ex.assert_awaited_once()
    mock_up.assert_awaited_once_with(fake_jpeg)


@pytest.mark.asyncio
async def test_generate_thumbnail_returns_none_on_ffmpeg_failure():
    """ffmpeg crash must NOT raise — caller flow continues without a thumbnail."""
    import subprocess

    from app.services import video_thumbnail as svc

    fake_err = subprocess.CalledProcessError(1, ["ffmpeg"], stderr=b"boom")
    with patch.object(svc, "extract_first_frame_jpeg", side_effect=fake_err):
        url = await svc.generate_thumbnail_for_video_url("https://cdn/videos/bad.mp4")
    assert url is None


@pytest.mark.asyncio
async def test_generate_thumbnail_returns_none_on_boto_error():
    from app.services import video_thumbnail as svc

    with patch.object(svc, "extract_first_frame_jpeg", side_effect=RuntimeError("s3 down")):
        url = await svc.generate_thumbnail_for_video_url("https://cdn/videos/x.mp4")
    assert url is None


@pytest.mark.asyncio
async def test_generate_thumbnail_skips_when_url_has_no_recognisable_key():
    from app.services import video_thumbnail as svc

    # Empty path → no marker → no key.
    url = await svc.generate_thumbnail_for_video_url("https://cdn/")
    assert url is None


# ---------------------------------------------------------------------------
# Backfill endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_endpoint_fills_missing_thumbnails(client, db, admin_headers):
    foundation = await create_foundation(db)
    c1 = await create_campaign(db, foundation, title="With video, no thumb")
    c1.video_url = "https://cdn/videos/c1.mp4"
    c1.thumbnail_url = None

    c2 = await create_campaign(db, foundation, title="With video, has thumb")
    c2.video_url = "https://cdn/videos/c2.mp4"
    c2.thumbnail_url = "https://cdn/thumbnails/existing.jpg"

    c3 = await create_campaign(db, foundation, title="No video at all")
    c3.video_url = None
    await db.flush()

    with patch(
        "app.api.v1.admin.campaigns.generate_thumbnail_for_video_url",
        return_value="https://cdn/thumbnails/generated.jpg",
    ):
        resp = await client.post(
            "/api/v1/admin/campaigns/backfill-thumbnails",
            headers=admin_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scanned"] == 1  # only c1 matches
    assert body["filled"] == 1
    assert body["failed"] == 0
    assert str(c1.id) in body["filled_ids"]

    await db.refresh(c1)
    await db.refresh(c2)
    await db.refresh(c3)
    assert c1.thumbnail_url == "https://cdn/thumbnails/generated.jpg"
    assert c2.thumbnail_url == "https://cdn/thumbnails/existing.jpg"
    assert c3.thumbnail_url is None


@pytest.mark.asyncio
async def test_backfill_endpoint_records_failures(client, db, admin_headers):
    foundation = await create_foundation(db)
    c = await create_campaign(db, foundation, title="Broken video")
    c.video_url = "https://cdn/videos/broken.mp4"
    c.thumbnail_url = None
    await db.flush()

    with patch(
        "app.api.v1.admin.campaigns.generate_thumbnail_for_video_url",
        return_value=None,
    ):
        resp = await client.post(
            "/api/v1/admin/campaigns/backfill-thumbnails",
            headers=admin_headers,
        )

    body = resp.json()
    assert body["filled"] == 0
    assert body["failed"] == 1
    assert body["failed_items"][0]["id"] == str(c.id)
    await db.refresh(c)
    assert c.thumbnail_url is None


@pytest.mark.asyncio
async def test_backfill_requires_admin(client):
    resp = await client.post("/api/v1/admin/campaigns/backfill-thumbnails")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auto-fill on create / update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_campaign_auto_generates_thumbnail(client, db, admin_headers):
    foundation = await create_foundation(db)

    with patch(
        "app.api.v1.admin.campaigns.generate_thumbnail_for_video_url",
        return_value="https://cdn/thumbnails/auto.jpg",
    ) as mock_gen:
        resp = await client.post(
            "/api/v1/admin/campaigns",
            headers=admin_headers,
            json={
                "foundation_id": str(foundation.id),
                "title": "Auto-thumb test",
                "description": "x",
                "video_url": "https://cdn/videos/new.mp4",
                "goal_amount": 100000,
                "urgency_level": 3,
                "is_permanent": False,
            },
        )

    assert resp.status_code == 201, resp.text
    assert resp.json()["thumbnail_url"] == "https://cdn/thumbnails/auto.jpg"
    mock_gen.assert_awaited_once_with("https://cdn/videos/new.mp4")


@pytest.mark.asyncio
async def test_create_campaign_skips_thumbnail_when_explicit(client, db, admin_headers):
    """If admin explicitly passes a thumbnail, don't override it."""
    foundation = await create_foundation(db)

    with patch(
        "app.api.v1.admin.campaigns.generate_thumbnail_for_video_url",
    ) as mock_gen:
        resp = await client.post(
            "/api/v1/admin/campaigns",
            headers=admin_headers,
            json={
                "foundation_id": str(foundation.id),
                "title": "Manual-thumb",
                "description": "x",
                "video_url": "https://cdn/videos/v.mp4",
                "thumbnail_url": "https://cdn/thumbnails/manual.jpg",
                "goal_amount": 100000,
                "urgency_level": 3,
                "is_permanent": False,
            },
        )

    assert resp.status_code == 201
    assert resp.json()["thumbnail_url"] == "https://cdn/thumbnails/manual.jpg"
    mock_gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_campaign_auto_generates_thumbnail(client, db, admin_headers):
    foundation = await create_foundation(db)
    c = await create_campaign(db, foundation, title="Update test")
    c.video_url = None
    c.thumbnail_url = None
    await db.flush()

    with patch(
        "app.api.v1.admin.campaigns.generate_thumbnail_for_video_url",
        return_value="https://cdn/thumbnails/upd.jpg",
    ) as mock_gen:
        resp = await client.patch(
            f"/api/v1/admin/campaigns/{c.id}",
            headers=admin_headers,
            json={"video_url": "https://cdn/videos/upd.mp4"},
        )

    assert resp.status_code == 200, resp.text
    mock_gen.assert_awaited_once_with("https://cdn/videos/upd.mp4")
    await db.refresh(c)
    assert c.thumbnail_url == "https://cdn/thumbnails/upd.jpg"
