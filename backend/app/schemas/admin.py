from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr
from app.schemas.base import OrmBase


class AdminResponse(OrmBase):
    id: UUID
    email: str
    name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminCreateRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class AdminUpdateRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
