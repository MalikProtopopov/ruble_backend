"""Media upload validation rules."""

from app.domain.constants import (
    ALLOWED_AUDIO_CONTENT_TYPES,
    ALLOWED_DOCUMENT_CONTENT_TYPES,
    ALLOWED_IMAGE_CONTENT_TYPES,
    ALLOWED_VIDEO_CONTENT_TYPES,
    MAX_AUDIO_SIZE_BYTES,
    MAX_DOCUMENT_SIZE_BYTES,
    MAX_IMAGE_SIZE_BYTES,
    MAX_VIDEO_SIZE_BYTES,
)


class FileTooLarge(Exception):
    def __init__(self, media_type: str, size: int, max_size: int):
        super().__init__(f"{media_type} file {size} bytes exceeds limit {max_size}")


class InvalidFileFormat(Exception):
    def __init__(self, content_type: str, allowed: frozenset):
        super().__init__(f"Content type '{content_type}' not in {allowed}")


def validate_media(media_type: str, content_type: str, size_bytes: int) -> None:
    """Validate file against business rules. Raises FileTooLarge or InvalidFileFormat."""
    if media_type == "video":
        if content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
            raise InvalidFileFormat(content_type, ALLOWED_VIDEO_CONTENT_TYPES)
        if size_bytes > MAX_VIDEO_SIZE_BYTES:
            raise FileTooLarge(media_type, size_bytes, MAX_VIDEO_SIZE_BYTES)
    elif media_type == "document":
        if content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
            raise InvalidFileFormat(content_type, ALLOWED_DOCUMENT_CONTENT_TYPES)
        if size_bytes > MAX_DOCUMENT_SIZE_BYTES:
            raise FileTooLarge(media_type, size_bytes, MAX_DOCUMENT_SIZE_BYTES)
    elif media_type == "audio":
        if content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
            raise InvalidFileFormat(content_type, ALLOWED_AUDIO_CONTENT_TYPES)
        if size_bytes > MAX_AUDIO_SIZE_BYTES:
            raise FileTooLarge(media_type, size_bytes, MAX_AUDIO_SIZE_BYTES)
    elif media_type == "image":
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise InvalidFileFormat(content_type, ALLOWED_IMAGE_CONTENT_TYPES)
        if size_bytes > MAX_IMAGE_SIZE_BYTES:
            raise FileTooLarge(media_type, size_bytes, MAX_IMAGE_SIZE_BYTES)
    else:
        raise ValueError(f"Unknown media type: {media_type}")
