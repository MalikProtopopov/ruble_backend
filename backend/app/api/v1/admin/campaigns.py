"""Admin campaign management endpoints, including documents and thanks content."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import BusinessLogicError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.domain.campaign import InvalidStatusTransition, validate_status_transition
from app.models import CampaignDonor, User
from app.models.base import AllocationChangeReason, CampaignStatus
from app.repositories import campaign_repo, foundation_repo
from app.schemas.campaign import (
    AdminCampaignCreate,
    AdminCampaignDetailResponse,
    AdminCampaignResponse,
    AdminCampaignUpdate,
    CampaignDocumentCreate,
    CampaignDocumentResponse,
    CloseEarlyRequest,
    ForceReallocResponse,
    ThanksContentBrief,
    ThanksContentCreate,
    ThanksContentUpdate,
)
from app.schemas.offline_payment import OfflinePaymentCreate, OfflinePaymentResponse
from app.services.allocation import reallocate_campaign_subscriptions, reallocate_subscription
from app.services.media_asset_resolve import THUMBNAIL_OR_LOGO, VIDEO_ONLY, resolve_public_url
from app.services.notification import send_push
from app.services.payment import check_campaign_auto_complete
from app.services.video_thumbnail import generate_thumbnail_for_video_url

router = APIRouter()
logger = get_logger(__name__)


def _serialize_campaign(c) -> dict:
    data = AdminCampaignResponse.model_validate(c).model_dump(mode="json")
    try:
        data["foundation_name"] = c.foundation.name if c.foundation else None
    except Exception:
        pass
    return data


def _serialize_campaign_detail(c) -> dict:
    data = AdminCampaignDetailResponse.model_validate(c).model_dump(mode="json")
    try:
        data["foundation_name"] = c.foundation.name if c.foundation else None
    except Exception:
        pass
    return data


# --- Campaign CRUD ---


@router.get(
    "",
    summary="List campaigns",
    description="Список кампаний с фильтрацией по статусу, фонду и поиском",
)
async def list_campaigns(
    status: CampaignStatus | None = Query(default=None),
    foundation_id: UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await campaign_repo.list_admin(
        session, pagination, status=status, foundation_id=foundation_id, search=search,
    )
    data = [_serialize_campaign(c) for c in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.post(
    "",
    status_code=201,
    summary="Create campaign",
    description="Создание новой кампании (статус draft)",
)
async def create_campaign(
    body: AdminCampaignCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    foundation = await foundation_repo.get_by_id(session, body.foundation_id)
    if foundation is None:
        raise NotFoundError(message="Фонд не найден")

    # Auto-generate thumbnail from the first frame of the video if the admin
    # didn't provide one explicitly. Best-effort — failures don't block creation.
    thumbnail_url = body.thumbnail_url
    if body.video_url and not thumbnail_url:
        thumbnail_url = await generate_thumbnail_for_video_url(body.video_url)

    campaign = await campaign_repo.create(
        session,
        foundation_id=body.foundation_id,
        title=body.title,
        description=body.description,
        video_url=body.video_url,
        thumbnail_url=thumbnail_url,
        goal_amount=body.goal_amount,
        urgency_level=body.urgency_level,
        is_permanent=body.is_permanent,
        ends_at=body.ends_at,
        sort_order=body.sort_order,
        status=CampaignStatus.draft,
    )
    logger.info("campaign_created", campaign_id=str(campaign.id), admin_id=admin["sub"])
    data = _serialize_campaign(campaign)
    data["foundation_name"] = foundation.name
    return data


@router.get(
    "/{campaign_id}",
    summary="Get campaign detail",
    description="Детальная информация о кампании с документами и благодарностями",
)
async def get_campaign(
    campaign_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id, with_relations=True)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")
    return _serialize_campaign_detail(campaign)


@router.patch(
    "/{campaign_id}",
    summary="Update campaign",
    description="Обновление данных кампании",
)
async def update_campaign(
    campaign_id: UUID,
    body: AdminCampaignUpdate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")

    update_data = body.model_dump(exclude_unset=True)

    if "video_media_asset_id" in update_data:
        aid = update_data.pop("video_media_asset_id")
        update_data.pop("video_url", None)
        update_data["video_url"] = await resolve_public_url(session, aid, allowed_types=VIDEO_ONLY)
    if "thumbnail_media_asset_id" in update_data:
        aid = update_data.pop("thumbnail_media_asset_id")
        update_data.pop("thumbnail_url", None)
        update_data["thumbnail_url"] = await resolve_public_url(
            session, aid, allowed_types=THUMBNAIL_OR_LOGO,
        )

    # Auto-fill thumbnail from the first frame of the (new or existing) video
    # if the resulting state has a video but no thumbnail. Triggers when:
    #   - admin sets video_url without setting thumbnail_url, OR
    #   - admin clears thumbnail_url while leaving video_url, OR
    #   - existing campaign already had this state (handled by backfill endpoint).
    new_video = update_data.get("video_url", campaign.video_url)
    explicit_thumb = (
        update_data["thumbnail_url"] if "thumbnail_url" in update_data else campaign.thumbnail_url
    )
    if new_video and not explicit_thumb:
        generated = await generate_thumbnail_for_video_url(new_video)
        if generated:
            update_data["thumbnail_url"] = generated

    campaign = await campaign_repo.update(session, campaign, update_data)
    logger.info("campaign_updated", campaign_id=str(campaign_id), admin_id=admin["sub"])
    return _serialize_campaign(campaign)


# --- Status transitions ---


async def _transition(session, campaign_id, target_status: str, admin):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")
    try:
        validate_status_transition(campaign.status.value, target_status)
    except InvalidStatusTransition:
        raise BusinessLogicError(
            code="INVALID_STATUS_TRANSITION",
            message=f"Переход из '{campaign.status.value}' в '{target_status}' невозможен",
        )
    return campaign


@router.post(
    "/backfill-thumbnails",
    summary="Backfill thumbnails for campaigns missing them",
    description=(
        "Один раз пройти по всем кампаниям с непустым `video_url` и пустым "
        "`thumbnail_url`, извлечь первый кадр через ffmpeg, загрузить в S3 и "
        "записать ссылку. Идемпотентно — повторный запуск пропустит уже "
        "заполненные. Возвращает количество обработанных и список ошибок."
    ),
)
async def backfill_thumbnails(
    limit: int = Query(default=100, ge=1, le=500, description="Максимум кампаний за один вызов"),
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    from app.models import Campaign

    candidates = (await session.execute(
        select(Campaign)
        .where(
            Campaign.video_url.isnot(None),
            (Campaign.thumbnail_url.is_(None)) | (Campaign.thumbnail_url == ""),
        )
        .limit(limit)
    )).scalars().all()

    filled: list[str] = []
    failed: list[dict] = []
    for c in candidates:
        url = await generate_thumbnail_for_video_url(c.video_url)
        if url:
            c.thumbnail_url = url
            filled.append(str(c.id))
        else:
            failed.append({"id": str(c.id), "video_url": c.video_url})
    await session.flush()

    logger.info(
        "campaigns_thumbnails_backfilled",
        admin_id=admin["sub"],
        filled=len(filled),
        failed=len(failed),
        scanned=len(candidates),
    )
    return {
        "scanned": len(candidates),
        "filled": len(filled),
        "failed": len(failed),
        "filled_ids": filled,
        "failed_items": failed,
    }


@router.post(
    "/{campaign_id}/publish",
    summary="Publish campaign",
    description="Публикация кампании (draft -> active)",
)
async def publish_campaign(
    campaign_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await _transition(session, campaign_id, "active", admin)
    campaign = await campaign_repo.update(session, campaign, {"status": CampaignStatus.active})
    logger.info("campaign_published", campaign_id=str(campaign_id), admin_id=admin["sub"])
    return _serialize_campaign(campaign)


@router.post(
    "/{campaign_id}/pause",
    summary="Pause campaign",
    description="Приостановка активной кампании",
)
async def pause_campaign(
    campaign_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await _transition(session, campaign_id, "paused", admin)
    campaign = await campaign_repo.update(session, campaign, {"status": CampaignStatus.paused})
    logger.info("campaign_paused", campaign_id=str(campaign_id), admin_id=admin["sub"])
    return _serialize_campaign(campaign)


@router.post(
    "/{campaign_id}/complete",
    summary="Complete campaign",
    description="Завершение кампании с реаллокацией подписок",
)
async def complete_campaign(
    campaign_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await _transition(session, campaign_id, "completed", admin)
    campaign = await campaign_repo.update(session, campaign, {"status": CampaignStatus.completed})
    count = await reallocate_campaign_subscriptions(session, campaign_id, "campaign_completed")
    await session.refresh(campaign)
    logger.info("campaign_completed", campaign_id=str(campaign_id), reallocated=count, admin_id=admin["sub"])

    # CLOSE-03: Push to all donors
    donor_result = await session.execute(
        select(User.id, User.push_token)
        .join(CampaignDonor, CampaignDonor.user_id == User.id)
        .where(CampaignDonor.campaign_id == campaign_id, User.push_token.isnot(None))
    )
    for row in donor_result.all():
        await send_push(
            session, user_id=row[0], push_token=row[1],
            notification_type="campaign_completed",
            title="Сбор завершён",
            body=f"Кампания «{campaign.title}» завершена",
            data={"type": "campaign_closed", "campaign_id": str(campaign_id), "closed_early": False},
        )

    return _serialize_campaign(campaign)


@router.post(
    "/{campaign_id}/archive",
    summary="Archive campaign",
    description="Архивирование завершённой кампании",
)
async def archive_campaign(
    campaign_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await _transition(session, campaign_id, "archived", admin)
    campaign = await campaign_repo.update(session, campaign, {"status": CampaignStatus.archived})
    logger.info("campaign_archived", campaign_id=str(campaign_id), admin_id=admin["sub"])
    return _serialize_campaign(campaign)


@router.post(
    "/{campaign_id}/close-early",
    summary="Close campaign early",
    description="Досрочное завершение кампании с указанием причины",
)
async def close_early(
    campaign_id: UUID,
    body: CloseEarlyRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await _transition(session, campaign_id, "completed", admin)
    campaign = await campaign_repo.update(session, campaign, {
        "status": CampaignStatus.completed,
        "closed_early": True,
        "close_note": body.close_note,
    })
    count = await reallocate_campaign_subscriptions(session, campaign_id, "campaign_closed_early")
    await session.refresh(campaign)
    logger.info("campaign_closed_early", campaign_id=str(campaign_id), reallocated=count, admin_id=admin["sub"])

    # CLOSE-03: Push to all donors
    donor_result = await session.execute(
        select(User.id, User.push_token)
        .join(CampaignDonor, CampaignDonor.user_id == User.id)
        .where(CampaignDonor.campaign_id == campaign_id, User.push_token.isnot(None))
    )
    for row in donor_result.all():
        await send_push(
            session, user_id=row[0], push_token=row[1],
            notification_type="campaign_completed",
            title="Сбор завершён",
            body=campaign.close_note or f"Кампания «{campaign.title}» завершена",
            data={"type": "campaign_closed", "campaign_id": str(campaign_id), "closed_early": True},
        )

    return _serialize_campaign(campaign)


@router.post(
    "/{campaign_id}/force-realloc",
    response_model=ForceReallocResponse,
    summary="Force reallocation",
    description="Принудительная реаллокация подписок кампании",
)
async def force_realloc(
    campaign_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")

    subscriptions = await campaign_repo.get_active_subscriptions(session, campaign_id)

    count = 0
    for sub in subscriptions:
        new_campaign = await reallocate_subscription(session, sub, AllocationChangeReason.manual_by_admin)
        if new_campaign is not None:
            count += 1

    await session.flush()
    logger.info("force_realloc", campaign_id=str(campaign_id), reallocated=count, admin_id=admin["sub"])
    return ForceReallocResponse(reallocated_subscriptions=count).model_dump()


# --- Offline payments ---


@router.post(
    "/{campaign_id}/offline-payment",
    status_code=201,
    response_model=OfflinePaymentResponse,
    summary="Create offline payment",
    description="Регистрация офлайн-платежа для кампании",
)
async def create_offline_payment(
    campaign_id: UUID,
    body: OfflinePaymentCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")

    if body.external_reference:
        is_dup = await campaign_repo.find_duplicate_offline_payment(
            session, campaign_id, body.external_reference, body.payment_date, body.amount_kopecks,
        )
        if is_dup:
            raise ConflictError(
                message="Дублирующий офлайн-платёж",
                details={"code": "DUPLICATE_OFFLINE_PAYMENT"},
            )

    admin_id = UUID(admin["sub"])
    payment = await campaign_repo.create_offline_payment(
        session,
        campaign_id=campaign_id,
        amount_kopecks=body.amount_kopecks,
        payment_method=body.payment_method,
        description=body.description,
        external_reference=body.external_reference,
        recorded_by_admin_id=admin_id,
        payment_date=body.payment_date,
    )

    await campaign_repo.atomic_increment_collected(session, campaign_id, body.amount_kopecks)
    await check_campaign_auto_complete(session, campaign_id)
    await session.flush()

    logger.info(
        "offline_payment_created",
        campaign_id=str(campaign_id),
        amount=body.amount_kopecks,
        admin_id=admin["sub"],
    )
    return OfflinePaymentResponse.model_validate(payment).model_dump(mode="json")


@router.get(
    "/{campaign_id}/offline-payments",
    summary="List offline payments",
    description="Список офлайн-платежей кампании",
)
async def list_offline_payments(
    campaign_id: UUID,
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")

    result = await campaign_repo.list_offline_payments(session, campaign_id, pagination)
    data = [OfflinePaymentResponse.model_validate(p).model_dump(mode="json") for p in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


# --- Documents ---


@router.post(
    "/{campaign_id}/documents",
    status_code=201,
    response_model=CampaignDocumentResponse,
    summary="Add document to campaign",
    description="Добавление документа к кампании",
)
async def create_document(
    campaign_id: UUID,
    body: CampaignDocumentCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")

    doc = await campaign_repo.add_document(
        session, campaign_id, title=body.title, file_url=body.file_url, sort_order=body.sort_order,
    )
    logger.info("document_created", campaign_id=str(campaign_id), doc_id=str(doc.id), admin_id=admin["sub"])
    return CampaignDocumentResponse.model_validate(doc).model_dump(mode="json")


@router.delete(
    "/{campaign_id}/documents/{doc_id}",
    status_code=204,
    summary="Delete document",
    description="Удаление документа кампании",
)
async def delete_document(
    campaign_id: UUID,
    doc_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await campaign_repo.get_document(session, campaign_id, doc_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    await campaign_repo.delete_document(session, doc)
    logger.info("document_deleted", campaign_id=str(campaign_id), doc_id=str(doc_id), admin_id=admin["sub"])


# --- Thanks content ---


@router.post(
    "/{campaign_id}/thanks",
    status_code=201,
    summary="Create thanks content",
    description="Создание контента благодарности для кампании",
)
async def create_thanks(
    campaign_id: UUID,
    body: ThanksContentCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await campaign_repo.get_by_id(session, campaign_id)
    if campaign is None:
        raise NotFoundError(message="Кампания не найдена")

    thanks = await campaign_repo.add_thanks(
        session, campaign_id, type=body.type, media_url=body.media_url, title=body.title, description=body.description,
    )
    logger.info("thanks_created", campaign_id=str(campaign_id), thanks_id=str(thanks.id), admin_id=admin["sub"])

    # THANKS-04: Push notification to all donors of this campaign
    if campaign.status == CampaignStatus.active:
        donor_result = await session.execute(
            select(User.id, User.push_token)
            .join(CampaignDonor, CampaignDonor.user_id == User.id)
            .where(CampaignDonor.campaign_id == campaign_id, User.push_token.isnot(None))
        )
        for row in donor_result.all():
            await send_push(
                session, user_id=row[0], push_token=row[1],
                notification_type="thanks_content",
                title="Благодарность от фонда",
                body=f"{campaign.title}: {thanks.title or 'Новое видео/аудио'}",
                data={"type": "thanks_content", "thanks_content_id": str(thanks.id), "campaign_id": str(campaign_id)},
            )

    return ThanksContentBrief.model_validate(thanks).model_dump(mode="json")


@router.patch(
    "/{campaign_id}/thanks/{thanks_id}",
    summary="Update thanks content",
    description="Обновление контента благодарности",
)
async def update_thanks(
    campaign_id: UUID,
    thanks_id: UUID,
    body: ThanksContentUpdate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    thanks = await campaign_repo.get_thanks(session, campaign_id, thanks_id)
    if thanks is None:
        raise NotFoundError(message="Контент благодарности не найден")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(thanks, field, value)
    await session.flush()

    logger.info("thanks_updated", thanks_id=str(thanks_id), admin_id=admin["sub"])
    return ThanksContentBrief.model_validate(thanks).model_dump(mode="json")


@router.delete(
    "/{campaign_id}/thanks/{thanks_id}",
    status_code=204,
    summary="Delete thanks content",
    description="Удаление контента благодарности",
)
async def delete_thanks(
    campaign_id: UUID,
    thanks_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    thanks = await campaign_repo.get_thanks(session, campaign_id, thanks_id)
    if thanks is None:
        raise NotFoundError(message="Контент благодарности не найден")

    await campaign_repo.delete_thanks(session, thanks)
    logger.info("thanks_deleted", thanks_id=str(thanks_id), admin_id=admin["sub"])
