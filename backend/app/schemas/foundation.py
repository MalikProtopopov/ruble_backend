from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from app.schemas.base import OrmBase


class FoundationPublicResponse(OrmBase):
    id: UUID
    name: str
    description: str | None
    logo_url: str | None
    website_url: str | None
    status: str


class FoundationAdminResponse(FoundationPublicResponse):
    legal_name: str
    inn: str
    yookassa_shop_id: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FoundationCreate(BaseModel):
    name: str
    legal_name: str
    inn: str
    description: str | None = None
    logo_url: str | None = None
    website_url: str | None = None


class FoundationUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    inn: str | None = None
    description: str | None = None
    logo_url: str | None = None
    logo_media_asset_id: UUID | None = None
    website_url: str | None = None
    status: str | None = None
    yookassa_shop_id: str | None = None
