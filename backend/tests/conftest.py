"""Shared test fixtures for the По Рублю API test suite."""

import hashlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Override settings BEFORE importing app modules
os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_PRIVATE_KEY_PATH", "keys/private.pem")
os.environ.setdefault("JWT_PUBLIC_KEY_PATH", "keys/public.pem")
os.environ.setdefault("NOTIFICATION_PROVIDER", "mock")
os.environ.setdefault("EMAIL_PROVIDER", "mock")

from app.core.security import create_access_token, create_refresh_token  # noqa: E402
from app.models.base import uuid7  # noqa: E402
from app.models import (  # noqa: E402
    Admin,
    Campaign,
    CampaignDocument,
    Donation,
    Foundation,
    OfflinePayment,
    RefreshToken,
    Subscription,
    ThanksContent,
    Transaction,
    User,
)
from app.models.base import (  # noqa: E402
    AllocationStrategy,
    Base,
    BillingPeriod,
    CampaignStatus,
    DonationSource,
    DonationStatus,
    FoundationStatus,
    SubscriptionStatus,
    TransactionStatus,
    UserRole,
)

_ph = PasswordHasher()

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


def _make_engine():
    return create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database():
    """Create all tables once per test session."""
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Per-test database session. Rolls back all changes after the test."""
    engine = _make_engine()
    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _noop_lifespan(app):
    """Replace the real lifespan to skip DB/Redis ping at startup."""
    yield


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    """HTTPX AsyncClient bound to the FastAPI app with DB override."""
    from app.core.database import get_db_session
    from app.main import create_app

    app = create_app()
    # Disable lifespan to avoid connecting to DB/Redis in tests
    app.router.lifespan_context = _noop_lifespan

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _make_access_token(subject_id: UUID, role: str) -> str:
    return create_access_token(subject_id, role)


def _make_refresh_token(subject_id: UUID) -> str:
    return create_refresh_token(subject_id)


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------


async def create_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    role: UserRole = UserRole.donor,
    is_active: bool = True,
    name: str | None = "Test User",
) -> User:
    user = User(
        id=uuid7(),
        email=email or f"user-{uuid7().hex}@test.com",
        name=name,
        role=role,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def create_admin(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str = "TestPassword123",
    name: str = "Test Admin",
    is_active: bool = True,
) -> Admin:
    admin = Admin(
        id=uuid7(),
        email=email or f"admin-{uuid7().hex}@test.com",
        password_hash=_ph.hash(password),
        name=name,
        is_active=is_active,
    )
    db.add(admin)
    await db.flush()
    return admin


async def create_foundation(
    db: AsyncSession,
    *,
    name: str = "Test Foundation",
    status: FoundationStatus = FoundationStatus.active,
    inn: str | None = None,
) -> Foundation:
    foundation = Foundation(
        id=uuid7(),
        name=name,
        legal_name=f"ООО «{name}»",
        inn=inn or f"{uuid7().int % 10**12:012d}",
        status=status,
    )
    db.add(foundation)
    await db.flush()
    return foundation


async def create_campaign(
    db: AsyncSession,
    foundation: Foundation,
    *,
    title: str = "Test Campaign",
    status: CampaignStatus = CampaignStatus.active,
    goal_amount: int | None = 1000000,
    collected_amount: int = 0,
    is_permanent: bool = False,
    urgency_level: int = 3,
) -> Campaign:
    campaign = Campaign(
        id=uuid7(),
        foundation_id=foundation.id,
        title=title,
        status=status,
        goal_amount=goal_amount,
        collected_amount=collected_amount,
        is_permanent=is_permanent,
        urgency_level=urgency_level,
    )
    db.add(campaign)
    await db.flush()
    return campaign


async def create_subscription(
    db: AsyncSession,
    user: User,
    *,
    amount_kopecks: int = 300,
    billing_period: BillingPeriod = BillingPeriod.monthly,
    allocation_strategy: AllocationStrategy = AllocationStrategy.platform_pool,
    status: SubscriptionStatus = SubscriptionStatus.active,
    campaign_id: UUID | None = None,
    foundation_id: UUID | None = None,
) -> Subscription:
    sub = Subscription(
        id=uuid7(),
        user_id=user.id,
        amount_kopecks=amount_kopecks,
        billing_period=billing_period,
        allocation_strategy=allocation_strategy,
        status=status,
        campaign_id=campaign_id,
        foundation_id=foundation_id,
        next_billing_at=datetime.now(timezone.utc) + timedelta(days=30) if status == SubscriptionStatus.active else None,
    )
    db.add(sub)
    await db.flush()
    return sub


async def create_donation(
    db: AsyncSession,
    user: User,
    campaign: Campaign,
    *,
    amount_kopecks: int = 10000,
    status: DonationStatus = DonationStatus.success,
    source: DonationSource = DonationSource.app,
) -> Donation:
    from app.services.payment import calculate_fees

    fees = calculate_fees(amount_kopecks)
    donation = Donation(
        id=uuid7(),
        user_id=user.id,
        campaign_id=campaign.id,
        foundation_id=campaign.foundation_id,
        amount_kopecks=amount_kopecks,
        platform_fee_kopecks=fees["platform_fee_kopecks"],
        nco_amount_kopecks=fees["nco_amount_kopecks"],
        idempotence_key=str(uuid7()),
        status=status,
        source=source,
    )
    db.add(donation)
    await db.flush()
    return donation


async def create_transaction(
    db: AsyncSession,
    subscription: Subscription,
    campaign: Campaign,
    *,
    amount_kopecks: int = 9000,
    status: TransactionStatus = TransactionStatus.success,
) -> Transaction:
    from app.services.payment import calculate_fees

    fees = calculate_fees(amount_kopecks)
    txn = Transaction(
        id=uuid7(),
        subscription_id=subscription.id,
        campaign_id=campaign.id,
        foundation_id=campaign.foundation_id,
        amount_kopecks=amount_kopecks,
        platform_fee_kopecks=fees["platform_fee_kopecks"],
        nco_amount_kopecks=fees["nco_amount_kopecks"],
        idempotence_key=str(uuid7()),
        status=status,
    )
    db.add(txn)
    await db.flush()
    return txn


async def create_refresh_token_record(
    db: AsyncSession,
    *,
    user_id: UUID | None = None,
    admin_id: UUID | None = None,
    token_str: str | None = None,
) -> tuple[RefreshToken, str]:
    """Create a RefreshToken DB record. Returns (record, raw_token_string)."""
    raw = token_str or f"rt-{uuid7().hex}"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    rt = RefreshToken(
        id=uuid7(),
        user_id=user_id,
        admin_id=admin_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(rt)
    await db.flush()
    return rt, raw


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    return await create_user(db)


@pytest_asyncio.fixture
async def patron_user(db: AsyncSession) -> User:
    return await create_user(db, role=UserRole.patron)


@pytest_asyncio.fixture
async def admin(db: AsyncSession) -> Admin:
    return await create_admin(db)


@pytest_asyncio.fixture
async def foundation(db: AsyncSession) -> Foundation:
    return await create_foundation(db)


@pytest_asyncio.fixture
async def campaign(db: AsyncSession, foundation: Foundation) -> Campaign:
    return await create_campaign(db, foundation)


@pytest_asyncio.fixture
async def donor_headers(user: User) -> dict:
    return auth_header(_make_access_token(user.id, "donor"))


@pytest_asyncio.fixture
async def patron_headers(patron_user: User) -> dict:
    return auth_header(_make_access_token(patron_user.id, "patron"))


@pytest_asyncio.fixture
async def admin_headers(admin: Admin) -> dict:
    return auth_header(_make_access_token(admin.id, "admin"))
