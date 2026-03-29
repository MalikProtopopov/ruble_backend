"""Admin user management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.models.base import UserRole
from app.repositories import user_repo
from app.schemas.user import (
    AdminUserDonationBrief,
    AdminUserListItem,
    AdminUserSubscriptionBrief,
)

router = APIRouter()
logger = get_logger(__name__)


def _serialize(u) -> dict:
    return AdminUserListItem.model_validate(u).model_dump(mode="json")


@router.get(
    "",
    summary="List users",
    description="Список пользователей с фильтрацией по роли и поиском",
)
async def list_users(
    role: UserRole | None = Query(default=None),
    search: str | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await user_repo.list_admin(session, pagination, role=role, search=search)
    data = [_serialize(u) for u in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.get(
    "/{user_id}",
    summary="Get user detail",
    description="Детальная информация о пользователе с подписками и донатами",
)
async def get_user(
    user_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(message="Пользователь не найден")

    data = _serialize(user)

    subs = await user_repo.get_subscriptions(session, user_id)
    data["subscriptions"] = [
        AdminUserSubscriptionBrief.model_validate(s).model_dump(mode="json") for s in subs
    ]

    donations = await user_repo.get_recent_donations(session, user_id)
    data["recent_donations"] = [
        AdminUserDonationBrief.model_validate(d).model_dump(mode="json") for d in donations
    ]

    return data


@router.post(
    "/{user_id}/grant-patron",
    summary="Grant patron role",
    description="Назначение пользователю роли мецената",
)
async def grant_patron(
    user_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(message="Пользователь не найден")

    user = await user_repo.set_role(session, user, UserRole.patron)
    logger.info("patron_granted", user_id=str(user_id), admin_id=admin["sub"])
    return {"id": str(user.id), "role": user.role.value}


@router.post(
    "/{user_id}/revoke-patron",
    summary="Revoke patron role",
    description="Снятие роли мецената, возврат в обычного донора",
)
async def revoke_patron(
    user_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(message="Пользователь не найден")

    user = await user_repo.set_role(session, user, UserRole.donor)
    logger.info("patron_revoked", user_id=str(user_id), admin_id=admin["sub"])
    return {"id": str(user.id), "role": user.role.value}


@router.post(
    "/{user_id}/deactivate",
    summary="Deactivate user",
    description="Деактивация пользователя: отзыв токенов и приостановка подписок",
)
async def deactivate_user(
    user_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(message="Пользователь не найден")

    user = await user_repo.set_active(session, user, False)
    await user_repo.revoke_all_tokens(session, user_id)
    await user_repo.pause_active_subscriptions(session, user_id)
    await session.flush()

    logger.info("user_deactivated", user_id=str(user_id), admin_id=admin["sub"])
    return {"id": str(user.id), "is_active": False}


@router.post(
    "/{user_id}/activate",
    summary="Activate user",
    description="Активация ранее деактивированного пользователя",
)
async def activate_user(
    user_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError(message="Пользователь не найден")

    user = await user_repo.set_active(session, user, True)
    logger.info("user_activated", user_id=str(user_id), admin_id=admin["sub"])
    return {"id": str(user.id), "is_active": True}
