"""Admin maintenance endpoints for saved payment methods.

Used by support / one-shot maintenance scripts:

- POST /admin/payment-methods/backfill-fingerprints — for every PM with NULL
  fingerprint, fetch the original payment from YooKassa, extract card data and
  compute the fingerprint. Required for retroactive deduplication of cards
  saved before migration 008.

- POST /admin/payment-methods/dedupe — find PMs that share a fingerprint per
  user, soft-delete the older duplicates, ensure exactly one is_default per
  user. Idempotent.

Both endpoints are admin-only and intended to be run a handful of times (after
migration, after support cases). They are not on a cron — duplicate creation
is already prevented at write time by the per-fingerprint logic in
account_merge / save_from_yookassa.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_admin
from app.services import payment_method as pm_service

router = APIRouter()


@router.post(
    "/backfill-fingerprints",
    summary="Backfill card fingerprints for legacy payment methods",
    description=(
        "Fetches the original payment from YooKassa for every PaymentMethod "
        "with NULL `card_fingerprint` and computes the fingerprint from "
        "`payment_method.card.first6/last4/expiry`. Idempotent."
    ),
)
async def backfill_fingerprints(
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    return await pm_service.backfill_fingerprints_from_yookassa(session)


@router.post(
    "/dedupe",
    summary="Soft-delete duplicate payment methods per user",
    description=(
        "Groups payment methods by `(user_id, card_fingerprint)`, keeps the "
        "newest in each group, soft-deletes the rest, and ensures exactly one "
        "`is_default` per user. Run after `backfill-fingerprints`. Idempotent."
    ),
)
async def dedupe_payment_methods(
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    return await pm_service.dedupe_payment_methods(session)
