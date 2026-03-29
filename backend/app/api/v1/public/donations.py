"""Donation endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import bearer_scheme, decode_token, require_donor
from app.schemas.donation import CreateDonationRequest, DonationDetailResponse, DonationResponse
from app.services import donation as donation_service

router = APIRouter(tags=["donations"])


@router.post("", response_model=DonationResponse, status_code=status.HTTP_201_CREATED, summary="Create a donation", description="Создание разового пожертвования (доступно без авторизации)")
async def create_donation(
    body: CreateDonationRequest,
    session: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    user_id = None
    email = body.email
    if credentials is not None:
        payload = decode_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    return await donation_service.create_donation(
        session,
        campaign_id=body.campaign_id,
        amount_kopecks=body.amount_kopecks,
        user_id=user_id,
        email=str(email) if email else None,
    )


@router.get("", summary="List user donations", description="Список пожертвований текущего пользователя")
async def list_donations(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
    pagination: PaginationParams = Depends(get_pagination),
    donation_status: str | None = Query(default=None, alias="status"),
    campaign_id: UUID | None = Query(default=None),
):
    user_id = UUID(user["sub"])
    result = await donation_service.list_donations(
        session,
        user_id=user_id,
        limit=pagination.limit,
        cursor=pagination.cursor,
        status=donation_status,
        campaign_id=campaign_id,
    )
    return paginated_response(result["data"], result["next_cursor"], result["has_more"])


@router.get("/{donation_id}", response_model=DonationDetailResponse, summary="Get donation detail", description="Детальная информация о пожертвовании")
async def get_donation_detail(
    donation_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await donation_service.get_donation(session, donation_id, user_id)
