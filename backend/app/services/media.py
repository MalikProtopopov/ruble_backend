"""S3 media upload service."""

import asyncio
import uuid
from io import BytesIO

import boto3
from botocore.config import Config as BotoConfig

from app.core.config import build_media_url, settings
from app.core.exceptions import BusinessLogicError
from app.core.logging import get_logger
from app.domain.media import validate_media, FileTooLarge, InvalidFileFormat

logger = get_logger(__name__)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
    )


async def upload_media(file_content: bytes, filename: str, content_type: str, media_type: str) -> dict:
    """Upload file to S3. media_type: 'video' or 'document'."""
    size = len(file_content)

    try:
        validate_media(media_type, content_type, size)
    except FileTooLarge:
        msg = "Видео не должно превышать 500 МБ" if media_type == "video" else "Документ не должен превышать 10 МБ"
        raise BusinessLogicError(code="FILE_TOO_LARGE", message=msg)
    except InvalidFileFormat:
        msg = "Допустимый формат видео: mp4" if media_type == "video" else "Допустимый формат документа: pdf"
        raise BusinessLogicError(code="INVALID_FILE_FORMAT", message=msg)

    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    key = f"media/{uuid.uuid4()}.{ext}"

    client = get_s3_client()
    await asyncio.to_thread(
        client.upload_fileobj,
        BytesIO(file_content),
        settings.S3_BUCKET,
        key,
        ExtraArgs={"ContentType": content_type},
    )

    url = build_media_url(key)
    logger.info("media_uploaded", key=key, size=size, content_type=content_type)

    return {"url": url, "filename": filename, "size_bytes": size, "content_type": content_type}
