"""Cursor-based pagination utilities."""

import base64
import json
from dataclasses import dataclass

from fastapi import Query


@dataclass
class PaginationParams:
    limit: int
    cursor: str | None


def get_pagination(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> PaginationParams:
    return PaginationParams(limit=limit, cursor=cursor)


def encode_cursor(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()))


def paginated_response(data: list, next_cursor: str | None, has_more: bool):
    return {
        "data": data,
        "pagination": {
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": None,
        },
    }
