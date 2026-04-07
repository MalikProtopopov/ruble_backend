"""Authentication: email OTP flow + anonymous device registration."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.auth import (
    DeviceRegisterRequest,
    LinkEmailTokenResponse,
    LinkEmailVerifyRequest,
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
    "/device-register",
    response_model=UserTokenResponse,
    summary="Register an anonymous device",
    description=(
        "Создаёт гостевого пользователя по client-generated device_id и возвращает "
        "пару access/refresh токенов с увеличенным TTL refresh-токена. "
        "Идемпотентно: повторный вызов с тем же device_id вернёт того же юзера."
    ),
    responses=_error_responses,
)
async def device_register(
    body: DeviceRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.device_register(
        session,
        device_id=body.device_id,
        push_token=body.push_token,
        push_platform=body.push_platform,
        timezone_name=body.timezone,
    )


@router.post(
    "/link-email/verify-otp",
    response_model=LinkEmailTokenResponse,
    summary="Link email to anonymous account (with optional merge)",
    description=(
        "Привязывает email к текущему гостевому аккаунту после проверки OTP. "
        "Если email уже принадлежит другому юзеру и allow_merge=false — вернёт ошибку "
        "EMAIL_ALREADY_LINKED. Если allow_merge=true — выполнит слияние гостевого "
        "аккаунта в существующий и вернёт токены целевого аккаунта."
    ),
    responses=_error_responses,
)
async def link_email_verify_otp(
    body: LinkEmailVerifyRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await auth_service.link_email_verify_otp(
        session,
        current_user_id=UUID(user["sub"]),
        email=body.email,
        code=body.code,
        allow_merge=body.allow_merge,
    )


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
