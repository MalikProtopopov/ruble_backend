from fastapi import APIRouter

from app.api.v1.admin.auth import router as auth_router
from app.api.v1.admin.foundations import router as foundations_router
from app.api.v1.admin.campaigns import router as campaigns_router
from app.api.v1.admin.media import router as media_router
from app.api.v1.admin.users import router as users_router
from app.api.v1.admin.stats import router as stats_router
from app.api.v1.admin.payouts import router as payouts_router
from app.api.v1.admin.achievements import router as achievements_router
from app.api.v1.admin.logs import router as logs_router
from app.api.v1.admin.admins import router as admins_router
from app.api.v1.admin.documents import router as documents_router
from app.api.v1.admin.payment_methods import router as payment_methods_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["admin-auth"])
router.include_router(foundations_router, prefix="/foundations", tags=["admin-foundations"])
router.include_router(campaigns_router, prefix="/campaigns", tags=["admin-campaigns"])
router.include_router(media_router, prefix="/media", tags=["admin-media"])
router.include_router(users_router, prefix="/users", tags=["admin-users"])
router.include_router(stats_router, prefix="/stats", tags=["admin-stats"])
router.include_router(payouts_router, prefix="/payouts", tags=["admin-payouts"])
router.include_router(achievements_router, prefix="/achievements", tags=["admin-achievements"])
router.include_router(logs_router, prefix="/logs", tags=["admin-logs"])
router.include_router(admins_router, prefix="/admins", tags=["admin-admins"])
router.include_router(documents_router, prefix="/documents", tags=["admin-documents"])
router.include_router(payment_methods_router, prefix="/payment-methods", tags=["admin-payment-methods"])
