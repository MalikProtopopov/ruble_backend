"""Seed 6 documents per ACTIVE campaign: Markdown body + a generated PDF in S3.

For every active campaign this inserts a standard set of legal/reporting
documents. Each document carries:
  - excerpt  — short preview for the list,
  - content  — full Markdown body (read in-app),
  - file_url — a PDF generated from the same text and uploaded to MinIO/S3.

Idempotent: a (campaign, slug) that already exists is skipped, so re-running
only fills gaps. Run inside the backend container:

    docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app \
        backend python seed_campaign_documents.py
"""
import asyncio

import boto3
from botocore.client import Config as BotoConfig
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.slug import slugify
from app.infrastructure.pdf import render_markdown_pdf
from app.models import Campaign, CampaignDocument
from app.models.base import CampaignStatus, uuid7

PUB = settings.S3_PUBLIC_URL.rstrip("/")
BUCKET = settings.S3_BUCKET

s3 = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
    config=BotoConfig(signature_version="s3v4"),
    region_name="us-east-1",
)


# Each document: (title, excerpt, markdown body). {campaign} / {foundation}
# are interpolated per campaign.
DOCUMENTS = [
    (
        "Отчёт о целевом использовании средств",
        "Как расходуются пожертвования по сбору «{campaign}».",
        """# Отчёт о целевом использовании средств

## Сбор «{campaign}»

Фонд **{foundation}** публикует отчёт о расходовании средств, собранных в рамках
сбора «{campaign}». Все пожертвования направляются строго на заявленные цели.

## Структура расходов

- Прямая адресная помощь благополучателям
- Закупка необходимого оборудования и материалов
- Оплата услуг специалистов
- Организационные и административные расходы (не более 20%)

## Контроль

Каждая операция подтверждается первичными документами. Сводный отчёт
обновляется ежемесячно и доступен всем жертвователям. По запросу мы
предоставляем детализацию по конкретному платежу.

Спасибо, что помогаете вместе с нами.""",
    ),
    (
        "Публичная оферта о пожертвовании",
        "Условия, на которых принимается пожертвование по сбору.",
        """# Публичная оферта о добровольном пожертвовании

## 1. Общие положения

Настоящий документ является официальным предложением (офертой) фонда
**{foundation}** заключить договор о благотворительном пожертвовании на цели
сбора «{campaign}».

## 2. Предмет договора

Жертвователь добровольно и безвозмездно передаёт фонду денежные средства
(пожертвование), а фонд принимает их и направляет на уставные цели.

## 3. Порядок внесения

- Пожертвование вносится через платёжные сервисы в приложении.
- Размер пожертвования определяется жертвователем самостоятельно.
- Договор считается заключённым с момента поступления средств.

## 4. Заключительные положения

Совершая пожертвование, жертвователь подтверждает согласие с условиями
настоящей оферты и политикой обработки персональных данных.""",
    ),
    (
        "Политика конфиденциальности",
        "Как мы обрабатываем и защищаем ваши данные.",
        """# Политика конфиденциальности

## Какие данные мы собираем

Фонд **{foundation}** обрабатывает минимально необходимый объём данных:
адрес электронной почты, историю пожертвований и технические сведения об
устройстве.

## Цели обработки

- Проведение и подтверждение пожертвований по сбору «{campaign}»
- Направление уведомлений и отчётов
- Исполнение требований законодательства

## Защита данных

Мы применяем организационные и технические меры защиты. Данные не передаются
третьим лицам, кроме платёжных провайдеров и случаев, предусмотренных законом.

## Ваши права

Вы можете запросить доступ к своим данным, их исправление или удаление,
обратившись в службу поддержки фонда.""",
    ),
    (
        "Согласие на обработку персональных данных",
        "Условия согласия, которое вы даёте при пожертвовании.",
        """# Согласие на обработку персональных данных

Совершая пожертвование на сбор «{campaign}», вы предоставляете фонду
**{foundation}** согласие на обработку ваших персональных данных.

## Перечень данных

- Адрес электронной почты
- Сведения о совершённых пожертвованиях
- Технические данные приложения

## Действия с данными

Сбор, запись, хранение, уточнение, использование и удаление — исключительно в
целях, связанных с благотворительной деятельностью фонда.

## Срок действия

Согласие действует до его отзыва. Отозвать согласие можно в любой момент,
направив обращение в службу поддержки.""",
    ),
    (
        "Положение о проведении сбора средств",
        "Правила и порядок проведения благотворительного сбора.",
        """# Положение о проведении сбора средств

## Назначение

Документ определяет порядок проведения сбора «{campaign}», организованного
фондом **{foundation}**.

## Принципы

- Прозрачность: публикуем цели, ход и итоги сбора
- Адресность: средства идут на заявленную цель
- Отчётность: регулярно публикуем отчёты о расходах

## Завершение сбора

Сбор завершается по достижении цели или в установленный срок. Если средства
собраны сверх необходимого, излишек направляется на близкие по смыслу
программы фонда с уведомлением жертвователей.""",
    ),
    (
        "Финансовый отчёт за 2025 год",
        "Сводные финансовые показатели фонда за 2025 год.",
        """# Финансовый отчёт за 2025 год

## Сбор «{campaign}»

Фонд **{foundation}** представляет сводные показатели за 2025 год.

## Поступления

- Пожертвования физических лиц
- Пожертвования организаций
- Прочие поступления

## Расходы

- Программные расходы (благотворительные программы)
- Содержание и обеспечение деятельности фонда
- Налоги и обязательные платежи

## Заключение

Деятельность фонда соответствует уставным целям. Полная версия отчёта с
приложениями предоставляется по запросу и направляется в контролирующие
органы в установленном порядке.""",
    ),
]


def ensure_bucket() -> None:
    try:
        s3.head_bucket(Bucket=BUCKET)
    except Exception:
        print(f"WARNING: bucket {BUCKET} not reachable/found — uploads may fail")


def upload_pdf(key: str, data: bytes) -> str:
    s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType="application/pdf")
    return f"{PUB}/{key}"


async def main() -> None:
    ensure_bucket()
    created = skipped = 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.active)
        )
        campaigns = list(result.scalars().all())
        print(f"active campaigns: {len(campaigns)}")

        for camp in campaigns:
            foundation_name = "По Рублю"
            existing = await session.execute(
                select(CampaignDocument.slug).where(CampaignDocument.campaign_id == camp.id)
            )
            existing_slugs = set(existing.scalars().all())

            for order, (title, excerpt_t, body_t) in enumerate(DOCUMENTS):
                slug = slugify(title)
                if slug in existing_slugs:
                    skipped += 1
                    continue

                ctx = {"campaign": camp.title, "foundation": foundation_name}
                excerpt = excerpt_t.format(**ctx)
                content = body_t.format(**ctx)

                pdf_bytes = render_markdown_pdf(title, content)
                key = f"documents/campaigns/{camp.id}/{slug}.pdf"
                file_url = upload_pdf(key, pdf_bytes)

                session.add(
                    CampaignDocument(
                        id=uuid7(),
                        campaign_id=camp.id,
                        title=title,
                        slug=slug,
                        excerpt=excerpt,
                        content=content,
                        file_url=file_url,
                        sort_order=order,
                    )
                )
                created += 1

            await session.flush()
            print(f"  {camp.title!r}: documents ready")

        await session.commit()

    print(f"done — created {created}, skipped {skipped} (already existed)")


if __name__ == "__main__":
    asyncio.run(main())
