"""Subscription endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.subscription import (
    BindCardResponse,
    CreateSubscriptionRequest,
    SubscriptionResponse,
    UpdateSubscriptionRequest,
)
from app.services import subscription as subscription_service

router = APIRouter(tags=["subscriptions"])


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED, summary="Create subscription", description="Создание подписки на регулярные пожертвования")
async def create_subscription(
    body: CreateSubscriptionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await subscription_service.create_subscription(session, user_id, body.model_dump())


@router.get("", response_model=list[SubscriptionResponse], summary="List subscriptions", description="Список подписок текущего пользователя")
async def list_subscriptions(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await subscription_service.list_subscriptions(session, user_id)


@router.patch("/{subscription_id}", response_model=SubscriptionResponse, summary="Update subscription", description="Обновление параметров подписки")
async def update_subscription(
    subscription_id: UUID,
    body: UpdateSubscriptionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await subscription_service.update_subscription(
        session, subscription_id, user_id, body.model_dump(exclude_unset=True),
    )


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse, summary="Pause subscription", description="Приостановка подписки")
async def pause_subscription(
    subscription_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await subscription_service.pause_subscription(session, subscription_id, user_id)


@router.post("/{subscription_id}/resume", response_model=SubscriptionResponse, summary="Resume subscription", description="Возобновление приостановленной подписки")
async def resume_subscription(
    subscription_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await subscription_service.resume_subscription(session, subscription_id, user_id)


@router.delete("/{subscription_id}", status_code=204, summary="Cancel subscription", description="Отмена подписки")
async def cancel_subscription(
    subscription_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    await subscription_service.cancel_subscription(session, subscription_id, user_id)
    return Response(status_code=204)


@router.post(
    "/{subscription_id}/bind-card",
    response_model=BindCardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bind card to subscription",
    description="Привязка банковской карты к подписке",
)
async def bind_card(
    subscription_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await subscription_service.bind_card(session, subscription_id, user_id)
