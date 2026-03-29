"""Admin management endpoints (CRUD for admin accounts)."""

from uuid import UUID

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.repositories import admin_repo
from app.schemas.admin import AdminCreateRequest, AdminResponse, AdminUpdateRequest

router = APIRouter()
logger = get_logger(__name__)
ph = PasswordHasher()


def _serialize(a) -> dict:
    return AdminResponse.model_validate(a).model_dump(mode="json")


@router.get(
    "",
    summary="List admins",
    description="Список администраторов с фильтрацией по статусу активности",
)
async def list_admins(
    is_active: bool | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await admin_repo.list_all(session, pagination, is_active=is_active)
    data = [_serialize(a) for a in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.post(
    "",
    status_code=201,
    response_model=AdminResponse,
    summary="Create admin",
    description="Создание нового администратора",
)
async def create_admin(
    body: AdminCreateRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    existing = await admin_repo.get_by_email(session, body.email)
    if existing is not None:
        raise ConflictError(
            message="Администратор с таким email уже существует",
            details={"code": "ADMIN_EMAIL_EXISTS"},
        )

    new_admin = await admin_repo.create(
        session,
        email=body.email,
        password_hash=ph.hash(body.password),
        name=body.name,
    )
    logger.info("admin_created", new_admin_id=str(new_admin.id), by_admin_id=admin["sub"])
    return _serialize(new_admin)


@router.get(
    "/{admin_id}",
    response_model=AdminResponse,
    summary="Get admin",
    description="Получение информации об администраторе",
)
async def get_admin(
    admin_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await admin_repo.get_by_id(session, admin_id)
    if target is None:
        raise NotFoundError(message="Администратор не найден")
    return _serialize(target)


@router.patch(
    "/{admin_id}",
    response_model=AdminResponse,
    summary="Update admin",
    description="Обновление данных администратора",
)
async def update_admin(
    admin_id: UUID,
    body: AdminUpdateRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await admin_repo.get_by_id(session, admin_id)
    if target is None:
        raise NotFoundError(message="Администратор не найден")

    update_data = body.model_dump(exclude_unset=True)

    # Check email uniqueness if being changed
    if "email" in update_data and update_data["email"] != target.email:
        existing = await admin_repo.get_by_email(session, update_data["email"])
        if existing is not None:
            raise ConflictError(
                message="Администратор с таким email уже существует",
                details={"code": "ADMIN_EMAIL_EXISTS"},
            )

    # Handle password hashing separately
    data_for_repo = {}
    if "email" in update_data:
        data_for_repo["email"] = update_data["email"]
    if "name" in update_data:
        data_for_repo["name"] = update_data["name"]
    if "password" in update_data:
        data_for_repo["password_hash"] = ph.hash(update_data["password"])

    target = await admin_repo.update(session, target, data_for_repo)
    logger.info("admin_updated", target_admin_id=str(admin_id), by_admin_id=admin["sub"])
    return _serialize(target)


@router.post(
    "/{admin_id}/deactivate",
    summary="Deactivate admin",
    description="Деактивация администратора и отзыв всех токенов",
)
async def deactivate_admin(
    admin_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    current_admin_id = UUID(admin["sub"])
    if current_admin_id == admin_id:
        raise ForbiddenError(message="Невозможно деактивировать собственный аккаунт")

    target = await admin_repo.get_by_id(session, admin_id)
    if target is None:
        raise NotFoundError(message="Администратор не найден")

    target = await admin_repo.update(session, target, {"is_active": False})
    await admin_repo.revoke_all_tokens(session, admin_id)
    await session.flush()

    logger.info("admin_deactivated", target_admin_id=str(admin_id), by_admin_id=admin["sub"])
    return {"id": str(target.id), "is_active": False}


@router.post(
    "/{admin_id}/activate",
    summary="Activate admin",
    description="Активация ранее деактивированного администратора",
)
async def activate_admin(
    admin_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    target = await admin_repo.get_by_id(session, admin_id)
    if target is None:
        raise NotFoundError(message="Администратор не найден")

    target = await admin_repo.update(session, target, {"is_active": True})
    logger.info("admin_activated", target_admin_id=str(admin_id), by_admin_id=admin["sub"])
    return {"id": str(target.id), "is_active": True}
