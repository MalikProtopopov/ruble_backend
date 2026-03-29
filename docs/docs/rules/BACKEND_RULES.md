# Backend Rules — AI Coding Guide

> Контекст для AI (Cursor и т.д.) при работе с репозиторием **trihoback**.  
> Фактический код — в `backend/`; при расхождении с документом приоритет у кода.

---

## Стек

| Категория | Технология |
|-----------|------------|
| Язык | Python 3.11 |
| Фреймворк | FastAPI |
| ORM | SQLAlchemy 2.0 (async), asyncpg |
| БД | PostgreSQL 16 |
| Кэш / брокер задач | Redis 7 + **Taskiq** |
| Миграции | Alembic (`backend/alembic/`) |
| Auth | JWT **RS256** (ключи в PEM), access + refresh; пароли — **Argon2id** |
| Валидация | Pydantic v2 |
| Логирование | structlog (JSON в prod) |
| Лимиты | slowapi |
| HTTP-клиент к платежкам | httpx |
| Линтинг / формат | ruff (см. `pyproject.toml`) |

---

## Структура каталогов (как устроен проект)

Проект **не** использует схему `app/modules/{name}/`. Основные слои:

```
backend/app/
  main.py              # FastAPI app, CORS, middleware, роутеры, lifespan
  core/                # config, database, redis, security, exceptions, logging, permissions, pagination …
  api/v1/              # HTTP-роутеры по доменам (auth, subscriptions, webhooks, admin/*, public/* …)
  models/              # SQLAlchemy-модели (+ enums в base.py при необходимости)
  schemas/             # Pydantic-схемы запросов/ответов
  services/            # Бизнес-логика (часто пакеты: subscriptions/, exports/, event_registration/ …)
  tasks/               # Taskiq: broker, email_tasks, telegram_tasks, scheduler …
```

### Правила

- **Бизнес-логика** — в `services/` (и вложенных модулях), а не в толстых роутерах.
- **Роуты** — тонкие: парсинг входа, зависимости `Depends`, вызов сервиса, ответ.
- **Модели** — таблицы и связи; общие миксины — `app/models/base.py`.
- **Схемы** — контракт API; для ответов из ORM — `model_config = ConfigDict(from_attributes=True)`.

Пример паттерна (идея, не копировать дословно):

```python
# api/v1/example.py
@router.post("/items", response_model=ItemResponse, status_code=201)
async def create_item(
    data: ItemCreate,
    db: AsyncSession = Depends(get_db_session),
    _: AdminUser = Depends(require_staff_admin),  # или другая зависимость роли
):
    return await ItemService(db).create(data)
```

---

## База данных и модели

### Миксины (`app/models/base.py`)

- **`UUIDMixin`** — первичный ключ **UUID v7** (`uuid_utils`), не v4.
- **`TimestampMixin`** — `created_at` / `updated_at` с `server_default=func.now()`.
- **`SoftDeleteMixin`** — `is_deleted`, `deleted_at` (используется не везде — смотреть конкретную модель).

`VersionMixin` в коде может отсутствовать — не выдумывать, проверять `base.py`.

### Правила

- Для enum-подобных полей часто используются **PostgreSQL native enum** (`SAEnum` в `base.py`), не только `CheckConstraint`.
- Внешние ключи: явно указывать `ondelete` (CASCADE / SET NULL и т.д.).
- Индексы — на фильтры и сортировки в списках.

---

## Миграции (Alembic)

Команды из каталога `backend/` (или через `docker compose exec backend`):

```bash
alembic revision --autogenerate -m "описание"
alembic upgrade head
alembic downgrade -1
```

- Проверять сгенерированный код вручную.
- `downgrade()` должен быть осмысленным.

---

## Pydantic и API

- Паттерны **Create / Update / Response** по месту использования; имена файлов — по домену (`schemas/subscriptions.py` и т.д.).
- Пароли и токены в **Response** не отдавать.
- Пагинация — см. `app/core/pagination.py` и существующие list-эндпоинты.

### Ошибки

Стандартное тело ошибки приложения — **обёртка `error`**, не полный RFC 7807:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "…",
    "details": {}
  }
}
```

Исключения: `AppError` и наследники в `app/core/exceptions.py`, хендлеры в `register_exception_handlers`.

### Префиксы URL

- Основной API: `/api/v1/...`
- Публичные: `/api/v1/public/...`
- Админка: `/api/v1/...` с проверкой роли (staff)
- Webhooks: `/api/v1/webhooks/...` (Moneta, kassa, Telegram и т.д.)

Health: **`GET /api/v1/health`** (используется в Docker healthcheck и деплое).

---

## Аутентификация и роли

- JWT подписывается **RS256**; пути к ключам — `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` (в контейнере часто volume `./backend/keys` → `/app/keys`).
- В payload access-токена: `sub` (user id), `role`, `type`, `aud`, `iss`, сроки.
- **Multi-tenant `tenant_id` в JWT в этом проекте нет** — не добавлять в правила вымышленный контекст тенанта.
- Роли для UI/доступа к разделам — см. `app/core/permissions.py`: staff (`admin`, `manager`, `accountant`), клиенты (`doctor`, `user`, `pending`). Точные проверки в эндпоинтах — через зависимости в `core/security.py` / админские deps.

В **production** при старте выполняется `_validate_production_config()` в `main.py`: сильные секреты, ключи JWT, `DATABASE_URL`, обязательные поля Moneta/YooKassa при выбранном провайдере, фискализация и т.д.

---

## Фоновые задачи

- **Taskiq** worker: сервис `worker` в compose, команда `taskiq worker app.tasks:broker`.
- Задачи — в `app/tasks/`; планировщик — `scheduler.py` при включённой конфигурации.

---

## Платежи и внешние интеграции

- Провайдер задаётся **`PAYMENT_PROVIDER`** (`moneta` — основной сценарий, опционально `yookassa`).
- Логика создания платежей и вебхуков — `services/payment_*`, `api/v1/webhooks.py`, клиенты в `services/payment_providers/`.
- Фискализация Pay URL / kassa — `services/kassa_payanyway_fiscal.py` (при включённых настройках).

При изменении платежного потока сверяться с `docs/handoff/kassaspecification.md` и `docs/env-production-trichologia.ru.template.md`.

---

## S3 / медиа

- Dev и prod в compose используют **MinIO** (S3-совместимый endpoint внутри сети).
- Публичные URL медиа в prod часто идут через **nginx** `/media/` → proxy на MinIO bucket (см. `nginx/templates/api.conf.template`).

---

## Логирование

```python
from app.core.logging import get_logger

logger = get_logger(__name__)
logger.info("event_name", key=value)
```

События — структурированные поля, без логирования секретов и полных тел платежных callback’ов в открытом виде.

---

## Код-стиль

- Type hints по возможности на публичных функциях и методах.
- Следовать существующему стилю файла (импорты, `from __future__ import annotations` где уже принято).
- **ruff** — единый линтер/форматер; перед коммитом прогон по проекту.

---

## Тесты

- `backend/tests/`, **pytest**, async-тесты с маркерами по необходимости.
- При добавлении критичной логики — тесты рядом с доменом (как уже сделано для kassa/webhooks и т.д.).

---

## Чек-лист для AI при новой фиче

- [ ] Роутер в `api/v1/`, схемы в `schemas/`, логика в `services/`
- [ ] При необходимости — модель + миграция Alembic
- [ ] Ошибки через `AppError` / существующие типы, не «голый» HTTPException без стиля проекта
- [ ] Права доступа согласованы с ролями (`permissions` / deps)
- [ ] Для prod — новые секреты отражены в `env.prod.example` или шаблоне документации, не в git с реальными значениями
- [ ] Health / критичные пути не ломают `/api/v1/health`
