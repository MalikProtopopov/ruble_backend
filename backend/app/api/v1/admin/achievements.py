"""Admin achievement management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import require_admin
from app.repositories import achievement_repo
from app.schemas.achievement import (
    AchievementAdminResponse,
    AchievementCreateRequest,
    AchievementUpdateRequest,
)

router = APIRouter()
logger = get_logger(__name__)


def _serialize(a) -> dict:
    return AchievementAdminResponse.model_validate(a).model_dump(mode="json")


@router.get(
    "",
    summary="List achievements",
    description="Список всех достижений",
)
async def list_achievements(
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    items = await achievement_repo.list_all(session)
    return {"data": [_serialize(a) for a in items]}


@router.post(
    "",
    status_code=201,
    response_model=AchievementAdminResponse,
    summary="Create achievement",
    description="Создание нового достижения",
)
async def create_achievement(
    body: AchievementCreateRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    existing = await achievement_repo.get_by_code(session, body.code)
    if existing is not None:
        raise ConflictError(
            message="Достижение с таким кодом уже существует",
            details={"code": "ACHIEVEMENT_CODE_EXISTS"},
        )

    achievement = await achievement_repo.create(
        session,
        code=body.code,
        title=body.title,
        description=body.description,
        icon_url=body.icon_url,
        condition_type=body.condition_type,
        condition_value=body.condition_value,
    )
    logger.info("achievement_created", achievement_id=str(achievement.id), admin_id=admin["sub"])
    return _serialize(achievement)


@router.patch(
    "/{achievement_id}",
    response_model=AchievementAdminResponse,
    summary="Update achievement",
    description="Обновление достижения",
)
async def update_achievement(
    achievement_id: UUID,
    body: AchievementUpdateRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    achievement = await achievement_repo.get_by_id(session, achievement_id)
    if achievement is None:
        raise NotFoundError(message="Достижение не найдено")

    update_data = body.model_dump(exclude_unset=True)

    # Check code uniqueness if being updated
    if "code" in update_data and update_data["code"] != achievement.code:
        existing = await achievement_repo.get_by_code(session, update_data["code"])
        if existing is not None:
            raise ConflictError(
                message="Достижение с таким кодом уже существует",
                details={"code": "ACHIEVEMENT_CODE_EXISTS"},
            )

    achievement = await achievement_repo.update(session, achievement, update_data)
    logger.info("achievement_updated", achievement_id=str(achievement_id), admin_id=admin["sub"])
    return _serialize(achievement)
