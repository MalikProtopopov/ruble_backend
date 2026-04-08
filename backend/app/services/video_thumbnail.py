"""Generate JPEG thumbnails from the first frame of MP4 videos in S3.

Used to auto-fill `campaigns.thumbnail_url` when an admin saves a campaign with
a video but without an explicit thumbnail. Also used by the backfill admin
endpoint to retroactively fill missing thumbnails.

Pipeline:
    1. Stream-download the source video from S3 (boto3)
    2. Run `ffmpeg -ss 0 -i in.mp4 -frames:v 1 -q:v 3 out.jpg` in a temp dir
    3. Upload the resulting JPEG back to S3 under thumbnails/
    4. Return the public URL

ffmpeg is shipped in the backend image (see Dockerfile).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import uuid
from urllib.parse import urlparse

from app.core.config import build_media_url, settings
from app.core.logging import get_logger
from app.services.media import get_s3_client

logger = get_logger(__name__)


def _extract_s3_key_from_url(url: str) -> str | None:
    """Best-effort extraction of an S3 key from a stored public URL.

    URLs in the DB are built by `build_media_url(s3_key)` which prepends
    `S3_PUBLIC_URL`. To get the key back we strip a known prefix; if the prefix
    doesn't match (legacy data) we fall back to taking everything after the
    first `videos/`, `images/`, `media/` segment so we still grab the right
    object.
    """
    if not url:
        return None
    public = settings.S3_PUBLIC_URL.rstrip("/")
    if url.startswith(public + "/"):
        return url[len(public) + 1:]
    # Fallback: parse and find a known prefix segment.
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    for marker in ("videos/", "images/", "media/", "documents/", "audio/"):
        idx = path.find(marker)
        if idx != -1:
            return path[idx:]
    return path or None


def _run_ffmpeg(input_path: str, output_path: str) -> None:
    """Synchronous ffmpeg invocation. Raises CalledProcessError on failure."""
    cmd = [
        "ffmpeg",
        "-y",                # overwrite
        "-loglevel", "error",
        "-ss", "0",          # seek to start (before -i = fast, key-frame snap)
        "-i", input_path,
        "-frames:v", "1",
        "-q:v", "3",         # JPEG quality 1 (best) – 31 (worst); 3 is high
        "-vf", "scale='min(1280,iw)':-2",  # cap width at 1280, keep AR
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)


async def extract_first_frame_jpeg(*, s3_key: str) -> bytes:
    """Download `s3_key` from S3, return the first frame as JPEG bytes.

    Runs entirely in a thread (boto3 + ffmpeg are blocking)."""

    def _work() -> bytes:
        client = get_s3_client()
        tmpdir = tempfile.mkdtemp(prefix="thumb_")
        try:
            in_path = os.path.join(tmpdir, "in.mp4")
            out_path = os.path.join(tmpdir, "out.jpg")
            client.download_file(settings.S3_BUCKET, s3_key, in_path)
            _run_ffmpeg(in_path, out_path)
            with open(out_path, "rb") as fh:
                return fh.read()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return await asyncio.to_thread(_work)


async def upload_thumbnail_jpeg(jpeg_bytes: bytes) -> tuple[str, str]:
    """Upload JPEG bytes to S3 under `thumbnails/`. Returns (s3_key, public_url)."""
    key = f"thumbnails/{uuid.uuid4().hex}.jpg"

    def _work() -> None:
        client = get_s3_client()
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=jpeg_bytes,
            ContentType="image/jpeg",
        )

    await asyncio.to_thread(_work)
    return key, build_media_url(key)


async def generate_thumbnail_for_video_url(video_url: str) -> str | None:
    """High-level helper: given a video URL, return a thumbnail public URL.

    Returns None and logs a warning if the source can't be located or ffmpeg
    fails — generation is best-effort and must never break the calling flow.
    """
    s3_key = _extract_s3_key_from_url(video_url)
    if not s3_key:
        logger.warning("thumbnail_skip_no_key", video_url=video_url)
        return None
    try:
        jpeg = await extract_first_frame_jpeg(s3_key=s3_key)
        _, url = await upload_thumbnail_jpeg(jpeg)
        logger.info("thumbnail_generated", source_key=s3_key, size=len(jpeg))
        return url
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "thumbnail_ffmpeg_failed",
            source_key=s3_key,
            stderr=(exc.stderr or b"")[:500].decode("utf-8", errors="replace"),
        )
        return None
    except Exception as exc:  # boto3 errors, timeouts, etc.
        logger.warning(
            "thumbnail_generate_failed",
            source_key=s3_key,
            error=type(exc).__name__,
            detail=str(exc)[:500],
        )
        return None
