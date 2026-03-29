# Функциональные требования: API «По Рублю» v3.0

> **Тип системы:** REST API для мобильного приложения (Flutter iOS/Android), с перспективой подключения веб-клиента.
> **Стек:** FastAPI + PostgreSQL 16 + Redis 7 + Taskiq + YooKassa + Docker
> **Хранилище медиа:** S3-совместимое (Selectel / Timeweb Cloud / локальный MinIO)
> **Все суммы:** в копейках (integer). Все даты: UTC. Все UUID v7.
> **UUID v7** (библиотека `uuid_utils`). Монотонные, эффективнее для B-tree индексов PostgreSQL.

---

## 0. Соглашения документа

### Формат ошибок (единый для всего API)

```json
{
  "error": {
    "code": "SUBSCRIPTION_LIMIT_EXCEEDED",
    "message": "Максимальное количество активных подписок достигнуто",
    "details": {}
  }
}
```

Стандартные HTTP-коды: `400` — ошибка валидации, `401` — не авторизован, `403` — нет прав, `404` — не найдено, `409` — конфликт, `422` — ошибка бизнес-логики, `429` — превышен rate limit, `500` — ошибка сервера.

Дополнительные бизнес-коды:
- `ACCOUNT_DEACTIVATED` (403) — аккаунт деактивирован администратором
- `AUTH_REQUIRED` (401) — требуется авторизация (пользователь с email уже зарегистрирован)
- `EMAIL_REQUIRED` (400) — email обязателен для неавторизованных пользователей

### Пагинация (cursor-based, единый стандарт)

```json
// Request: GET /api/v1/campaigns?limit=20&cursor=eyJpZCI6IjEyMyJ9
// Response:
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6IjE0MyJ9",
    "has_more": true,
    "total": null
  }
}
```

Cursor — base64-encoded JSON с последним `id` и `sort_key`. Limit по умолчанию: 20, максимум: 100.

### Rate Limiting

| Endpoint | Лимит |
|---|---|
| `POST /auth/send-otp` | 3 запроса / 10 мин / IP |
| `POST /auth/verify-otp` | 5 попыток / 15 мин / email или телефон |
| `POST /subscriptions` | 10 запросов / час / user |
| Все остальные | 100 запросов / мин / user |

При превышении: `429 Too Many Requests` + заголовок `Retry-After: {seconds}`.

---

## 1. Роли и доступ

| Роль | Описание | Аутентификация |
|---|---|---|
| **Гость** | Просмотр ленты и деталей кампаний. Без права платить. | — |
| **Донор (Donor)** | Подписки, разовые донаты, история, импакт, шеринг. | JWT (email OTP — см. решение OQ-03) |
| **Меценат (Patron)** | Донор с расширенными правами: может формировать крупные платёжные ссылки для закрытия сборов. Назначается вручную администратором. | JWT (тот же механизм что у Donor) |
| **Администратор (Admin)** | Управление всем контентом, фондами, пользователями, статистикой, офлайн-платежами. | JWT (email + пароль), отдельный JWT secret |
| **Менеджер фонда (Foundation Manager)** | Статистика и контент своих кампаний. | JWT. **v2, не реализовывать в MVP.** |

---

## 2. Принятые решения по архитектуре

### OQ-03: Аутентификация — email OTP вместо SMS

**Решение: аутентификация по email + OTP-код на почту.**

SMS-код юридически не требуется. Российское законодательство (ФЗ-152, ФЗ-115) не обязывает благотворительные приложения с микро-платежами использовать именно SMS. Выбор метода аутентификации — продуктовое решение. Email OTP: бесплатно или почти бесплатно (SendGrid free tier — 100 писем/день, Unisender, MailJet), при этом не уступает по безопасности.

**Что меняется в сущностях:** `User.phone` → `User.email` как основной идентификатор. Поле `phone` остаётся опциональным — пользователь может добавить его для уведомлений.

**Код OTP:** 6 цифр, TTL 10 минут, max 5 попыток. Хранить hashed (bcrypt или SHA-256 + salt).

**Если в будущем понадобится SMS:** провайдер подключается как альтернативный канал доставки OTP без изменения логики кодов. Достаточно добавить SMS-транспорт в модуль нотификаций.

### OQ-02: Выплаты фондам — один общий счёт + ручные переводы

**Решение: один ЮKassa-аккаунт «По Рублю», ручные переводы фондам.**

Юридическое оформление: **агентский договор** с каждым НКО-партнёром. Платформа действует как агент, принимающий пожертвования от имени и в пользу фонда. Вознаграждение агента — 15% комиссии. Это стандартная схема для краудфандинговых и благотворительных платформ в России (Благо.ру, «Нужна помощь» работали именно так).

Важно: агентский договор прямо разрешает платформе удерживать комиссию до перечисления остатка. Перечислять фондам — по договорённости (еженедельно, ежемесячно). Каждый перевод фиксируется в системе как `PayoutRecord`.

### OQ-04: Хранилище медиа — S3-совместимое

**Решение: Selectel Object Storage или Timeweb Cloud S3 (оба совместимы с boto3/s3fs).**

На старте при ограниченном бюджете — локальный MinIO в Docker-контейнере с той же S3 API. Переключение на облако = смена одной env-переменной `S3_ENDPOINT_URL`. Хранение обязательно в России (ФЗ-152).

### OQ-05: Push-уведомления — провайдер-агностичная архитектура

**Решение: реализовать через абстракцию `NotificationProvider`.**

Код строится так, что конкретный провайдер — это подключаемый модуль. Пока нет ключей Firebase — используется `MockNotificationProvider`, который пишет уведомления в лог и в таблицу `notification_log` в БД. Когда ключи появятся — добавляется `FirebaseNotificationProvider`, переключается через env-переменную `NOTIFICATION_PROVIDER=firebase`.

```
NOTIFICATION_PROVIDER=mock    # пишет в лог, тестируемо
NOTIFICATION_PROVIDER=firebase # реальные push через FCM/APNs
```

Таблица `notification_log` используется для тестирования: в тестах проверять что нужные уведомления попали в лог с правильными данными. При переключении на Firebase тесты работают без изменений.

---

## 3. Сущности (Entities)

### 3.0 Общие миксины

Все сущности наследуют стандартные миксины для унификации полей и поведения.

**UUIDMixin** — `id: UUID v7, PK, default=uuid7()`. Библиотека `uuid_utils`. UUID v7 монотонны и оптимальны для B-tree индексов PostgreSQL — новые записи всегда добавляются в конец индекса, избегая random page splits.

**TimestampMixin** — `created_at: datetime (UTC, server_default=now())`, `updated_at: datetime (UTC, onupdate=now())`.

**SoftDeleteMixin** — `is_deleted: bool (default=false)`, `deleted_at: datetime (nullable)`. Применяется к сущностям: **User**, **Subscription**, **Donation**. Все SELECT-запросы по умолчанию фильтруют `WHERE is_deleted = false`. Для админки — отдельные эндпоинты без фильтра.

> **Уточнение для Subscription:** поле `cancelled_at` означает дату отмены подписки пользователем (бизнес-действие). Поле `deleted_at` из SoftDeleteMixin — техническое soft-удаление записи (например, при анонимизации пользователя по ФЗ-152). Это разные события: подписка может быть `cancelled`, но не `deleted`.

### 3.1 Foundation (Фонд)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| name | string(255) | Публичное название |
| legal_name | string(500) | Юридическое название |
| inn | string(12) | ИНН — обязательно для верификации |
| description | text | Описание (до 2000 символов) |
| logo_url | string | URL логотипа (CDN) |
| website_url | string | Официальный сайт (nullable) |
| status | enum | `pending_verification`, `active`, `suspended` |
| yookassa_shop_id | string | Nullable. На старте — общий счёт платформы. |
| verified_at | datetime | Дата верификации (nullable) |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

**Бизнес-правило:** кампании фонда `suspended` не показываются в публичной ленте.

### 3.2 Campaign (Кампания)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| foundation_id | UUID v7 | FK → Foundation |
| title | string(255) | Заголовок |
| description | text | Описание (до 5000 символов) |
| video_url | string | URL видео (CDN, nullable) |
| thumbnail_url | string | URL превью |
| status | enum | `draft`, `active`, `paused`, `completed`, `archived` |
| goal_amount | integer | Целевая сумма, копейки (nullable для бессрочных) |
| collected_amount | integer | Собрано, копейки. Default: 0. Атомарное обновление. |
| donors_count | integer | Уникальные доноры. Default: 0. Атомарное обновление. |
| urgency_level | integer | 1–5. Default: 3. |
| is_permanent | boolean | Бессрочный — не закрывается автоматически. Default: false. |
| ends_at | datetime | Дата окончания (nullable) |
| sort_order | integer | Ручная сортировка. Default: 0. |
| closed_early | boolean | Досрочно закрыт. Default: false. |
| close_note | text | Комментарий к закрытию (для пользователей, nullable). Например: «Нам удалось собрать X₽ из Y₽. Все средства переданы фонду.» |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

**Бизнес-правила:**
- Автоматически `completed` при `collected_amount >= goal_amount`, если `is_permanent = false`.
- `collected_amount` обновлять только атомарным `UPDATE ... SET collected_amount = collected_amount + :amount`.
- При досрочном закрытии: `status = completed`, `closed_early = true`, `close_note = <текст>`.

**Граф переходов статуса кампании:**

```
draft ──→ active ──→ paused ──→ active
              │                    │
              │                    ▼
              ├──→ completed ──→ archived
              │        ▲
              │        │ (collected >= goal, ends_at, close-early)
              └────────┘
```

- `draft → active` — публикация (Admin: POST .../publish)
- `active → paused` — приостановка (Admin: POST .../pause)
- `paused → active` — возобновление (Admin: POST .../publish)
- `active → completed` — автоматически при достижении цели, по дате `ends_at`, или досрочно (Admin: POST .../close-early)
- `completed → archived` — архивация (Admin: POST .../archive)
- Переходы назад (completed → active и т.д.) запрещены.

### 3.2а CampaignDonors (Уникальные доноры кампании)

Таблица для точного подсчёта уникальных доноров кампании. Используется вместо `COUNT(DISTINCT user_id)` по транзакциям, что было бы медленно на больших объёмах.

| Поле | Тип | Описание |
|---|---|---|
| campaign_id | UUID v7 | FK → Campaign. Часть составного PK. |
| user_id | UUID v7 | FK → User. Часть составного PK. |
| first_at | datetime | UTC. Дата первого доната в эту кампанию. |

**PK:** `(campaign_id, user_id)` — составной первичный ключ.

**Логика вставки:**
```sql
INSERT INTO campaign_donors (campaign_id, user_id, first_at)
VALUES (:campaign_id, :user_id, now())
ON CONFLICT (campaign_id, user_id) DO NOTHING;
```

При `INSERT ... ON CONFLICT DO NOTHING` — если пользователь уже жертвовал в эту кампанию, вставка игнорируется. Поле `first_at` сохраняет дату самого первого доната.

**Бизнес-правило:** инкремент `campaign.donors_count` выполнять только если `INSERT` вернул `rowcount = 1` (то есть донор действительно новый). Это гарантирует точность счётчика уникальных доноров.

### 3.3 Campaign Document

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| campaign_id | UUID v7 | FK → Campaign |
| title | string(255) | Название документа |
| file_url | string | URL PDF (S3) |
| sort_order | integer | Порядок |
| created_at | datetime | UTC |

### 3.4 Thanks Content (Благодарность от фонда)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| campaign_id | UUID v7 | FK → Campaign |
| type | enum | `video`, `audio` |
| media_url | string | URL медиа (CDN) |
| title | string(255) | Заголовок (nullable) |
| description | text | Текст (nullable) |
| created_at | datetime | UTC |

**Бизнес-правило:** показывать донору после успешного списания в эту кампанию, не чаще раза на устройство.

### 3.4а ThanksContentShown (Показы благодарностей)

Таблица фиксирует факт показа конкретной благодарности конкретному пользователю на конкретном устройстве. Используется для выполнения правила «не чаще раза на устройство».

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User |
| thanks_content_id | UUID v7 | FK → ThanksContent |
| device_id | string | Идентификатор устройства (из заголовка X-Device-Id) |
| shown_at | datetime | UTC. Время показа. |

**UNIQUE constraint:** `(user_id, thanks_content_id)` — один пользователь видит одну благодарность максимум один раз (независимо от устройства).

> **Retention:** записи старше 12 месяцев можно удалять пакетно (cron-задача). После удаления пользователь может увидеть благодарность повторно, что допустимо для старого контента.

### 3.5 User (Пользователь)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| email | string(255) | Email. Unique. Основной идентификатор. |
| phone | string(20) | Телефон E.164 (nullable, опционально) |
| name | string(100) | Имя (nullable) |
| avatar_url | string | URL аватара (nullable) |
| role | enum | `donor`, `patron`. Default: `donor`. |
| push_token | string | FCM/APNs токен (nullable). Обновляется при входе. |
| push_platform | enum | `fcm`, `apns` (nullable) |
| timezone | string | IANA timezone. Default: `Europe/Moscow`. |
| notification_preferences | jsonb | Настройки уведомлений (см. ниже) |
| is_active | boolean | Default: true. |
| current_streak_days | integer | Текущая длина streak в днях. Default: 0. Кэш-поле. |
| last_streak_date | date | UTC-дата последнего засчитанного streak-дня. Nullable. |
| total_donated_kopecks | bigint | Общая сумма всех успешных платежей (копейки). Default: 0. Кэш-поле. |
| total_donations_count | integer | Общее количество успешных платежей. Default: 0. Кэш-поле. |
| next_streak_push_at | datetime | UTC. Время следующего streak-пуша (для шедулера). Nullable. |
| is_deleted | boolean | Default: false. SoftDeleteMixin. |
| deleted_at | datetime | UTC. Nullable. SoftDeleteMixin. |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

**Логика streak-кэша:**
- При каждом `success` Transaction/Donation: если `last_streak_date < today(UTC)` → `current_streak_days += 1`, `last_streak_date = today(UTC)`.
- Если `last_streak_date < yesterday(UTC)` → streak сброшен: `current_streak_days = 1`, `last_streak_date = today(UTC)`.
- `skipped` с `skipped_reason = no_active_campaigns` также засчитывается как streak-день (streak не прерывается).
- Кэш-поля обновляются атомарно в той же транзакции, что и основная операция.
- `next_streak_push_at` рассчитывается как `today + 1 day, 12:00 в timezone пользователя`, используется шедулером для NOTIF-08.

**Структура `notification_preferences`:**
```json
{
  "push_on_payment": true,
  "push_on_campaign_change": true,
  "push_daily_streak": false,
  "push_campaign_completed": true
}
```

**Бизнес-правило `is_active`:**
- При `is_active = false` — пользователь не может авторизоваться. При попытке верификации OTP возвращается `403 ACCOUNT_DEACTIVATED` с сообщением «Ваш аккаунт деактивирован. Обратитесь в поддержку.»
- Деактивация выполняется только администратором через `POST /admin/users/{id}/deactivate`.
- При деактивации: все refresh-токены отзываются, активные подписки приостанавливаются (`paused_reason = user_request`).
- При активации (`POST /admin/users/{id}/activate`): подписки НЕ возобновляются автоматически — пользователь делает это вручную.

### 3.6 OTP Code

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| email | string | Email получателя |
| code_hash | string | Hashed код (не plain text) |
| expires_at | datetime | UTC. TTL: 10 минут. |
| is_used | boolean | Default: false. |
| attempts | integer | Неверных попыток. Max: 5. |
| created_at | datetime | UTC |

### 3.6а RefreshToken (Токены обновления)

Хранение refresh-токенов для реализации token rotation и возможности принудительного отзыва сессий.

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User. Nullable (заполняется для donor/patron). |
| admin_id | UUID v7 | FK → Admin. Nullable (заполняется для админов). |
| token_hash | string | SHA-256 хэш refresh-токена. Unique. |
| expires_at | datetime | UTC. TTL: 30 дней. |
| is_used | boolean | Default: false. При rotation — помечается true. |
| is_revoked | boolean | Default: false. При logout или принудительном отзыве. |
| created_at | datetime | UTC |

**CHECK constraint:** `CHECK (user_id IS NOT NULL OR admin_id IS NOT NULL)` — токен всегда привязан к кому-то.

**Бизнес-правила:**
- При `POST /auth/refresh`: найти токен по `token_hash`, проверить `is_used = false`, `is_revoked = false`, `expires_at > now()`. Пометить `is_used = true`, создать новую пару access + refresh.
- При `POST /auth/logout` (donor) или `POST /admin/auth/logout` (admin): пометить `is_revoked = true`.
- Если обнаружено повторное использование уже `is_used = true` токена — это признак компрометации. Отозвать все активные refresh-токены пользователя/админа.
- Cron-задача: удалять записи с `expires_at < now() - 7 days` (grace period для аналитики).

### 3.7 Donation (Разовый платёж)

Отдельная сущность для разовых пожертвований — без подписки.

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User. Nullable — анонимный донат через ссылку мецената. |
| campaign_id | UUID v7 | FK → Campaign. Куда идёт донат. |
| foundation_id | UUID v7 | FK → Foundation. Фонд кампании (денормализация для отчётов). |
| amount_kopecks | integer | Сумма. Любое значение ≥ 1000 коп (10 руб — минимум для разового). |
| platform_fee_kopecks | integer | 15% от суммы. |
| acquiring_fee_kopecks | integer | Комиссия ЮKassa. |
| nco_amount_kopecks | integer | Итого НКО = amount - platform_fee - acquiring_fee. |
| provider_payment_id | string | ID платежа ЮKassa (nullable до оплаты). |
| idempotence_key | string | UUID. Unique. |
| payment_url | string | Ссылка на оплату ЮKassa (nullable — для patron-доната через ссылку). |
| status | enum | `pending`, `success`, `failed`, `refunded` |
| source | enum | `app` (стандартный донат из приложения), `patron_link` (оплата по ссылке мецената), `offline` (записан вручную) |
| is_deleted | boolean | Default: false. SoftDeleteMixin. |
| deleted_at | datetime | UTC. Nullable. SoftDeleteMixin. |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

**Бизнес-правила:**
- Разовый донат увеличивает `collected_amount` кампании атомарно при `status = success`.
- Для `source = offline` статус сразу `success`, `provider_payment_id = null`.
- Минимальная сумма разового доната: 1000 копеек (10 рублей). Для patron_link — любая сумма, задаётся в ссылке.

### 3.8 OfflinePayment (Платёж вне системы)

Запись о платеже, который поступил в фонд вне ЮKassa: наличными, банковским переводом, или по другим каналам. Юридически — просто учётная запись для прозрачности. Комиссия платформы с офлайн-платежей **не берётся**, так как платформа не участвует в транзакции.

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| campaign_id | UUID v7 | FK → Campaign |
| amount_kopecks | integer | Сумма |
| payment_method | enum | `cash`, `bank_transfer`, `other` |
| description | text | Комментарий (откуда, от кого) |
| recorded_by_admin_id | UUID v7 | FK → Admin, кто зафиксировал |
| payment_date | date | Дата поступления (не created_at!) |
| external_reference | string | Nullable. Unique. Номер платёжного поручения, квитанции или иной внешний идентификатор. |
| created_at | datetime | UTC |

**Бизнес-правило:** при создании `OfflinePayment` атомарно увеличивать `campaign.collected_amount`. Если достигнута `goal_amount` — автоматически `completed`. Лог в `AllocationChange` не требуется.

**Dedup-защита:** поле `external_reference` (unique) позволяет предотвратить повторную запись одного и того же офлайн-платежа. Если админ пытается создать запись с уже существующим `external_reference` — возвращать `409 Conflict`. Поле опционально: если reference не указан, проверка не выполняется.

### 3.9 Subscription (Подписка)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User |
| amount_kopecks | integer | 100, 300, 500 или 1000 (1/3/5/10 руб/день) |
| billing_period | enum | `weekly` (×7), `monthly` (×30) |
| allocation_strategy | enum | `platform_pool`, `foundation_pool`, `specific_campaign` |
| campaign_id | UUID v7 | FK nullable (для `specific_campaign`) |
| foundation_id | UUID v7 | FK nullable (для `foundation_pool`) |
| payment_method_id | string | Токен ЮKassa (`pm-...`). Nullable до привязки. |
| status | enum | `active`, `paused`, `cancelled`, `pending_payment_method` |
| paused_reason | enum | `user_request`, `no_campaigns`, `payment_failed`. Nullable. |
| paused_at | datetime | UTC (nullable) |
| next_billing_at | datetime | UTC. Null если paused/cancelled. |
| is_deleted | boolean | Default: false. SoftDeleteMixin. |
| deleted_at | datetime | UTC. Nullable. SoftDeleteMixin. |
| created_at | datetime | UTC |
| cancelled_at | datetime | UTC. Бизнес-отмена подписки пользователем. Nullable. |

**Ограничения:** макс. 5 активных подписок на пользователя.

> **Уточнение:** `cancelled_at` — дата бизнес-отмены подписки пользователем (SUB-07). `deleted_at` — техническое soft-удаление (например, при анонимизации). Подписка может быть `cancelled` (пользователь отменил), но не `deleted` (запись остаётся для истории).

### 3.10 Transaction (Рекуррентный платёж)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| subscription_id | UUID v7 | FK → Subscription |
| campaign_id | UUID v7 | FK → Campaign. **Nullable** (null при `skipped`). |
| foundation_id | UUID v7 | FK → Foundation. **Nullable** (null при `skipped`). |
| amount_kopecks | integer | Сумма списания |
| platform_fee_kopecks | integer | 15% |
| nco_amount_kopecks | integer | Итого НКО |
| acquiring_fee_kopecks | integer | Комиссия ЮKassa |
| provider_payment_id | string | ID ЮKassa. Nullable. Unique. |
| idempotence_key | string | UUID. Unique. |
| status | enum | `pending`, `success`, `failed`, `skipped`, `refunded` |
| skipped_reason | enum('no_active_campaigns') | Nullable. Причина пропуска транзакции. |
| cancellation_reason | string | Reason из ЮKassa при отказе (nullable) |
| attempt_number | integer | Default: 1 |
| next_retry_at | datetime | Nullable |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

### 3.11 AllocationChange (Лог перераспределений)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| subscription_id | UUID v7 | FK → Subscription |
| from_campaign_id | UUID v7 | Nullable |
| to_campaign_id | UUID v7 | Nullable |
| reason | enum | `campaign_completed`, `campaign_closed_early`, `no_campaigns_in_foundation`, `no_campaigns_on_platform`, `manual_by_admin` |
| notified_at | datetime | Nullable |
| created_at | datetime | UTC |

### 3.12 Achievement (Достижения)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| code | string | Уникальный код: `FIRST_DONATION`, `STREAK_30`, `TOTAL_1000` |
| title | string(255) | Название |
| description | text | Условие получения |
| icon_url | string | URL иконки |
| condition_type | enum | `streak_days`, `total_amount_kopecks`, `donations_count` |
| condition_value | integer | Порог |
| is_active | boolean | Default: true |
| created_at | datetime | UTC |

### 3.13 UserAchievement

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User |
| achievement_id | UUID v7 | FK → Achievement |
| earned_at | datetime | UTC |
| notified_at | datetime | Nullable |

### 3.14 PayoutRecord (Выплата фонду)

Фиксирует факт ручного перевода собранных средств в НКО. Нужен для финансовой прозрачности и сверки.

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| foundation_id | UUID v7 | FK → Foundation |
| amount_kopecks | integer | Сумма перевода |
| period_from | date | Начало периода (за какие сборы) |
| period_to | date | Конец периода |
| transfer_reference | string | Реквизиты перевода / номер платёжки (nullable) |
| note | text | Комментарий (nullable) |
| created_by_admin_id | UUID v7 | FK → Admin |
| created_at | datetime | UTC |

### 3.15 PatronPaymentLink (Ссылки меценатов)

Меценат — донор с особым статусом (`role = patron`), который может формировать крупные платёжные ссылки для закрытия/дозакрытия конкретного сбора. Ссылки генерируются через ЮKassa и могут быть отправлены любому плательщику.

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| campaign_id | UUID v7 | FK → Campaign |
| created_by_user_id | UUID v7 | FK → User (role=patron) |
| amount_kopecks | integer | Сумма в ссылке |
| donation_id | UUID v7 | FK → Donation. Создаётся при генерации ссылки. |
| payment_url | string | URL страницы оплаты ЮKassa |
| expires_at | datetime | UTC. Срок жизни ссылки (24 часа по умолчанию). |
| status | enum | `pending`, `paid`, `expired` |
| created_at | datetime | UTC |

**Юридически:** платёж по ссылке мецената — обычный разовый донат через ЮKassa. Никаких специальных разрешений не требуется. Комиссия платформы 15% применяется как к обычному донату. Меценат не несёт ответственности за то, кто перейдёт по ссылке.

### 3.16 NotificationLog (Лог уведомлений)

Используется когда `NOTIFICATION_PROVIDER=mock`. В продакшне с реальным Firebase — опционально, но полезно для дебага.

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User (nullable для broadcast) |
| push_token | string | Токен получателя (nullable) |
| notification_type | string | Код типа уведомления |
| title | string | Заголовок пуша |
| body | string | Текст пуша |
| data | jsonb | Данные (deep link и т.д.) |
| status | enum | `sent`, `mock`, `failed` |
| provider_response | jsonb | Ответ провайдера (nullable) |
| created_at | datetime | UTC |

---

## 4. Функциональные требования по модулям

### 4.1 Модуль: Аутентификация

| ID | Требование | Роль |
|---|---|---|
| AUTH-01 | Запрос OTP-кода на email. Если пользователь с таким email существует и `is_active = false` — не отправлять OTP, вернуть `403 ACCOUNT_DEACTIVATED` (как при verify-otp). | Гость |
| AUTH-02 | Верификация OTP, выдача JWT access (TTL 15 мин) + refresh (TTL 30 дней). В ответе возвращать флаг `is_new: bool` — `true` если пользователь создан при этой верификации (первый вход), `false` если существующий. Клиент использует флаг для показа onboarding-экрана. Перед выдачей JWT проверять `is_active`. Если `false` → `403 ACCOUNT_DEACTIVATED`. | Гость |
| AUTH-03 | Обновление access-токена по refresh (rotation — refresh инвалидируется после использования) | Donor |
| AUTH-04 | Выход — инвалидация refresh-токена | Donor |
| AUTH-05 | Вход администратора: email + пароль | Admin |
| AUTH-06 | Обновление admin access-токена по refresh (rotation). `POST /admin/auth/refresh`. Логика аналогична AUTH-03, но используется `admin_id` в `RefreshToken`. | Admin |
| AUTH-07 | Выход администратора — инвалидация admin refresh-токена. `POST /admin/auth/logout`. Логика аналогична AUTH-04. | Admin |
| AUTH-08 | OTP хранится hashed, TTL 10 мин, max 5 попыток ввода, после использования `is_used=true` | Система |

### 4.2 Модуль: Кампании (публичная часть)

| ID | Требование | Роль |
|---|---|---|
| CAMP-01 | Лента активных кампаний. Сортировка: `urgency_level DESC`, `(collected/goal) DESC`, `sort_order ASC`. Cursor-пагинация. | Гость, Donor |
| CAMP-02 | Деталь кампании: прогресс, документы, фонд, thanks_content. Поле `close_note` отображается если `closed_early = true`. | Гость, Donor |
| CAMP-03 | Документы кампании | Гость, Donor |
| CAMP-04 | Страница фонда (INN и legal_name не показывать публично) | Гость, Donor |
| CAMP-05 | Deeplink для шеринга кампании | Donor |

### 4.3 Модуль: Разовые донаты (Donor)

| ID | Требование | Роль |
|---|---|---|
| DON-01 | Создание разового доната. **С Bearer-токеном:** `campaign_id`, `amount_kopecks` (≥1000), донат привязывается к пользователю. **Без Bearer-токена:** дополнительно обязательно поле `email`. Система проверяет email в базе: если пользователь найден и активен → `401 AUTH_REQUIRED` (клиент перенаправляет на OTP), если найден и деактивирован → `403 ACCOUNT_DEACTIVATED`, если не найден → авто-регистрация, создание Donation(pending), возврат `payment_url`. После успешной оплаты отправляется OTP на email. | Donor |
| DON-02 | Вебхук `payment.succeeded` для доната: `Donation.status = success`, атомарно увеличить `collected_amount` и `donors_count`. | Система |
| DON-03 | История разовых донатов пользователя | Donor |

### 4.4 Модуль: Подписки (Donor)

| ID | Требование | Роль |
|---|---|---|
| SUB-01 | Создание подписки: сумма (100/300/500/1000), период, стратегия. Статус: `pending_payment_method`. | Donor |
| SUB-02 | Привязка карты: `POST /subscriptions/{id}/bind-card`. Инициирует первый платёж через ЮKassa SDK с `save_payment_method=true` и 3DS. Фактическая сумма списания: `amount_kopecks × 7` (weekly) или `amount_kopecks × 30` (monthly). При успехе: токен → `subscription.payment_method_id`, `status=active`, `next_billing_at = now + period`. Создаётся Transaction(pending). Результат приходит через webhook. | Donor |
| SUB-03 | Список своих подписок (включая paused, без cancelled) | Donor |
| SUB-04 | Изменение: сумма, стратегия, привязка. Изменение суммы — с **следующего** биллинга. | Donor |
| SUB-05 | Пауза (`paused_reason=user_request`, `next_billing_at=null`) | Donor |
| SUB-06 | Возобновление (`status=active`, `next_billing_at = now + period`) | Donor |
| SUB-07 | Отмена в один клик (обязательно по закону). `status=cancelled`, `cancelled_at=now`. | Donor |
| SUB-08 | История транзакций (cursor, фильтры по дате/статусу/campaign) | Donor |
| SUB-09 | Деталь транзакции | Donor |

### 4.5 Модуль: Меценаты — крупные платежи (Patron)

| ID | Требование | Роль |
|---|---|---|
| PAT-01 | Создание платёжной ссылки: меценат указывает `campaign_id` и `amount_kopecks`. Система создаёт `Donation (source=patron_link)` и `PatronPaymentLink`, возвращает `payment_url`. | Patron |
| PAT-02 | Ссылка действительна 24 часа. По истечении — `status=expired`. | Система |
| PAT-03 | Оплата по ссылке — стандартный вебхук `payment.succeeded`. `PatronPaymentLink.status=paid`. | Система |
| PAT-04 | Список своих ссылок (статус, сумма, кампания) | Patron |
| PAT-05 | Admin: назначить пользователя меценатом (`role=patron`) | Admin |
| PAT-06 | Admin: отозвать статус мецената | Admin |

**Юридический комментарий:** платёжные ссылки мецената — это стандартные ЮKassa-ссылки с фиксированной суммой. Никаких лицензий сверх имеющегося соглашения с ЮKassa не нужно. Комиссия 15% применяется как к любому донату.

### 4.6 Модуль: Биллинг (фоновые задачи)

| ID | Требование | Роль |
|---|---|---|
| BILL-01 | Шедулер каждые 15 мин: `SELECT FOR UPDATE SKIP LOCKED` подписок с `next_billing_at <= now AND status=active` | Система |
| BILL-02 | Перед вызовом ЮKassa: создать `Transaction (status=pending)` с уникальным `idempotence_key` | Система |
| BILL-03 | Рекуррентный платёж server-to-server через `payment_method_id`. Таймаут: 30 сек. | Система |
| BILL-04 | Вебхук `payment.succeeded`: верифицировать подпись, Transaction→success, атомарно увеличить `collected_amount`/`donors_count`, обновить `next_billing_at` | Система |
| BILL-05 | Вебхук `payment.canceled`: Transaction→failed, сохранить `cancellation_reason`, запустить retry | Система |
| BILL-06 | Retry: soft decline → 24ч, 3д, 7д, 14д. Hard decline → сразу `pending_payment_method` + уведомление. После 4 soft retry → тоже `pending_payment_method`. | Система |
| BILL-07 | Комиссия 15% фиксируется в `platform_fee_kopecks` при каждом платеже | Система |
| BILL-08 | `SELECT FOR UPDATE SKIP LOCKED` — обязательно для параллельных воркеров | Система |
| BILL-09 | Шедулер ежечасно: подписки с `paused_reason=no_campaigns` → если появились активные кампании → возобновить, уведомить | Система |
| BILL-10 | При статусе кампании → `completed`: async Taskiq task на аллокацию всех привязанных подписок | Система |

### 4.7 Модуль: Распределение средств (Allocation)

| ID | Требование | Роль |
|---|---|---|
| ALLOC-01 | `platform_pool`: кампания с `urgency DESC`, `(collected/goal) DESC`. Фонды `suspended` — исключить. | Система |
| ALLOC-02 | `foundation_pool`: активная кампания фонда → fallback на ALLOC-01. Логировать в `AllocationChange`. | Система |
| ALLOC-03 | `specific_campaign`: привязанная кампания → если не active → ALLOC-02 → ALLOC-01. Логировать. | Система |
| ALLOC-04 | Авто-переключение: создать `AllocationChange`, отправить push. Причина в логе: `campaign_completed` или `campaign_closed_early`. | Система |
| ALLOC-05 | Нет активных кампаний: Transaction→skipped, подписка→paused(`no_campaigns`). Streak не прерывать. | Система |

### 4.8 Модуль: Закрытие кампаний

| ID | Требование | Роль |
|---|---|---|
| CLOSE-01 | Admin: досрочное закрытие кампании (`POST /admin/campaigns/{id}/close-early`). Параметры: `close_note` (текст для пользователей). Система: `status=completed`, `closed_early=true`, `close_note=...`. | Admin |
| CLOSE-02 | При закрытии (обычном или досрочном): автоматически запустить ALLOC-04 для всех подписок этой кампании. | Система |
| CLOSE-03 | Push всем донорам кампании при закрытии. Обычное: «Сбор закрыт — мы достигли цели! X₽ передано фонду.» Досрочное: текст из `close_note`. | Система |
| CLOSE-04 | Admin: офлайн-платёж (`POST /admin/campaigns/{id}/offline-payment`). Фиксирует поступление вне системы, увеличивает `collected_amount`. Комиссия не начисляется. | Admin |
| CLOSE-05 | Автоматическое закрытие по дате: шедулер ежедневно проверяет `ends_at <= now AND status=active AND is_permanent=false` → закрывает с `close_note` по умолчанию. | Система |

**Как другие платформы закрывают неполные сборы:**
- Благо.ру, «Нужна помощь»: закрывали досрочно с уведомлением «Собрали X из Y, передаём что есть».
- GoFundMe: деньги идут организатору независимо от достижения цели.
- Рекомендуемый подход для «По Рублю»: фиксировать `close_note` с честным объяснением, отправлять донорам пуш, в карточке кампании показывать факт досрочного закрытия и причину.

### 4.9 Модуль: Импакт и геймификация

| ID | Требование | Роль |
|---|---|---|
| IMPACT-01 | GET /impact: `total_donated_kopecks` (все success транзакции + success донаты), `streak_days`, `donations_count` | Donor |
| IMPACT-02 | Streak: UTC-день засчитывается при success Transaction **или** success Donation **или** skipped Transaction с `skipped_reason=no_active_campaigns`. | Система |
| IMPACT-03 | GET /impact/achievements: ачивки пользователя | Donor |
| IMPACT-04 | После каждого success Transaction/Donation: проверить и выдать незаработанные ачивки. Push о новой ачивке. | Система |

### 4.10 Модуль: Уведомления

| ID | Требование | Роль |
|---|---|---|
| NOTIF-01 | Push: успешное списание (сумма, кампания, streak) | Система |
| NOTIF-02 | Push: неудача soft decline (обновить карту) / hard decline (отдельный текст) | Система |
| NOTIF-03 | Push: авто-переключение кампании | Система |
| NOTIF-04 | Push: пауза из-за отсутствия кампаний | Система |
| NOTIF-05 | Push: возобновление подписки (BILL-09) | Система |
| NOTIF-06 | Push: кампания закрыта (обычно или досрочно — текст разный) | Система |
| NOTIF-07 | Push: истекает карта через 7 дней (если ЮKassa предоставляет данные) | Система |
| NOTIF-08 | Push: ежедневный streak (только если `push_daily_streak=true`, в timezone пользователя 12:00) | Система |
| NOTIF-09 | PATCH /me/notifications: управление `notification_preferences` | Donor |
| NOTIF-10 | Все уведомления логируются в `NotificationLog`. При `NOTIFICATION_PROVIDER=mock` — только лог, push не отправляется. | Система |

**Push data payloads (структура поля `data` в push-уведомлении):**

| Тип уведомления | `notification_type` | Поле `data` (JSON) |
|---|---|---|
| Успешное списание | `payment_success` | `{"type": "payment_success", "transaction_id": "...", "campaign_id": "...", "amount_kopecks": 100, "streak_days": 15, "deep_link": "porubly://transaction/{id}"}` |
| Неудача (soft decline) | `payment_soft_decline` | `{"type": "payment_soft_decline", "subscription_id": "...", "deep_link": "porubly://subscription/{id}/update-card"}` |
| Неудача (hard decline) | `payment_hard_decline` | `{"type": "payment_hard_decline", "subscription_id": "...", "deep_link": "porubly://subscription/{id}/update-card"}` |
| Авто-переключение | `campaign_switched` | `{"type": "campaign_switched", "subscription_id": "...", "from_campaign_id": "...", "to_campaign_id": "...", "deep_link": "porubly://subscription/{id}"}` |
| Пауза (нет кампаний) | `subscription_paused` | `{"type": "subscription_paused", "subscription_id": "...", "reason": "no_campaigns", "deep_link": "porubly://subscriptions"}` |
| Возобновление | `subscription_resumed` | `{"type": "subscription_resumed", "subscription_id": "...", "deep_link": "porubly://subscription/{id}"}` |
| Кампания закрыта | `campaign_closed` | `{"type": "campaign_closed", "campaign_id": "...", "closed_early": false, "deep_link": "porubly://campaign/{id}"}` |
| Кампания закрыта досрочно | `campaign_closed_early` | `{"type": "campaign_closed_early", "campaign_id": "...", "closed_early": true, "close_note": "...", "deep_link": "porubly://campaign/{id}"}` |
| Истекает карта | `card_expiring` | `{"type": "card_expiring", "subscription_id": "...", "days_left": 7, "deep_link": "porubly://subscription/{id}/update-card"}` |
| Ежедневный streak | `daily_streak` | `{"type": "daily_streak", "streak_days": 15, "deep_link": "porubly://impact"}` |
| Новая ачивка | `achievement_earned` | `{"type": "achievement_earned", "achievement_id": "...", "achievement_code": "STREAK_30", "deep_link": "porubly://impact/achievements"}` |
| Благодарность от фонда | `thanks_content` | `{"type": "thanks_content", "thanks_content_id": "...", "campaign_id": "...", "deep_link": "porubly://thanks/{id}"}` |

### 4.11 Модуль: Выплаты фондам (Admin)

| ID | Требование | Роль |
|---|---|---|
| PAY-01 | Admin: создать `PayoutRecord` — фиксирует факт ручного перевода фонду | Admin |
| PAY-02 | GET /admin/payouts: список выплат с фильтрацией по фонду, периоду | Admin |
| PAY-03 | GET /admin/payouts/balance: для каждого фонда: собрано за период - выплачено = к выплате | Admin |
| PAY-04 | Расчёт «к выплате»: `SUM(nco_amount_kopecks WHERE status=success)` по всем транзакциям и донатам фонда за период минус `SUM(amount_kopecks)` из `PayoutRecord` за тот же период. | Система |

### 4.12 Модуль: Админ-панель

| ID | Требование | Роль |
|---|---|---|
| ADM-01 | CRUD фондов | Admin |
| ADM-02 | CRUD кампаний, управление статусами через action-эндпоинты | Admin |
| ADM-03 | Загрузка медиа в S3 (видео max 500MB, документы max 10MB, форматы: mp4/pdf) | Admin |
| ADM-04 | CRUD thanks_content | Admin |
| ADM-05 | Список пользователей с деталью (подписки, донаты) | Admin |
| ADM-06 | Статистика кампании: collected, donors_count, средний чек | Admin |
| ADM-07 | Общая статистика: GMV, platform_fee за период, активные подписки, retention 30/90 дней | Admin |
| ADM-08 | Управление urgency_level и sort_order | Admin |
| ADM-09 | Логи allocation_changes | Admin |
| ADM-10 | CRUD ачивок | Admin |
| ADM-11 | Принудительный auto-switch (`force-realloc`) | Admin |
| ADM-12 | Назначение/отзыв роли `patron` у пользователя | Admin |
| ADM-13 | Досрочное закрытие кампании с `close_note` (CLOSE-01) | Admin |
| ADM-14 | Запись офлайн-платежа (CLOSE-04) | Admin |
| ADM-15 | Выплаты фондам: создание PayoutRecord, просмотр баланса к выплате (PAY-01 — PAY-04) | Admin |
| ADM-16 | CRUD администраторов: создание, просмотр, обновление, деактивация/активация. Нельзя деактивировать себя. При деактивации — отзыв всех refresh-токенов. | Admin |

### 4.13 Модуль: Благодарности от фондов

| ID | Требование | Роль |
|---|---|---|
| THANKS-01 | При успешном списании (Transaction.status=success или Donation.status=success): проверить наличие ThanksContent для campaign_id. Если есть и пользователь ещё не видел (нет записи в ThanksContentShown) — отправить push с `thanks_content_id` в data-payload (см. api_public §0.6). **HTTP-ответ вебхука ЮKassa** остаётся `{ "status": "ok" }` без тела благодарности. | Система |
| THANKS-02 | GET `/thanks/{id}`: получить контент благодарности (media_url, title, description). При первом запросе — создать запись в ThanksContentShown. Клиент вызывает этот эндпоинт при показе экрана благодарности. Ответ включает блок `user_contribution` — сводку по вкладу пользователя в кампанию (сумма, количество платежей, даты первого и последнего). | Donor |
| THANKS-03 | GET `/thanks/unseen`: список непросмотренных благодарностей пользователя (LEFT JOIN ThanksContentShown WHERE shown_at IS NULL). Используется клиентом при открытии приложения для показа пропущенных благодарностей. | Donor |
| THANKS-04 | Admin: CRUD ThanksContent привязан к кампании (уже покрыто ADM-04). Дополнительно: при создании нового ThanksContent для активной кампании — отправить push всем донорам этой кампании (через CampaignDonors) с типом `thanks_content`. | Admin, Система |
| THANKS-05 | Retention: cron-задача ежемесячно удаляет записи ThanksContentShown старше 12 месяцев. Логировать количество удалённых записей. | Система |

### 4.14 Модуль: Фоновые задачи (Taskiq)

| ID | Задача | Расписание | Логика |
|---|---|---|---|
| TASK-01 | Биллинг-шедулер | Каждые 15 мин | `SELECT FOR UPDATE SKIP LOCKED` подписок с `next_billing_at <= now AND status=active`. Для каждой: определить campaign (ALLOC-01/02/03), создать Transaction(pending), вызвать ЮKassa. BILL-01 — BILL-03. |
| TASK-02 | Retry failed транзакций | Каждые 15 мин | `SELECT FROM transactions WHERE status='failed' AND next_retry_at <= now`. Retry по расписанию: soft decline → 24ч, 3д, 7д, 14д. Hard decline → сразу `pending_payment_method`. BILL-06. |
| TASK-03 | Авто-возобновление подписок | Каждый час | Подписки с `paused_reason=no_campaigns`: проверить наличие активных кампаний → если есть → `status=active`, `next_billing_at = now + period`, push NOTIF-05. BILL-09. |
| TASK-04 | Авто-закрытие кампаний по дате | Ежедневно, 00:05 UTC | `SELECT FROM campaigns WHERE ends_at <= now AND status='active' AND is_permanent=false`. Для каждой: `status=completed`, `close_note` по умолчанию, запустить ALLOC-04, push CLOSE-03. CLOSE-05. |
| TASK-05 | Экспирация patron-ссылок | Каждый час | `UPDATE patron_payment_links SET status='expired' WHERE expires_at <= now AND status='pending'`. PAT-02. |
| TASK-06 | Ежедневный streak push | Каждую минуту | `SELECT FROM users WHERE next_streak_push_at <= now AND is_deleted=false AND notification_preferences->>'push_daily_streak' = 'true'`. Отправить push, обновить `next_streak_push_at = завтра 12:00 в timezone юзера`. NOTIF-08. |
| TASK-07 | Очистка ThanksContentShown | Ежемесячно, 1-е число, 03:00 UTC | `DELETE FROM thanks_content_shown WHERE shown_at < now() - interval '12 months'`. Логировать количество удалённых. THANKS-05. |
| TASK-08 | Очистка expired RefreshToken | Ежедневно, 04:00 UTC | `DELETE FROM refresh_tokens WHERE expires_at < now() - interval '7 days'`. |
| TASK-09 | Очистка expired OTP | Ежечасно | `DELETE FROM otp_codes WHERE expires_at < now() - interval '1 day' AND is_used = true` или `expires_at < now() - interval '1 day'`. |
| TASK-10 | Проверка истекающих карт | Ежедневно, 10:00 UTC | Если ЮKassa предоставляет данные о сроке действия карты: найти подписки с картой, истекающей через 7 дней → push NOTIF-07. |

**Конфигурация Taskiq:**
- Scheduler: строго **один инстанс** (Redis lock или отдельный контейнер).
- Workers: горизонтально масштабируемые.
- Брокер: Redis 7.
- Все задачи идемпотентны (безопасен повторный запуск).

---

## 5. API Endpoints

### Публичные

```
GET    /api/v1/campaigns                            # Лента
GET    /api/v1/campaigns/{id}                       # Деталь
GET    /api/v1/campaigns/{id}/documents             # Документы
GET    /api/v1/foundations/{id}                     # Фонд

POST   /api/v1/auth/send-otp                       # Запрос OTP на email
POST   /api/v1/auth/verify-otp                     # Верификация OTP
POST   /api/v1/auth/refresh                        # Обновление токена
POST   /api/v1/auth/logout                         # Выход (инвалидация refresh)
```

### Donor (JWT)

```
GET    /api/v1/me
PATCH  /api/v1/me
PATCH  /api/v1/me/notifications
DELETE /api/v1/me                                   # Анонимизация (ФЗ-152)

# Подписки
POST   /api/v1/subscriptions
GET    /api/v1/subscriptions
PATCH  /api/v1/subscriptions/{id}
POST   /api/v1/subscriptions/{id}/bind-card
POST   /api/v1/subscriptions/{id}/pause
POST   /api/v1/subscriptions/{id}/resume
DELETE /api/v1/subscriptions/{id}

# Рекуррентные транзакции
GET    /api/v1/transactions
GET    /api/v1/transactions/{id}

# Разовые донаты
POST   /api/v1/donations                            # Создать разовый донат → payment_url
GET    /api/v1/donations                            # История разовых донатов
GET    /api/v1/donations/{id}

# Импакт
GET    /api/v1/impact
GET    /api/v1/impact/achievements

# Благодарности
GET    /api/v1/thanks/{id}                          # Контент благодарности
GET    /api/v1/thanks/unseen                        # Непросмотренные благодарности

GET    /api/v1/campaigns/{id}/share
```

### Patron (JWT, role=patron)

```
POST   /api/v1/patron/payment-links                 # Создать платёжную ссылку
GET    /api/v1/patron/payment-links                 # Мои ссылки
GET    /api/v1/patron/payment-links/{id}
```

### Webhooks

```
POST   /api/v1/webhooks/yookassa
```

### Admin (JWT, role=admin)

```
POST   /api/v1/admin/auth/login
POST   /api/v1/admin/auth/refresh                    # AUTH-06: обновление admin токена
POST   /api/v1/admin/auth/logout                     # AUTH-07: выход администратора

# Фонды
GET/POST        /api/v1/admin/foundations
GET/PATCH       /api/v1/admin/foundations/{id}

# Кампании
GET/POST        /api/v1/admin/campaigns
GET/PATCH       /api/v1/admin/campaigns/{id}
POST            /api/v1/admin/campaigns/{id}/publish
POST            /api/v1/admin/campaigns/{id}/pause
POST            /api/v1/admin/campaigns/{id}/complete
POST            /api/v1/admin/campaigns/{id}/archive
POST            /api/v1/admin/campaigns/{id}/close-early        # + close_note в body
POST            /api/v1/admin/campaigns/{id}/force-realloc
POST            /api/v1/admin/campaigns/{id}/offline-payment    # запись офлайн-платежа
GET             /api/v1/admin/campaigns/{id}/offline-payments   # список офлайн-платежей

# Медиа
POST   /api/v1/admin/media/upload

# Документы / благодарности
POST/DELETE     /api/v1/admin/campaigns/{id}/documents/{doc_id?}
POST/PATCH/DELETE /api/v1/admin/campaigns/{id}/thanks/{t_id?}

# Пользователи
GET    /api/v1/admin/users
GET    /api/v1/admin/users/{id}
POST   /api/v1/admin/users/{id}/grant-patron        # назначить мецената
POST   /api/v1/admin/users/{id}/revoke-patron       # отозвать
POST   /api/v1/admin/users/{id}/deactivate          # деактивация пользователя
POST   /api/v1/admin/users/{id}/activate            # активация пользователя

# Администраторы
GET/POST        /api/v1/admin/admins
GET/PATCH       /api/v1/admin/admins/{id}
POST            /api/v1/admin/admins/{id}/deactivate
POST            /api/v1/admin/admins/{id}/activate

# Статистика
GET    /api/v1/admin/stats/overview
GET    /api/v1/admin/stats/campaigns/{id}

# Выплаты фондам
GET/POST /api/v1/admin/payouts
GET      /api/v1/admin/payouts/balance              # сколько к выплате по каждому фонду

# Ачивки
GET/POST /api/v1/admin/achievements
PATCH    /api/v1/admin/achievements/{id}

# Логи
GET    /api/v1/admin/allocation-logs
GET    /api/v1/admin/notification-logs              # для отладки
```

---

## 6. Бизнес-правила

| # | Правило |
|---|---|
| 1 | **Нет внутреннего баланса.** Платформа не хранит средства пользователей. |
| 2 | **Суммы подписки:** только 100/300/500/1000 копеек. |
| 3 | **Отображение vs списание:** X руб/день, фактическое списание ×7 (weekly) или ×30 (monthly). |
| 4 | **Комиссия платформы:** 15% от каждого ЮKassa-платежа. Для офлайн-платежей — не применяется. |
| 5 | **Приоритет способов оплаты:** СБП (0.4%) > SberPay > Карта (2.4%). |
| 6 | **Макс. 5 активных подписок** на пользователя. |
| 7 | **Soft delete:** подписки, донаты, пользователи не удаляются физически. |
| 8 | **Idempotence key** обязателен для каждого вызова ЮKassa. |
| 9 | **Retry soft decline:** 24ч → 3д → 7д → 14д → `pending_payment_method`. |
| 10 | **Hard decline:** сразу `pending_payment_method` + push. |
| 11 | **Streak:** засчитывается при success Transaction/Donation или skipped-no_campaigns в UTC-день. |
| 12 | **Уведомления обязательны** при каждом списании (ФЗ-161 ст. 9). |
| 13 | **Отмена подписки в один клик** — без дополнительных подтверждений. |
| 14 | **`collected_amount` и `donors_count`** — только атомарное обновление. |
| 15 | **OTP хранится hashed**, TTL 10 мин, max 5 попыток. |
| 16 | **Досрочное закрытие** фиксирует `closed_early=true` и `close_note` — пользователи видят объяснение. |
| 17 | **Меценаты** назначаются только вручную администратором. |
| 18 | **Платёжные ссылки** мецената истекают через 24 часа. |
| 19 | **Офлайн-платежи** не учитываются в расчёте комиссии платформы. |
| 20 | **Агентский договор** с каждым НКО обязателен до подключения фонда к платформе (юридическое основание для удержания комиссии). |
| 21 | **Деактивация аккаунта:** `is_active=false` блокирует авторизацию. Подписки приостанавливаются. Refresh-токены отзываются. |
| 22 | **Guest-донат:** без Bearer-токена обязателен email. Если email найден в базе → требуется авторизация. Если нет → авто-регистрация. |
| 23 | **Фактическая сумма списания подписки:** `amount_kopecks × 7` (weekly) или `amount_kopecks × 30` (monthly). |
| 24 | **Благодарности:** показываются только после успешного платежа. Ответ включает вклад пользователя в кампанию. |

---

## 7. Нефункциональные требования

| Требование | Описание |
|---|---|
| **Масштабируемость** | Горизонтальное масштабирование API и Taskiq workers. Taskiq scheduler — строго один инстанс планировщика задач. |
| **Безопасность** | HTTPS only. JWT access 15 мин, refresh 30 дней с rotation. Верификация подписей вебхуков ЮKassa. Rate limiting. |
| **Хранение данных** | PostgreSQL 16. Суммы — integer (копейки). Даты — UTC. UUID v7 (библиотека `uuid_utils`). Монотонные, эффективнее для B-tree индексов PostgreSQL. |
| **Медиа** | S3-совместимое хранилище в РФ (Selectel / Timeweb Cloud / MinIO). Переключение через `S3_ENDPOINT_URL`. |
| **Уведомления** | Абстракция `NotificationProvider`. Переключение `NOTIFICATION_PROVIDER=mock|firebase`. |
| **Персональные данные** | Серверы в РФ (ФЗ-152). `DELETE /me` — анонимизация PD, транзакции сохраняются. Анонимизация через 3 года. |
| **Мониторинг** | Логирование всех платёжных операций. Алерты: failed > 10%, Taskiq lag > 5 мин. |
| **Деплой** | Docker Compose: `api`, `worker`, `scheduler`, `postgres`, `redis`. CI/CD — GitHub Actions. |
| **API versioning** | Префикс `/api/v1/`. |
| **Документация** | OpenAPI автогенерация FastAPI. |

### Рекомендуемые индексы БД

```sql
CREATE INDEX idx_subscriptions_billing
  ON subscriptions (next_billing_at, status) WHERE status = 'active';

CREATE UNIQUE INDEX idx_users_email ON users (email);

CREATE INDEX idx_transactions_subscription
  ON transactions (subscription_id, created_at DESC);

CREATE INDEX idx_transactions_retry
  ON transactions (next_retry_at, status)
  WHERE status = 'failed' AND next_retry_at IS NOT NULL;

CREATE INDEX idx_campaigns_feed
  ON campaigns (urgency_level DESC, sort_order ASC, status) WHERE status = 'active';

CREATE INDEX idx_donations_user
  ON donations (user_id, created_at DESC);

CREATE INDEX idx_patron_links_campaign
  ON patron_payment_links (campaign_id, status);
```

---

## 8. Фазы реализации

### Фаза 1 — MVP

**Цель:** первые доноры могут поддержать кампанию подпиской и разовым донатом.

- [ ] Аутентификация (email + OTP)
- [ ] Кампании (лента, деталь, документы, фонд)
- [ ] Разовый донат через ЮKassa (DON-01 — DON-03)
- [ ] Стратегия `platform_pool`
- [ ] Создание подписки + токенизация (SUB-01, SUB-02)
- [ ] Webhook-обработка для транзакций и донатов
- [ ] Базовый биллинг (ежемесячное списание)
- [ ] Благодарность (thanks_content)
- [ ] Базовая админка: CRUD фондов, кампаний, медиа, офлайн-платежи
- [ ] Уведомления через MockProvider (лог в БД)
- [ ] Deeplink для шеринга
- [ ] Досрочное закрытие кампании (CLOSE-01 — CLOSE-03)
- [ ] Логи allocation_changes (AllocationChange)

### Фаза 2 — Подписки и удержание

- [ ] Все три стратегии аллокации
- [ ] Полный биллинг-шедулер (BILL-01 — BILL-10)
- [ ] Retry-логика по типу отказа
- [ ] Импакт-счётчик + streak (IMPACT-01 — IMPACT-04)
- [ ] Ачивки (ADM-10)
- [ ] Настройки уведомлений (NOTIF-09)
- [ ] Пауза / возобновление подписки
- [ ] BILL-09: авто-возобновление при появлении кампании
- [ ] Выплаты фондам в админке (PAY-01 — PAY-04)

### Фаза 3 — Меценаты и масштаб

- [ ] Роль Patron + платёжные ссылки (PAT-01 — PAT-06)
- [ ] Подключение реального push-провайдера (FCM/APNs)
- [ ] Расширенная статистика для админки
- [ ] Социальные механики («Волна», фандрайзинг)
- [ ] Кабинет менеджера фонда (Foundation Manager)
