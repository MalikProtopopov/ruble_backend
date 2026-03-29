"""Admin authentication endpoints."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.schemas.auth import AdminLoginRequest, AdminTokenResponse, LogoutRequest, RefreshRequest, TokenResponse
from app.schemas.base import ErrorResponse
from app.services import auth as auth_service

router = APIRouter()

_error_responses = {422: {"model": ErrorResponse, "description": "Ошибка валидации"}}


@router.post(
    "/login",
    response_model=AdminTokenResponse,
    summary="Admin login",
    description="Аутентификация администратора по email и паролю",
    responses=_error_responses,
)
async def admin_login(
    body: AdminLoginRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.admin_login(session, body.email, body.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh admin token",
    description="Обновление access-токена администратора",
    responses=_error_responses,
)
async def admin_refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.refresh_tokens(session, body.refresh_token)


@router.post(
    "/logout",
    status_code=204,
    summary="Admin logout",
    description="Выход и отзыв refresh-токена администратора",
    responses=_error_responses,
)
async def admin_logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_db_session),
):
    await auth_service.logout(session, body.refresh_token)
    return Response(status_code=204)
