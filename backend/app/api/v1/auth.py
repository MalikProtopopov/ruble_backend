"""Authentication: email OTP flow."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.auth import (
    LogoutRequest,
    OTPSentResponse,
    RefreshRequest,
    SendOTPRequest,
    TokenResponse,
    UserTokenResponse,
    VerifyOTPRequest,
)
from app.schemas.base import ErrorResponse
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])

_error_responses = {422: {"model": ErrorResponse, "description": "Ошибка валидации"}}


@router.post(
    "/send-otp",
    response_model=OTPSentResponse,
    summary="Send OTP code to email",
    description="Отправка одноразового кода на email пользователя",
    responses=_error_responses,
)
async def send_otp(
    body: SendOTPRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.send_otp(session, body.email)


@router.post(
    "/verify-otp",
    response_model=UserTokenResponse,
    summary="Verify OTP and get tokens",
    description="Проверка OTP-кода и получение JWT-токенов",
    responses=_error_responses,
)
async def verify_otp(
    body: VerifyOTPRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.verify_otp(session, body.email, body.code)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Обновление access-токена с помощью refresh-токена",
    responses=_error_responses,
)
async def refresh_token(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.refresh_tokens(session, body.refresh_token)


@router.post(
    "/logout",
    status_code=204,
    summary="Logout and revoke refresh token",
    description="Выход из системы и отзыв refresh-токена",
    responses=_error_responses,
)
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    await auth_service.logout(session, body.refresh_token)
    return Response(status_code=204)
