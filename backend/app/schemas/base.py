"""Shared schema types for pagination and error responses."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail
