"""Admin foundation management endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.models.base import FoundationStatus
from app.repositories import foundation_repo
from app.services.media_asset_resolve import THUMBNAIL_OR_LOGO, resolve_public_url
from app.schemas.foundation import FoundationAdminResponse, FoundationCreate, FoundationUpdate

router = APIRouter()
logger = get_logger(__name__)


def _serialize(f) -> dict:
    return FoundationAdminResponse.model_validate(f).model_dump(mode="json")


@router.get(
    "",
    summary="List foundations",
    description="Список фондов с фильтрацией по статусу и поиском",
)
async def list_foundations(
    status: FoundationStatus | None = Query(default=None),
    search: str | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await foundation_repo.list_admin(session, pagination, status=status, search=search)
    data = [_serialize(f) for f in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.post(
    "",
    status_code=201,
    response_model=FoundationAdminResponse,
    summary="Create foundation",
    description="Создание нового фонда",
)
async def create_foundation(
    body: FoundationCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    existing = await foundation_repo.get_by_inn(session, body.inn)
    if existing is not None:
        raise ConflictError(message="ИНН уже зарегистрирован", details={"code": "INN_ALREADY_EXISTS"})

    foundation = await foundation_repo.create(
        session,
        name=body.name,
        legal_name=body.legal_name,
        inn=body.inn,
        description=body.description,
        logo_url=body.logo_url,
        website_url=body.website_url,
        status=FoundationStatus.pending_verification,
    )
    logger.info("foundation_created", foundation_id=str(foundation.id), admin_id=admin["sub"])
    return _serialize(foundation)


@router.get(
    "/{foundation_id}",
    response_model=FoundationAdminResponse,
    summary="Get foundation",
    description="Получение информации о фонде по ID",
)
async def get_foundation(
    foundation_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    foundation = await foundation_repo.get_by_id(session, foundation_id)
    if foundation is None:
        raise NotFoundError(message="Фонд не найден")
    return _serialize(foundation)


@router.patch(
    "/{foundation_id}",
    response_model=FoundationAdminResponse,
    summary="Update foundation",
    description="Обновление данных фонда",
)
async def update_foundation(
    foundation_id: UUID,
    body: FoundationUpdate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    foundation = await foundation_repo.get_by_id(session, foundation_id)
    if foundation is None:
        raise NotFoundError(message="Фонд не найден")

    update_data = body.model_dump(exclude_unset=True)

    if "logo_media_asset_id" in update_data:
        aid = update_data.pop("logo_media_asset_id")
        update_data.pop("logo_url", None)
        update_data["logo_url"] = await resolve_public_url(
            session, aid, allowed_types=THUMBNAIL_OR_LOGO,
        )

    # If INN is being changed, check uniqueness
    if "inn" in update_data and update_data["inn"] != foundation.inn:
        existing = await foundation_repo.get_by_inn(session, update_data["inn"])
        if existing is not None:
            raise ConflictError(message="ИНН уже зарегистрирован", details={"code": "INN_ALREADY_EXISTS"})

    # If status changed to active, set verified_at
    if "status" in update_data and update_data["status"] == FoundationStatus.active and foundation.verified_at is None:
        update_data["verified_at"] = datetime.now(timezone.utc)

    foundation = await foundation_repo.update(session, foundation, update_data)

    logger.info("foundation_updated", foundation_id=str(foundation_id), admin_id=admin["sub"])
    return _serialize(foundation)
