from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger
from app.core.redis import redis_client

logger = get_logger(__name__)

tags_metadata = [
    {"name": "auth", "description": "Аутентификация: OTP, JWT токены"},
    {"name": "campaigns", "description": "Лента кампаний (публичная)"},
    {"name": "foundations", "description": "Информация о фондах (публичная)"},
    {"name": "profile", "description": "Профиль пользователя"},
    {"name": "donations", "description": "Разовые пожертвования"},
    {"name": "subscriptions", "description": "Подписки на пожертвования"},
    {"name": "transactions", "description": "История транзакций подписок"},
    {"name": "impact", "description": "Импакт и достижения"},
    {"name": "thanks", "description": "Благодарности от фондов"},
    {"name": "patron", "description": "Функции мецената"},
    {"name": "webhooks", "description": "Вебхуки платёжных систем"},
    {"name": "admin-auth", "description": "Аутентификация администратора"},
    {"name": "admin-foundations", "description": "Управление фондами"},
    {"name": "admin-campaigns", "description": "Управление кампаниями"},
    {"name": "admin-media", "description": "Загрузка медиа"},
    {"name": "admin-users", "description": "Управление пользователями"},
    {"name": "admin-stats", "description": "Статистика"},
    {"name": "admin-payouts", "description": "Выплаты фондам"},
    {"name": "admin-achievements", "description": "Управление достижениями"},
    {"name": "admin-logs", "description": "Логи системы"},
    {"name": "admin-admins", "description": "Управление администраторами"},
    {"name": "admin-documents", "description": "Управление документами"},
    {"name": "documents", "description": "Публичные документы"},
    {"name": "payment-methods", "description": "Сохранённые способы оплаты"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup")
    # Verify DB connection
    async with engine.begin() as conn:
        await conn.execute(sa_text("SELECT 1"))
    logger.info("database_connected")

    # Verify Redis connection
    await redis_client.ping()
    logger.info("redis_connected")

    yield

    # Shutdown
    await engine.dispose()
    await redis_client.aclose()
    logger.info("application_shutdown")


from sqlalchemy import text as sa_text  # noqa: E402 — needed after lifespan def


def create_app() -> FastAPI:
    app = FastAPI(
        title="По Рублю API",
        description="REST API для благотворительной платформы «По Рублю»",
        version="1.0.0",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        openapi_tags=tags_metadata,
        redirect_slashes=True,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # --- Routers ---
    from app.api.v1.health import router as health_router
    from app.api.v1.auth import router as auth_router
    from app.api.v1.public.campaigns import router as public_campaigns_router
    from app.api.v1.public.foundations import router as public_foundations_router
    from app.api.v1.public.profile import router as profile_router
    from app.api.v1.public.donations import router as donations_router
    from app.api.v1.public.subscriptions import router as subscriptions_router
    from app.api.v1.public.transactions import router as transactions_router
    from app.api.v1.public.impact import router as impact_router
    from app.api.v1.public.thanks import router as thanks_router
    from app.api.v1.public.patron import router as patron_router
    from app.api.v1.public.documents import router as public_documents_router
    from app.api.v1.public.payment_methods import router as payment_methods_router
    from app.api.v1.webhooks import router as webhooks_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(public_campaigns_router, prefix="/api/v1/campaigns", tags=["campaigns"])
    app.include_router(public_foundations_router, prefix="/api/v1/foundations", tags=["foundations"])
    app.include_router(profile_router, prefix="/api/v1/me", tags=["profile"])
    app.include_router(donations_router, prefix="/api/v1/donations", tags=["donations"])
    app.include_router(subscriptions_router, prefix="/api/v1/subscriptions", tags=["subscriptions"])
    app.include_router(transactions_router, prefix="/api/v1/transactions", tags=["transactions"])
    app.include_router(impact_router, prefix="/api/v1/impact", tags=["impact"])
    app.include_router(thanks_router, prefix="/api/v1/thanks", tags=["thanks"])
    app.include_router(patron_router, prefix="/api/v1/patron/payment-links", tags=["patron"])
    app.include_router(public_documents_router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(payment_methods_router, prefix="/api/v1/payment-methods", tags=["payment-methods"])
    app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])

    # Admin routers
    from app.api.v1.admin import router as admin_router
    app.include_router(admin_router, prefix="/api/v1/admin")

    # Media proxy — serves S3/MinIO files via /media/{s3_key}
    # In production nginx intercepts /media/ before it reaches FastAPI,
    # but this endpoint works as fallback and for local development.
    from app.api.v1.media_proxy import router as media_proxy_router
    app.include_router(media_proxy_router)

    return app


app = create_app()
