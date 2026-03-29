"""Proxy endpoint to serve S3/MinIO files via /media/{s3_key}.

Supports HEAD, full GET, and Range requests (HTTP 206 Partial Content)
required by video players (AVFoundation on iOS, ExoPlayer on Android).

In production, nginx can handle /media/ -> minio:9000/{bucket}/ directly.
This endpoint serves as a fallback and enables local development without nginx.
"""

import asyncio
from typing import AsyncIterator

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.core.config import settings

router = APIRouter()

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4"),
)


def _head_object(key: str) -> dict | None:
    """Get object metadata from S3. Returns None if not found."""
    try:
        return _s3.head_object(Bucket=settings.S3_BUCKET, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise


def _parse_range(range_header: str, total: int) -> tuple[int, int] | None:
    """Parse Range header like 'bytes=0-1023' or 'bytes=1000-'. Returns (start, end) or None."""
    if not range_header.startswith("bytes="):
        return None
    byte_range = range_header[6:]
    parts = byte_range.split("-", 1)
    try:
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else total - 1
    except (ValueError, IndexError):
        return None
    if start < 0 or start >= total or end >= total or start > end:
        end = min(end, total - 1)
        if start > end:
            return None
    return start, end


async def _stream_s3_body(body, chunk_size: int = 256 * 1024) -> AsyncIterator[bytes]:
    """Stream S3 body in chunks."""
    while True:
        chunk = await asyncio.to_thread(body.read, chunk_size)
        if not chunk:
            break
        yield chunk


@router.head("/media/{s3_key:path}", include_in_schema=False)
async def media_head(s3_key: str):
    head = await asyncio.to_thread(_head_object, s3_key)
    if head is None:
        return Response(status_code=404)

    return Response(
        status_code=200,
        headers={
            "Content-Type": head.get("ContentType", "application/octet-stream"),
            "Content-Length": str(head["ContentLength"]),
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/media/{s3_key:path}", include_in_schema=False)
async def media_get(s3_key: str, request: Request):
    # Get metadata first
    head = await asyncio.to_thread(_head_object, s3_key)
    if head is None:
        return Response(status_code=404)

    total = head["ContentLength"]
    content_type = head.get("ContentType", "application/octet-stream")
    range_header = request.headers.get("range")

    if range_header:
        parsed = _parse_range(range_header, total)
        if parsed is None:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{total}"},
            )

        start, end = parsed
        length = end - start + 1

        obj = await asyncio.to_thread(
            _s3.get_object,
            Bucket=settings.S3_BUCKET,
            Key=s3_key,
            Range=f"bytes={start}-{end}",
        )

        return StreamingResponse(
            _stream_s3_body(obj["Body"]),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Accept-Ranges": "bytes",
            },
        )

    # Full file
    obj = await asyncio.to_thread(
        _s3.get_object, Bucket=settings.S3_BUCKET, Key=s3_key,
    )

    return StreamingResponse(
        _stream_s3_body(obj["Body"]),
        status_code=200,
        media_type=content_type,
        headers={
            "Content-Length": str(total),
            "Accept-Ranges": "bytes",
        },
    )
