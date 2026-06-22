"""Local dev seed — comprehensive test data covering the QA checklist.

Run from backend/ with DATABASE_URL pointing at the local `porubly` DB.
Schema is (re)created via Base.metadata.create_all (same approach as tests).
RUNNING THIS DROPS ALL EXISTING DATA in the target DB.
"""

import asyncio
from datetime import datetime, timedelta, timezone, date

from argon2 import PasswordHasher
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
import app.models  # noqa: F401 — register all models on Base.metadata
from app.models import (
    Admin, Campaign, Foundation, User, Donation, Subscription, Transaction,
    PayoutRecord, Achievement, UserAchievement, AllocationChange, NotificationLog,
    MediaAsset, CampaignDocument, ThanksContent,
)
from app.models.document import Document
from app.models.base import (
    Base, uuid7,
    CampaignStatus, FoundationStatus, DocumentStatus, UserRole, PushPlatform,
    DonationStatus, DonationSource, SubscriptionStatus, BillingPeriod,
    AllocationStrategy, PausedReason, TransactionStatus, SkipReason,
    AchievementConditionType, AllocationChangeReason, NotificationStatus,
    MediaAssetType,
)
from app.services.payment import calculate_fees

ADMIN_EMAIL = "admin@porubly.ru"
ADMIN_PASSWORD = "Admin12345!"

ph = PasswordHasher()
now = datetime.now(timezone.utc)
today = date.today()

NOTIF_PREFS = {
    "push_on_payment": True, "push_on_campaign_change": True, "push_daily_streak": True,
    "push_campaign_completed": True, "push_on_donation_reminder": True,
}


def media_url(key: str) -> str:
    return f"{settings.S3_PUBLIC_URL.rstrip('/')}/{key}"


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        # ───────────────────────── Admin ─────────────────────────
        admin = Admin(id=uuid7(), email=ADMIN_EMAIL, password_hash=ph.hash(ADMIN_PASSWORD),
                      name="Local Admin", is_active=True)
        s.add(admin)

        # ─────────────────── Foundations (3 statuses) ───────────────────
        f_active = Foundation(id=uuid7(), name="Фонд «Добрый дом»", legal_name="АНО «Добрый дом»",
                              inn="7700000001", description="Помогаем семьям в трудной ситуации.",
                              website_url="https://example.org", status=FoundationStatus.active, verified_at=now)
        f_pending = Foundation(id=uuid7(), name="Фонд «Надежда»", legal_name="АНО «Надежда»",
                               inn="7700000002", description="На проверке.", status=FoundationStatus.pending_verification)
        f_suspended = Foundation(id=uuid7(), name="Фонд «Архив»", legal_name="АНО «Архив»",
                                 inn="7700000003", description="Приостановлен.", status=FoundationStatus.suspended)
        s.add_all([f_active, f_pending, f_suspended])
        await s.flush()

        # ─────────────────── Campaigns (all 5 statuses) ───────────────────
        c_draft = Campaign(id=uuid7(), foundation_id=f_active.id, title="Черновик сбора",
                           description="Ещё не опубликован.", status=CampaignStatus.draft,
                           goal_amount=300000, collected_amount=0, donors_count=0, urgency_level=3,
                           is_permanent=False, sort_order=10)
        c1 = Campaign(id=uuid7(), foundation_id=f_active.id, title="Лечение Маши",
                      description="Сбор на реабилитацию.", status=CampaignStatus.active,
                      goal_amount=500000, collected_amount=127500, donors_count=3, urgency_level=5,
                      is_permanent=False, ends_at=now + timedelta(days=20), sort_order=1)
        c2 = Campaign(id=uuid7(), foundation_id=f_active.id, title="Тёплые вещи к зиме",
                      description="Одежда для детей.", status=CampaignStatus.active,
                      goal_amount=200000, collected_amount=80000, donors_count=17, urgency_level=3,
                      is_permanent=False, ends_at=now + timedelta(days=45), sort_order=2)
        c_perm = Campaign(id=uuid7(), foundation_id=f_active.id, title="Постоянная помощь фонду",
                          description="Регулярная поддержка.", status=CampaignStatus.active,
                          goal_amount=None, collected_amount=300000, donors_count=120, urgency_level=2,
                          is_permanent=True, sort_order=3)
        c_paused = Campaign(id=uuid7(), foundation_id=f_active.id, title="Приостановленный сбор",
                            description="На паузе.", status=CampaignStatus.paused,
                            goal_amount=150000, collected_amount=40000, donors_count=9, urgency_level=3,
                            is_permanent=False, sort_order=5)
        c_completed = Campaign(id=uuid7(), foundation_id=f_active.id, title="Завершённый сбор",
                               description="Цель достигнута.", status=CampaignStatus.completed,
                               goal_amount=100000, collected_amount=100000, donors_count=88, urgency_level=1,
                               is_permanent=False, ends_at=now - timedelta(days=3), sort_order=6)
        c_archived = Campaign(id=uuid7(), foundation_id=f_active.id, title="Архивный сбор",
                              description="В архиве.", status=CampaignStatus.archived,
                              goal_amount=100000, collected_amount=100000, donors_count=50, urgency_level=1,
                              is_permanent=False, closed_early=True, close_note="Закрыт досрочно.", sort_order=7)
        s.add_all([c_draft, c1, c2, c_perm, c_paused, c_completed, c_archived])
        await s.flush()

        # campaign document + thanks content (for campaign detail screen)
        s.add(CampaignDocument(id=uuid7(), campaign_id=c1.id, title="Мед. заключение",
                               file_url=media_url("documents/med1.pdf"), sort_order=1))
        s.add(ThanksContent(id=uuid7(), campaign_id=c_completed.id, type="video",
                            media_url=media_url("videos/thanks1.mp4"), title="Спасибо!",
                            description="Видео-благодарность."))

        # ─────────────────── Documents (statuses + file/no-file) ───────────────────
        s.add_all([
            Document(id=uuid7(), slug="offerta", title="Публичная оферта", excerpt="Условия сервиса.",
                     content="# Оферта\n\nТекст…", status=DocumentStatus.published, document_version="v1.0",
                     published_at=now, file_url=media_url("documents/offerta.pdf"), sort_order=1, version=1),
            Document(id=uuid7(), slug="privacy", title="Политика конфиденциальности", excerpt="Обработка ПДн.",
                     content="# Политика\n\nТекст…", status=DocumentStatus.published, document_version="v2.0",
                     published_at=now, file_url=None, sort_order=2, version=1),
            Document(id=uuid7(), slug="draft-doc", title="Черновик документа", content="…",
                     status=DocumentStatus.draft, sort_order=3, version=1),
            Document(id=uuid7(), slug="archived-doc", title="Архивный документ", content="…",
                     status=DocumentStatus.archived, published_at=now - timedelta(days=100), sort_order=4, version=1),
        ])

        # ─────────────────── Users (donor/patron, active/inactive) ───────────────────
        donor = User(id=uuid7(), email="donor@example.com", name="Иван Донор", role=UserRole.donor,
                     is_anonymous=False, is_email_verified=True, timezone="Europe/Moscow",
                     notification_preferences=NOTIF_PREFS, push_token="fcm-token-donor", push_platform=PushPlatform.fcm,
                     current_streak_days=10, last_streak_date=today, total_donated_kopecks=150000,
                     total_donations_count=12, is_active=True)
        patron = User(id=uuid7(), email="patron@example.com", name="Пётр Патрон", role=UserRole.patron,
                      is_anonymous=False, is_email_verified=True, timezone="Europe/Moscow",
                      notification_preferences=NOTIF_PREFS, current_streak_days=3, last_streak_date=today,
                      total_donated_kopecks=50000, total_donations_count=4, is_active=True)
        donor_inactive = User(id=uuid7(), email="blocked@example.com", name="Деактивированный", role=UserRole.donor,
                              is_anonymous=False, is_email_verified=True, timezone="Europe/Moscow",
                              notification_preferences=NOTIF_PREFS, total_donated_kopecks=2000,
                              total_donations_count=1, is_active=False)
        anon = User(id=uuid7(), device_id="anon-device-0001", role=UserRole.donor, is_anonymous=True,
                    is_email_verified=False, timezone="Europe/Moscow", notification_preferences=NOTIF_PREFS,
                    is_active=True)
        s.add_all([donor, patron, donor_inactive, anon])
        await s.flush()

        # ─────────────────── Donations (success for refund + statuses) ───────────────────
        def don(user, camp, amount, status, pay_id=None, source=DonationSource.app):
            fees = calculate_fees(amount)
            return Donation(id=uuid7(), user_id=user.id, campaign_id=camp.id, foundation_id=camp.foundation_id,
                            amount_kopecks=amount, platform_fee_kopecks=fees["platform_fee_kopecks"],
                            nco_amount_kopecks=fees["nco_amount_kopecks"], idempotence_key=str(uuid7()),
                            provider_payment_id=pay_id, status=status, source=source)
        donations = [
            don(donor, c1, 50000, DonationStatus.success, "pay-success-refundable-001"),  # ← возврат тестировать тут
            don(donor, c1, 30000, DonationStatus.success, "pay-success-002"),
            don(donor, c1, 20000, DonationStatus.pending, "pay-pending-003"),
            don(donor, c2, 10000, DonationStatus.failed),
            don(donor, c1, 15000, DonationStatus.refunded, "pay-refunded-004"),
            don(patron, c2, 25000, DonationStatus.success, "pay-patron-005", DonationSource.patron_link),
        ]
        s.add_all(donations)

        # ─────────────────── Subscriptions (active/paused/cancelled) ───────────────────
        sub_active = Subscription(id=uuid7(), user_id=donor.id, amount_kopecks=1000,
                                  billing_period=BillingPeriod.weekly, allocation_strategy=AllocationStrategy.specific_campaign,
                                  campaign_id=c1.id, payment_method_id="pm-test-card-001",
                                  status=SubscriptionStatus.active, next_billing_at=now + timedelta(days=5))
        sub_paused = Subscription(id=uuid7(), user_id=donor.id, amount_kopecks=300,
                                  billing_period=BillingPeriod.monthly, allocation_strategy=AllocationStrategy.foundation_pool,
                                  foundation_id=f_active.id, payment_method_id="pm-test-card-001",
                                  status=SubscriptionStatus.paused, paused_reason=PausedReason.user_request, paused_at=now)
        sub_cancelled = Subscription(id=uuid7(), user_id=donor.id, amount_kopecks=500,
                                     billing_period=BillingPeriod.weekly, allocation_strategy=AllocationStrategy.platform_pool,
                                     status=SubscriptionStatus.cancelled, cancelled_at=now - timedelta(days=10))
        s.add_all([sub_active, sub_paused, sub_cancelled])
        await s.flush()

        # ─────────────────── Transactions (для истории + НКО-баланса) ───────────────────
        def txn(sub, camp, amount, status, **kw):
            fees = calculate_fees(amount)
            return Transaction(id=uuid7(), subscription_id=sub.id, campaign_id=camp.id if camp else None,
                               foundation_id=camp.foundation_id if camp else None, amount_kopecks=amount,
                               platform_fee_kopecks=fees["platform_fee_kopecks"], nco_amount_kopecks=fees["nco_amount_kopecks"],
                               idempotence_key=str(uuid7()), status=status, **kw)
        s.add_all([
            txn(sub_active, c1, 7000, TransactionStatus.success, provider_payment_id="txn-success-001"),
            txn(sub_active, c1, 7000, TransactionStatus.failed, attempt_number=1,
                next_retry_at=now + timedelta(days=1), cancellation_reason="insufficient_funds"),
            txn(sub_active, None, 7000, TransactionStatus.skipped, skipped_reason=SkipReason.no_active_campaigns),
        ])

        # ─────────────────── Payouts + ненулевой НКО-баланс ───────────────────
        # НКО по f_active (success донаты + транзакции): nco(50000)+nco(30000)+nco(25000? patron→c2 тоже f_active)+nco(7000 txn)
        # Выплачиваем меньше, чтобы остался due-баланс.
        s.add(PayoutRecord(id=uuid7(), foundation_id=f_active.id, amount_kopecks=50000,
                           period_from=today - timedelta(days=30), period_to=today,
                           transfer_reference="PAY-2026-001", note="Первая выплата", created_by_admin_id=admin.id))

        # ─────────────────── Achievements (3 типа условий + inactive) ───────────────────
        a_streak = Achievement(id=uuid7(), code="streak_7", title="Неделя добра",
                               description="7 дней подряд", icon_url=media_url("images/ach_streak.png"),
                               condition_type=AchievementConditionType.streak_days, condition_value=7, is_active=True)
        a_amount = Achievement(id=uuid7(), code="amount_1000", title="1000 рублей",
                               description="Пожертвовано 1000 ₽", condition_type=AchievementConditionType.total_amount_kopecks,
                               condition_value=100000, is_active=True)
        a_count = Achievement(id=uuid7(), code="count_10", title="10 пожертвований",
                              condition_type=AchievementConditionType.donations_count, condition_value=10, is_active=True)
        a_inactive = Achievement(id=uuid7(), code="streak_30", title="Месяц добра (выкл.)",
                                 condition_type=AchievementConditionType.streak_days, condition_value=30, is_active=False)
        s.add_all([a_streak, a_amount, a_count, a_inactive])
        await s.flush()
        # выдать донору достижения, которым он соответствует
        s.add_all([
            UserAchievement(id=uuid7(), user_id=donor.id, achievement_id=a_streak.id, earned_at=now, notified_at=now),
            UserAchievement(id=uuid7(), user_id=donor.id, achievement_id=a_amount.id, earned_at=now),
            UserAchievement(id=uuid7(), user_id=donor.id, achievement_id=a_count.id, earned_at=now),
        ])

        # ─────────────────── Allocation logs ───────────────────
        s.add_all([
            AllocationChange(id=uuid7(), subscription_id=sub_active.id, from_campaign_id=c_completed.id,
                             to_campaign_id=c1.id, reason=AllocationChangeReason.campaign_completed, notified_at=now),
            AllocationChange(id=uuid7(), subscription_id=sub_active.id, from_campaign_id=c1.id,
                             to_campaign_id=c2.id, reason=AllocationChangeReason.manual_by_admin),
        ])

        # ─────────────────── Notification logs (sent/mock/failed) ───────────────────
        s.add_all([
            NotificationLog(id=uuid7(), user_id=donor.id, push_token="fcm-token-donor",
                            notification_type="donation_success", title="Пожертвование 500₽", body="Спасибо!",
                            data={"type": "donation_success"}, status=NotificationStatus.sent,
                            provider_response={"message_id": "abc123"}),
            NotificationLog(id=uuid7(), user_id=donor.id, push_token=None, notification_type="streak_daily",
                            title="Стрик: 10 дней", body="Так держать!", data={"type": "streak_daily"},
                            status=NotificationStatus.mock),
            NotificationLog(id=uuid7(), user_id=patron.id, push_token="bad-token",
                            notification_type="payment_success", title="Списание", body="…",
                            status=NotificationStatus.failed, provider_response={"error": "UnregisteredError"}),
        ])

        # ─────────────────── Media assets (image/video/audio/document) ───────────────────
        for typ, key, ct, size in [
            (MediaAssetType.image, "images/photo1.jpg", "image/jpeg", 204800),
            (MediaAssetType.video, "videos/clip1.mp4", "video/mp4", 10485760),
            (MediaAssetType.audio, "audio/track1.mp3", "audio/mpeg", 3145728),
            (MediaAssetType.document, "documents/report1.pdf", "application/pdf", 524288),
        ]:
            s.add(MediaAsset(id=uuid7(), s3_key=key, public_url=media_url(key), type=typ,
                             original_filename=key.split("/")[-1], size_bytes=size, content_type=ct,
                             uploaded_by_admin_id=admin.id))

        await s.commit()

    await engine.dispose()
    print("SEED_OK")
    print(f"admin_email={ADMIN_EMAIL}")
    print(f"admin_password={ADMIN_PASSWORD}")
    print("donor=donor@example.com  patron=patron@example.com  inactive=blocked@example.com")


if __name__ == "__main__":
    asyncio.run(main())
