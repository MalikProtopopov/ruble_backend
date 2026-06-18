# Техническое задание — платформа «По Рублю» (backend)

> **Статус документа.** Реверс-инжиниринг по фактически реализованному коду
> репозитория `fondback/backend` (FastAPI). Все эндпоинты, поля, коды ошибок,
> константы и бизнес-правила взяты из реального кода, а не спроектированы заново.
> Формат функциональных требований: **User Story → API-запрос → Бизнес-логика**.
>
> **Денежные суммы везде в копейках** (`amount_kopecks`, целое число). 100 коп. = 1 ₽.

---

## Содержание

**Общая часть (для обеих частей):**
1. [Обзор продукта](#1-обзор-продукта)
2. [Архитектура и сквозные конвенции](#2-архитектура-и-сквозные-конвенции)
3. [Модель данных](#3-модель-данных)

**ЧАСТЬ A — Бэкенд для клиентского приложения (мобильное API):**
4. [Функциональные требования: публичное API](#4-функциональные-требования-публичное-api) (аутентификация, профиль, сборы, донаты, способы оплаты, подписки, транзакции, impact, благодарности, патрон, пуши)
5. [Платёжный поток end-to-end (ЮKassa)](#5-платёжный-поток-end-to-end-юkassa)

**ЧАСТЬ B — Бэкенд для админ-панели:**
6. [Админ-API](#6-админ-api) (auth, фонды, сборы+контент, возвраты, медиа, пользователи, статистика, выплаты, достижения, логи, админы, документы, обслуживание карт)

**ЧАСТЬ C — Сквозные процессы и справочник:**
7. [Фоновые задачи (cron)](#7-фоновые-задачи-cron)
8. [Справочник: перечисления, константы, коды ошибок](#8-справочник)
9. [Нефункциональные требования и открытые вопросы](#9-нефункциональные-требования-и-открытые-вопросы)

---

## 1. Обзор продукта

«По Рублю» — мобильная платформа благотворительных пожертвований. Пользователь
жертвует деньги в **сборы** (кампании), которые ведут проверенные **фонды**.
Поддерживаются два сценария пожертвований:

- **Разовое пожертвование** в конкретный сбор;
- **Подписка** — регулярные микро-списания (от 1 ₽/день), которые автоматически
  распределяются по сборам согласно выбранной стратегии (конкретный сбор / пул фонда /
  пул платформы).

Дополнительно: достижения и «стрики» (серии дней с донатами), благодарности от фондов
(видео/аудио), патрон-ссылки (генерация ссылок на оплату), админка для фондов/сборов/
выплат/контента.

**Ключевые роли:**
- `donor` — обычный жертвователь (в т.ч. анонимный, по `device_id`);
- `patron` — может генерировать платёжные ссылки;
- `admin` — оператор платформы (отдельная админ-авторизация).

---

## 2. Архитектура и сквозные конвенции

### 2.1 Технологический стек

| Слой | Технология |
|------|-----------|
| API | FastAPI (async), Pydantic v2 |
| ORM / БД | SQLAlchemy 2.0 (async, asyncpg), PostgreSQL |
| Кэш / лимиты | Redis (rate-limit OTP, троттлинг `last_seen`) |
| Фоновые задачи | Taskiq + Redis (broker + cron-планировщик) |
| Платежи | ЮKassa (HTTP API v3, разовые + рекуррентные) |
| Пуши | Firebase Admin (FCM/APNS) |
| Медиа | S3 / MinIO (видео, аудио, фото, документы), ffmpeg для превью |
| Авторизация | JWT RS256 (`iss=porubly`, `aud=porubly-api`) |
| Почта | OTP-письма (mock / SendGrid / SMTP) |

### 2.2 Слои и поток запроса

```
HTTP → Middleware(LastSeen) → Router(app/api/v1/...) → Depends(сессия БД, auth, пагинация)
     → Service(app/services/*.py — вся бизнес-логика) → Repository → ORM(app/models) → PostgreSQL
Фон: Taskiq tasks (app/tasks/*.py) — по cron или из вебхуков/сервисов.
```

- **Роутер** тонкий: разбор запроса, auth-зависимость, логирование, вызов сервиса.
- **Сервис** — вся логика и бизнес-правила; бросает доменные исключения.
- **Транзакция БД**: сессия на запрос. Внутри сервиса `session.flush()` (получить id без
  коммита), финальный `commit()` — на выходе из зависимости `get_db_session`; при любом
  исключении — `rollback()`.

### 2.3 Базовый префикс и группировка

- Все API под `/api/v1`. Публичные роутеры — `app/api/v1/public/*`, админ — `app/api/v1/admin/*`,
  служебные — `auth`, `webhooks`, `media_proxy` (`/media/...`), `payment_result` (`/payment-result`).
- **CORS**: разрешены все origin/методы/заголовки (на момент текущей реализации).
- **Lifespan**: на старте проверяются соединения с PostgreSQL (`SELECT 1`) и Redis (`PING`).

### 2.4 Аутентификация и роли

- Токен: `Authorization: Bearer <access_token>` (JWT RS256, TTL **15 минут**).
- Refresh-токен: TTL **30 дней** (зарегистрированный), **180 дней** (анонимный).
  Хранится в БД как **SHA-256-хэш**; поддерживает `is_revoked` (logout) и `is_used`
  (ротация + детект replay-атаки → отзыв всех токенов субъекта).
- **Анонимная регистрация по устройству** (`device_id`) — идемпотентна.
- **Привязка email через OTP** (argon2-хэш, TTL 10 мин, ≤5 попыток, rate-limit 5/60 с в Redis),
  опционально **с merge** анонимного аккаунта.
- Зависимости (`app/core/security.py`): `require_donor` (любой авторизованный),
  `require_patron` (только роль patron, иначе 403), `require_admin` (только admin),
  `bearer_scheme` (опциональный токен — для гостевых ручек с per-user полями).
- **Проверка владения** — в сервисе через условие запроса (`WHERE user_id == current AND is_deleted == false`).

#### 2.4а Dev-режим (только при `DEBUG=true`)

Для локальной разработки/стейджа без реальных интеграций (гейтится по `settings.DEBUG`, в проде не действует):
- **OTP-обход:** код `111111` принимается как валидный для любого email в `verify-otp` и `link-email/verify-otp`
  (`app/services/auth.py:_verify_otp`). Обычная argon2-проверка остаётся для всех прочих кодов.
- **Mock-провайдеры:** `EMAIL_PROVIDER=mock` (письма не уходят, но **реальный OTP-код пишется в лог**:
  `email_mock code=…`), `NOTIFICATION_PROVIDER=mock` (пуши логируются как `mock`),
  пустые `YOOKASSA_*` → платежи в mock-режиме (фейковый `payment_url`, вебхуки не приходят).
- **Вебхук ЮKassa:** проверка IP-allowlist отключена при `DEBUG`.

### 2.5 Единый формат ошибок

Все доменные ошибки — наследники `AppError`; тело ответа всегда одинаковое:

```json
{ "error": { "code": "DONATION_COOLDOWN", "message": "Текст для пользователя", "details": { } } }
```

| Класс | HTTP | Назначение |
|-------|------|-----------|
| `NotFoundError` | 404 | сущность не найдена / чужая |
| `ConflictError` | 409 | конфликт (email привязан, version-конфликт документа) |
| `ForbiddenError` | 403 | нет прав / аккаунт деактивирован |
| `BusinessLogicError(code, message)` | 422 | нарушено бизнес-правило |
| `AppError(code, message, status_code)` | любой | напр. 401 `AUTH_REQUIRED`, 429 `DONATION_COOLDOWN` |
| `HTTPException` | 401/403 | нет/невалиден токен, не та роль |

`details` — машиночитаемый контекст для клиента (`retry_after`, `next_available_at`,
`server_time_utc` и т.п.). Сообщения для пользователя — на русском.

### 2.6 Пагинация (курсорная)

- Query-параметры: `limit` (1–100, дефолт 20), `cursor` (base64-JSON).
- Тело ответа списков: `{ "data": [...], "pagination": { "next_cursor": ..., "has_more": bool, "total": null } }`.

### 2.7 Деньги, комиссии, идемпотентность

- Все суммы — целое число копеек.
- **Комиссия платформы**: `PLATFORM_FEE_PERCENT = 15` → `platform_fee = amount * 15 // 100`,
  `nco_amount = amount - platform_fee - acquiring_fee` (acquiring_fee пока 0).
- **Минимальный разовый донат**: `MIN_DONATION_AMOUNT_KOPECKS = 1000` (10 ₽). На уровне БД
  жёсткий минимум `amount_kopecks >= 100`.
- **Идемпотентность платежей**: при создании доната/транзакции генерируется `idempotence_key`
  (uuid7), уходит в ЮKassa и хранится с `unique`-индексом → защита от дублей и на стороне БД, и провайдера.

### 2.8 Активность пользователя

`LastSeenMiddleware` обновляет `users.last_seen_at` для авторизованных запросов, троттлинг —
1 запись на пользователя раз в 15 минут (Redis `SET NX EX`). Используется для зачистки
неактивных анонимных аккаунтов (180 дней).

### 2.9 Конфигурация и окружение (`app/core/config.py`)

Настройки задаются через `.env` / переменные окружения (pydantic-settings). Группы:

| Группа | Ключевые переменные |
|--------|---------------------|
| Приложение | `DEBUG`, `SECRET_KEY`, `ENCRYPTION_KEY` |
| База данных | `DATABASE_URL` (async PostgreSQL) |
| Redis | `REDIS_URL` |
| JWT | `JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`, `JWT_AUDIENCE`, `JWT_ADMIN_AUDIENCE`, `JWT_ISSUER`, TTL access/refresh/anon |
| Платежи | `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` (пусто → mock-режим без реального API) |
| Хранилище | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_PUBLIC_URL` |
| Уведомления | `NOTIFICATION_PROVIDER` (`mock`/`firebase`), `FIREBASE_CREDENTIALS_PATH` |
| Почта | `EMAIL_PROVIDER` (`mock`/`sendgrid`/`smtp`), `SENDGRID_API_KEY`, SMTP-настройки |
| Домены/URL | `PUBLIC_API_URL` (для `return_url` ЮKassa), `FRONTEND_URL`, `API_DOMAIN`, `CORS_ALLOWED_ORIGINS` |
| Бизнес-параметры | `DONATION_COOLDOWN_HOURS`, `ANONYMOUS_INACTIVE_DAYS`, `LAST_SEEN_THROTTLE_MINUTES` |

> В тест/незаданном окружении ЮKassa и провайдеры уведомлений/почты работают в mock-режиме
> (без внешних вызовов) — это используется автотестами.

---

## 3. Модель данных

### 3.1 Основные таблицы

| Сущность | Таблица | Ключевые поля | Soft-delete |
|----------|---------|---------------|:-----------:|
| Пользователь | `users` | `email`(uniq), `device_id`(uniq), `is_anonymous`, `is_email_verified`, `role`, `push_token`, `push_platform`, `timezone`, `notification_preferences`(jsonb), `current_streak_days`, `last_streak_date`, `total_donated_kopecks`, `total_donations_count`, `next_streak_push_at`, `last_seen_at`, `is_active` | ✔ |
| OTP-код | `otp_codes` | `email`, `code_hash`(argon2), `expires_at`, `is_used`, `attempts` | — |
| Refresh-токен | `refresh_tokens` | `user_id` XOR `admin_id`, `token_hash`(sha256, uniq), `expires_at`, `is_used`, `is_revoked` | — |
| Фонд | `foundations` | `name`, `legal_name`, `inn`(uniq), `description`, `logo_url`, `website_url`, `status`, `yookassa_shop_id`, `verified_at` | — |
| Сбор | `campaigns` | `foundation_id`, `title`, `description`, `video_url`, `thumbnail_url`, `status`, `goal_amount`, `collected_amount`, `donors_count`, `urgency_level`(1–5), `is_permanent`, `ends_at`, `closed_early`, `close_note`, `sort_order` | — |
| Документ сбора | `campaign_documents` | `campaign_id`, `title`, `file_url`, `sort_order` | — |
| Благодарность | `thanks_contents` | `campaign_id`, `type`(video/audio), `media_url`, `title`, `description` | — |
| Показ благодарности | `thanks_content_shown` | `user_id`, `thanks_content_id` (uniq вместе) | — |
| Донор сбора | `campaign_donors` | `campaign_id`, `user_id` (uniq вместе) — для дедупликации `donors_count` | — |
| Пожертвование | `donations` | `user_id`, `campaign_id`, `foundation_id`, `amount_kopecks`, `platform_fee_kopecks`, `nco_amount_kopecks`, `acquiring_fee_kopecks`, `provider_payment_id`(uniq), `idempotence_key`(uniq), `payment_url`, `status`, `source` | ✔ |
| Подписка | `subscriptions` | `user_id`, `amount_kopecks`(∈100/300/500/1000), `billing_period`, `allocation_strategy`, `campaign_id`, `foundation_id`, `payment_method_id`(ЮKassa), `status`, `paused_reason`, `paused_at`, `next_billing_at`, `cancelled_at` | ✔ |
| Транзакция | `transactions` | `subscription_id`, `campaign_id`, `foundation_id`, суммы+комиссии, `provider_payment_id`(uniq), `idempotence_key`(uniq), `status`, `skipped_reason`, `cancellation_reason`, `attempt_number`, `next_retry_at` | — |
| Способ оплаты | `payment_methods` | `user_id`, `provider`, `provider_pm_id`, `card_last4`, `card_type`, `title`, `is_default`, `card_fingerprint`(sha256) | ✔ |
| Изменение аллокации | `allocation_changes` | `subscription_id`, `from_campaign_id`, `to_campaign_id`, `reason`, `notified_at` | — |
| Патрон-ссылка | `patron_payment_links` | `campaign_id`, `created_by_user_id`, `amount_kopecks`, `donation_id`, `payment_url`, `expires_at`, `status` | — |
| Достижение | `achievements` | `code`(uniq), `title`, `description`, `icon_url`, `condition_type`, `condition_value`, `is_active` | — |
| Достижение юзера | `user_achievements` | `user_id`, `achievement_id` (uniq вместе), `earned_at`, `notified_at` | — |
| Лог уведомления | `notification_logs` | `user_id`, `push_token`, `notification_type`, `title`, `body`, `data`(jsonb), `status`, `provider_response`(jsonb) | — |
| Медиа-ассет | `media_assets` | `s3_key`(uniq), `public_url`, `type`, `original_filename`, `size_bytes`, `content_type`, `uploaded_by_admin_id` | — |
| Публичный документ | `documents` | `slug`(uniq), `title`, `excerpt`, `content`, `status`, `document_version`, `document_date`, `published_at`, `file_url`, `version`(optimistic lock) | ✔ |
| Офлайн-платёж | `offline_payments` | `campaign_id`, `amount_kopecks`, `payment_method`, `description`, `external_reference`, `payment_date` | — |
| Админ | `admins` | `email`(uniq), `password_hash`(argon2), `name`, `is_active` | — |
| Выплата фонду | `payout_records` | `foundation_id`, `amount_kopecks`, `period_from`, `period_to`, `transfer_reference`, `created_by_admin_id` | — |

### 3.2 Перечисления (enums)

- **UserRole**: `donor` · `patron` (+ `admin` для админов)
- **CampaignStatus**: `draft` · `active` · `paused` · `completed` · `archived`
- **FoundationStatus**: `pending_verification` · `active` · `suspended`
- **DonationStatus**: `pending` · `success` · `failed` · `refunded`
- **DonationSource**: `app` · `patron_link` · `offline`
- **SubscriptionStatus**: `active` · `paused` · `cancelled` · `pending_payment_method`
- **PausedReason**: `user_request` · `no_campaigns` · `payment_failed`
- **BillingPeriod**: `weekly` (×7) · `monthly` (×30)
- **AllocationStrategy**: `platform_pool` · `foundation_pool` · `specific_campaign`
- **AllocationChangeReason**: `campaign_completed` · `campaign_closed_early` · `no_campaigns_in_foundation` · `no_campaigns_on_platform` · `manual_by_admin`
- **TransactionStatus**: `pending` · `success` · `failed` · `skipped` · `refunded`
- **SkipReason**: `no_active_campaigns`
- **PatronLinkStatus**: `pending` · `paid` · `expired`
- **AchievementConditionType**: `streak_days` · `total_amount_kopecks` · `donations_count`
- **MediaAssetType**: `video` · `document` · `audio` · `image`
- **NotificationStatus**: `sent` · `mock` · `failed`
- **PushPlatform**: `fcm` · `apns`
- **DocumentStatus**: `draft` · `published` · `archived`

---

# ЧАСТЬ A. Бэкенд для клиентского приложения (мобильное API)

> Всё, что нужно мобильному фронту (iOS/Android): аутентификация по устройству/OTP, лента
> сборов, донаты, подписки, способы оплаты, импакт, благодарности, патрон-ссылки, пуши.
> Базовый префикс `/api/v1`. Сквозные конвенции (auth, формат ошибок, пагинация, деньги) — §2.
> Разделы §4 (эндпоинты) и §5 (платёжный поток) относятся к этой части.

## 4. Функциональные требования: публичное API

> Ядро пользовательских сценариев (аутентификация, сборы, донаты, подписки, платежи)
> описано в полном формате **User Story → API → Бизнес-логика**. Вспомогательные ручки —
> компактно. Все пути даны с полным префиксом.

---

### 4.1 Аутентификация и аккаунт

#### 4.1.1 Анонимная регистрация по устройству

**User Story.**
**TL;DR для заказчика:** при первом запуске приложение само регистрирует пользователя по
идентификатору устройства — без email и паролей. Человек может сразу жертвовать, а email
привязать позже.
**Как** новый пользователь, **я хочу** начать пользоваться приложением без регистрации,
**чтобы** не отвлекаться на формы и сразу помочь.
**Критерии приёмки:**
- Дано новый `device_id`, когда вызывается ручка, тогда создаётся анонимный пользователь и
  возвращается пара токенов; `is_new=true`.
- Дано тот же `device_id` повторно, когда вызывается ручка, тогда возвращается тот же
  пользователь с новыми токенами; `is_new=false` (идемпотентность).
- Дано деактивированный аккаунт устройства, тогда `403 FORBIDDEN`.

**API.** `POST /api/v1/auth/device-register` · auth: нет.

| Поле (`DeviceRegisterRequest`) | Тип | Обяз. | Ограничения |
|---|---|---|---|
| `device_id` | str | да | 8–64 символа |
| `push_token` | str? | нет | — |
| `push_platform` | str? | нет | `fcm` \| `apns` |
| `timezone` | str? | нет | IANA-зона |

Ответ `200` (`UserTokenResponse`): `access_token`, `refresh_token`, `token_type="bearer"`,
`user`{`id`, `email`, `name`, `role`, `is_new`, `is_anonymous=true`, `is_email_verified=false`}.

**Бизнес-логика.**
1. Найти пользователя по `device_id` (не удалённого).
2. Нет → создать `User(is_anonymous=true, is_email_verified=false, last_seen_at=now)`, проставить
   `timezone`/`push_token`/`push_platform` если переданы; `is_new=true`.
3. Есть → проверить `is_active` (иначе `ForbiddenError`); обновить push/timezone если изменились,
   `last_seen_at=now`; `is_new=false`.
4. Выпустить токены: access 15 мин, **refresh 180 дней** (анонимный TTL); сохранить хэш refresh.

#### 4.1.2 Отправка OTP на email

**User Story.** Как пользователь, я хочу получить код подтверждения на email, чтобы привязать
почту к аккаунту.

**API.** `POST /api/v1/auth/send-otp` · auth: нет. Тело: `{ email }`. Ответ `200`:
`{ message, expires_in_seconds: 600 }`.
**Ошибки:** `422 OTP_RATE_LIMIT` (>5 запросов на email за 60 с).

**Бизнес-логика.**
1. Redis rate-limit: `INCR otp_rate:{email}` (EXPIRE 60 с при первом), >5 → `OTP_RATE_LIMIT`.
2. Сгенерировать 6-значный код, захэшировать **argon2**, создать `OTPCode(expires_at=now+10мин)`.
3. Отправить письмо (mock/SendGrid/SMTP); ошибка отправки логируется, но не блокирует ответ.

#### 4.1.3 Подтверждение OTP (вход / регистрация по email)

**User Story.** Как пользователь, я хочу ввести код из письма, чтобы войти под своим email.

**API.** `POST /api/v1/auth/verify-otp` · auth: нет. Тело: `{ email, code }`. Ответ `200`
(`UserTokenResponse`): токены + `user`(`is_anonymous=false`, `is_email_verified=true`).
**Ошибки:** `422 OTP_EXPIRED`, `422 OTP_INVALID`, `422 OTP_MAX_ATTEMPTS`, `403 FORBIDDEN` (аккаунт деактивирован).

**Бизнес-логика.**
1. Взять активные (не использованные, не истёкшие) OTP по email (DESC). Нет → `OTP_EXPIRED`.
2. Проверить код argon2-верификацией; при промахе инкремент `attempts`, при ≥5 → `OTP_MAX_ATTEMPTS`, иначе `OTP_INVALID`.
3. Пометить все активные OTP `is_used=true`.
4. Найти/создать `User` по email (новый: `is_email_verified=true`, `is_anonymous=false`, `role=donor`).
   Деактивированный → `ForbiddenError`.
5. Выпустить токены (refresh 30 дней). `is_new=true` если создан.

#### 4.1.4 Привязка email к анонимному аккаунту (+ опциональный merge)

**User Story.**
**TL;DR для заказчика:** анонимный пользователь подтверждает email; если на этот email уже есть
аккаунт — с его согласия два аккаунта объединяются (история донатов и подписки сохраняются).
**Как** анонимный пользователь, **я хочу** привязать email, **чтобы** не потерять прогресс при
смене устройства.
**Критерии приёмки:**
- Дано email свободен, когда подтверждён OTP, тогда email привязывается к текущему аккаунту, `merged=false`.
- Дано email занят другим аккаунтом и `allow_merge=false`, тогда `422 EMAIL_ALREADY_LINKED` с превью объёма данных.
- Дано `allow_merge=true` и текущий аккаунт анонимный, тогда данные переносятся в целевой, `merged=true`.

**API.** `POST /api/v1/auth/link-email/verify-otp` · auth: `require_donor`.
Тело: `{ email, code, allow_merge=false }`. Ответ `200` (`LinkEmailTokenResponse`): токены, `user`, `merged`.
**Ошибки:** `OTP_*` как выше; `401 USER_NOT_FOUND`; `422 EMAIL_ALREADY_LINKED`
(details: `target_user_id`, `source_donations_count`, `source_subscriptions_count`,
`source_total_donated_kopecks`); `403 FORBIDDEN` (целевой деактивирован);
`422 MERGE_NOT_ALLOWED` (текущий аккаунт не анонимный).

**Бизнес-логика.**
1. Проверить OTP (как 4.1.3), пометить использованными.
2. Загрузить текущего пользователя из JWT; нет → `USER_NOT_FOUND`.
3. Найти целевого по email.
4. Целевой существует и ≠ текущий:
   - `allow_merge=false` → `EMAIL_ALREADY_LINKED` (с превью объёма данных текущего аккаунта);
   - `allow_merge=true`: проверить `target.is_active`, `current.is_anonymous` → `merge_anonymous_into(source=current, target=target)`,
     отозвать refresh текущего, выпустить токены целевого (30 дней), `merged=true`.
5. Иначе (email свободен/совпадает) → привязать email к текущему (`is_email_verified=true`,
   `is_anonymous=false`), выпустить токены (теперь 30 дней), `merged=false`.

**Merge (`merge_anonymous_into`)** — в одной транзакции: перенос `donations`, `subscriptions`,
`notification_logs`, `payment_methods` (с дедупликацией `is_default`) на целевого; среди активных
подписок целевого оставить **старейшую**, остальные `cancelled`; отзыв всех refresh источника;
агрегаты целевого (`total_donated_kopecks +=`, `total_donations_count +=`, `current_streak_days = max`);
soft-delete источника (`is_deleted=true`, `is_active=false`, `device_id=null`).

#### 4.1.5 Обновление токена / выход

- **`POST /api/v1/auth/refresh`** · auth: нет. Тело `{ refresh_token }` → новая пара (ротация).
  Логика: sha256-хэш → найти токен; проверки → ошибки `401 INVALID_REFRESH_TOKEN` (не найден/отозван/
  истёк/субъект деактивирован) и `401 REPLAY_ATTACK_DETECTED` (повторное использование → **отзыв всех**
  токенов субъекта). Помечает старый `is_used=true`, выпускает новый с TTL по типу субъекта.
- **`POST /api/v1/auth/logout`** · auth: `require_donor`. Тело `{ refresh_token }` → `204`. Помечает
  токен `is_revoked=true`; если не найден — тихо `204`.

---

### 4.2 Профиль

| Метод / путь | Auth | Назначение |
|---|---|---|
| `GET /api/v1/me` | require_donor | Профиль (`UserProfileResponse`: контакты, роль, timezone, флаги, `notification_preferences`, `current_streak_days`, `total_donated_kopecks`, `total_donations_count`, `donation_cooldown_hours`, `created_at`). 404 если нет. |
| `PATCH /api/v1/me` | require_donor | Обновление `name`, `phone`, `avatar_url`, `timezone`, `push_token`, `push_platform` (только переданные поля). |
| `PATCH /api/v1/me/notifications` | require_donor | Частичное обновление настроек пушей (`push_on_payment`, `push_on_campaign_change`, `push_daily_streak`, `push_campaign_completed`, `push_on_donation_reminder`). |
| `DELETE /api/v1/me` | require_donor | Удаление аккаунта с анонимизацией (ФЗ-152) → `204`. |

**Бизнес-логика удаления аккаунта.** Анонимизировать PII (`email=deleted_{id}@anonymized.local`,
`phone/name/avatar/push_token=null`), `is_deleted=true`, `is_active=false`, `deleted_at=now`;
отменить все активные/приостановленные/ожидающие подписки (`cancelled`); отозвать все refresh-токены.

---

### 4.3 Фонды и публичные документы

| Метод / путь | Auth | Назначение |
|---|---|---|
| `GET /api/v1/foundations` | нет | query `search` (ILIKE по имени). Список активных фондов (`status=active`), сорт по имени. Ответ `200` `list[FoundationPublicResponse]`. |
| `GET /api/v1/foundations/{foundation_id}` | нет | path `foundation_id` UUID. Ответ `FoundationPublicResponse`. 404 `NOT_FOUND` («Фонд не найден»). |
| `GET /api/v1/documents` | нет | query `search`, `limit`, `cursor`. Пагинированный список `DocumentPublicListItem`. |
| `GET /api/v1/documents/{slug}` | нет | path `slug` str. Ответ `DocumentPublicDetail`. 404 «Документ не найден». |

- **`FoundationPublicResponse`:** `id`, `name`, `description?`, `logo_url?`, `website_url?`, `status`.
- **`DocumentPublicListItem`:** `slug`, `title`, `excerpt?`, `document_version?`, `document_date?`, `published_at?`, `file_url?`.
- **`DocumentPublicDetail`** = list-item + `content?`.

Возвращаются только сущности в публичном статусе (`foundations.status=active`, `documents.status=published`).

---

### 4.4 Сборы (кампании)

#### 4.4.1 Лента сборов

**User Story.**
**TL;DR для заказчика:** главная лента сборов. Если пользователь авторизован, по каждому сбору
сразу видно, донатил ли он сегодня и когда можно помочь снова (сервер считает кулдаун сам, чтобы
не зависеть от часов на телефоне).
**Как** пользователь, **я хочу** видеть ленту актуальных сборов, **чтобы** выбрать, кому помочь.
**Критерии приёмки:**
- Дано гость, когда запрашивает ленту, тогда возвращаются активные сборы без per-user полей (они `null`).
- Дано авторизованный, тогда по каждому сбору заполнены `can_donate_now`, `next_available_at`,
  `next_available_in_seconds`, `server_time_utc`, `donated_today`, `has_any_donation`, `last_donation`.

**API.** `GET /api/v1/campaigns` · auth: опциональный (`bearer_scheme`).
Query: `status` (`active`|`completed`, дефолт `active`), `sort` (`default`|`helped_today`|`helped_ever`,
учитывается только для авторизованных), `limit`, `cursor`. Ответ `200`: пагинированный список `CampaignListItem`.

`CampaignListItem`: `id`, `foundation_id`, `foundation`{`id`,`name`,`logo_url`}, `title`, `description`,
`thumbnail_url`, `status`, `goal_amount`, `collected_amount`, `donors_count`, `urgency_level`(1–5),
`is_permanent`, `ends_at`, `created_at` + per-user поля (`null` для гостей):
`donated_today`, `has_any_donation`, `last_donation`{`id`,`amount_kopecks`,`created_at`,`status`},
`next_available_at`, `can_donate_now`, `next_available_in_seconds`, `server_time_utc`.

**Бизнес-логика.**
1. Нормализовать `status`/`sort` к допустимым.
2. Гость: `Campaign.status=filter AND Foundation.status=active`; сортировка для `active` — по
   `urgency_level DESC`, доле `collected/goal DESC`, `sort_order ASC`; для `completed` — `updated_at DESC`;
   курсор по `created_at`. Per-user поля `null`.
3. Авторизованный: LATERAL-подзапрос на последний успешный донат по каждому сбору → вычислить
   `donated_today` (по таймзоне пользователя), `has_any_donation`, `next_available_at =
   last_donation.created_at + DONATION_COOLDOWN_HOURS`; затем `can_donate_now`,
   `next_available_in_seconds`, `server_time_utc` (серверное «сейчас»).

> **Кулдаун (8 ч)** считается на сервере и отдаётся клиенту в абсолютном времени и в секундах,
> чтобы мобильный таймер не зависел от часов устройства.

#### 4.4.2 Прочие ручки сборов

| Метод / путь | Auth | Назначение |
|---|---|---|
| `GET /api/v1/campaigns/today` | опц. | Топ-3 активных сбора для виджета «Сегодня помогаем». |
| `GET /api/v1/campaigns/{id}` | опц. | Детальная карточка `CampaignDetailResponse` (= List + `video_url`, `closed_early`, `close_note`, `documents[]`, `thanks_contents[]`, `cooldown_hours`). Возвращается только `active`/`completed`. 404 «Кампания не найдена». |
| `GET /api/v1/campaigns/{id}/documents` | нет | Документы сбора (по `sort_order`). 404 если сбор не активен. |
| `GET /api/v1/campaigns/{id}/share` | require_donor | Данные для шаринга (`share_url`, `title`, `description`). |

---

### 4.5 Разовое пожертвование

**User Story.**
**TL;DR для заказчика:** пользователь выбирает сумму и жертвует в сбор; приложение получает ссылку
на оплату ЮKassa и открывает её. Подтверждение оплаты приходит асинхронно.
**Как** авторизованный донор, **я хочу** пожертвовать сумму в сбор, **чтобы** поддержать подопечного.
**Критерии приёмки:**
- Дано активный сбор и сумма ≥ 1000 коп., когда создаётся донат, тогда `201` с `status=pending` и `payment_url`.
- Дано сбор не активен → `422 CAMPAIGN_NOT_ACTIVE`; сумма < 1000 → `422 MIN_DONATION_AMOUNT`.
- Дано недавний донат в этот сбор → `429 DONATION_COOLDOWN` с `next_available_at`.
- Дано запрос без токена → `401 AUTH_REQUIRED`.

**API.** `POST /api/v1/donations` · auth: опциональный `bearer_scheme` (фактически требуется — без
`user_id` сервис бросает `AUTH_REQUIRED`).

| Поле (`CreateDonationRequest`) | Тип | Обяз. | Описание |
|---|---|---|---|
| `campaign_id` | UUID | да | В какой сбор |
| `amount_kopecks` | int | да | ≥ 1000 |
| `email` | str? | нет | для чека |
| `payment_method_id` | UUID? | нет | оплата сохранённой картой |
| `save_payment_method` | bool | нет | сохранить карту после оплаты (дефолт false) |

Ответ `201` (`DonationResponse`): `id`, `campaign_id`, `amount_kopecks`, `status="pending"`,
`source="app"`, `payment_url`, `created_at`.
**Ошибки:** `404 NOT_FOUND` (сбор / карта), `422 CAMPAIGN_NOT_ACTIVE`, `401 AUTH_REQUIRED`,
`429 DONATION_COOLDOWN` (`details`: `retry_after`, `next_available_in_seconds`, `next_available_at`,
`server_time_utc`, `last_donation_id`), `422 MIN_DONATION_AMOUNT`.

**Бизнес-логика (`donation.create_donation`).**
1. Загрузить сбор; нет → `NotFoundError`. Статус ≠ `active` → `CAMPAIGN_NOT_ACTIVE`.
2. `user_id is None` → `AUTH_REQUIRED` (401).
3. **Кулдаун** `_check_donation_cooldown`: есть успешный/pending донат в этот сбор за последние
   `DONATION_COOLDOWN_HOURS`(8) → `DONATION_COOLDOWN` (429) с расчётом `next_available_at`.
4. `amount_kopecks < 1000` → `MIN_DONATION_AMOUNT`.
5. Если передан `payment_method_id` — проверить принадлежность пользователю и `is_deleted=false`,
   достать `provider_pm_id`; иначе `NotFoundError`.
6. `calculate_fees(amount)` → комиссия + сумма фонду; `idempotence_key=uuid7()`.
7. Создать `Donation(status=pending, source=app)`, `flush`.
8. ЮKassa `create_payment(amount, description, idempotence_key, return_url=.../payment-result?donation_id=...,
   save_payment_method, payment_method_id, metadata={type:"donation", entity_id})`.
9. Записать `provider_payment_id`, `payment_url`, `flush`. Вернуть донат (`201`).
10. **Асинхронно:** подтверждение приходит вебхуком (см. §5); зависшие `pending` подбирает крон-реконсиляция.

**Список и детали.**
- `GET /api/v1/donations` · require_donor — список своих донатов (фильтры `status`, `campaign_id`; курсор).
- `GET /api/v1/donations/{id}` · require_donor — детали (`DonationDetailResponse` с данными сбора/фонда). 404 если чужой.

---

### 4.6 Способы оплаты и восстановление аккаунта

> Карты сохраняются автоматически при донате с `save_payment_method=true` (через вебхук ЮKassa).
> Для каждой карты вычисляется `card_fingerprint` (sha256 от `first6|last4|exp_month|exp_year`),
> что позволяет «связать» разные анонимные аккаунты, оплаченные одной физической картой.

#### 4.6.1 Управление сохранёнными картами

| Метод / путь | Auth | Назначение |
|---|---|---|
| `GET /api/v1/payment-methods` | require_donor | Список сохранённых карт (`is_default` первым), `PaymentMethodResponse`: `id`, `provider`, `card_last4`, `card_type`, `title`, `is_default`, `created_at`. |
| `DELETE /api/v1/payment-methods/{pm_id}` | require_donor | Soft-delete карты; если была дефолтной — назначить дефолтной новейшую из оставшихся. 404 если чужая. |
| `POST /api/v1/payment-methods/{pm_id}/set-default` | require_donor | Сделать карту дефолтной (снять флаг с прочих карт пользователя). 404 если чужая. |

#### 4.6.2 Восстановление аккаунта по сохранённой карте

**User Story.**
**TL;DR для заказчика:** если человек раньше жертвовал анонимно (с разных устройств) одной и той
же картой, а потом завёл основной аккаунт, он может «забрать» историю и подписки тех старых
анонимных аккаунтов к себе — система находит их по «отпечатку» карты и объединяет.
**Как** пользователь, сменивший устройство/переустановивший приложение, **я хочу** вернуть свою
историю донатов и активные подписки, **чтобы** не потерять прогресс и не платить дважды.
**Критерии приёмки:**
- Дано у текущего пользователя есть сохранённая карта с отпечатком, и существуют анонимные
  аккаунты с тем же отпечатком, когда он запрашивает `orphans`, тогда возвращается список таких
  аккаунтов с превью (сколько донатов/подписок/сумма).
- Дано пользователь подтверждает `recover`, тогда все найденные аккаунты объединяются в текущий
  (перенос донатов/подписок/карт), и возвращается сводка перенесённого.
- Дано у карты нет отпечатка (старые данные), когда вызывается `{pm_id}/recover`, тогда `422 PM_NO_FINGERPRINT`.

**API.**

| Метод / путь | Auth | Тело/ответ |
|---|---|---|
| `GET /api/v1/payment-methods/orphans` | require_donor | Превью по **всем** отпечаткам карт пользователя → `list[OrphanedAccountPreview]`{`user_id`, `donations_count`, `subscriptions_count`, `active_subscriptions_count`, `total_donated_kopecks`, `last_seen_at`}. |
| `POST /api/v1/payment-methods/recover` | require_donor | Merge **всех** найденных аккаунтов → `RecoveryResult`{`merged_user_ids[]`, `donations_transferred`, `subscriptions_transferred`, `total_donated_kopecks_transferred`}. |
| `GET /api/v1/payment-methods/{pm_id}/orphans` | require_donor | То же превью, но по отпечатку **конкретной** карты. 404 если карта чужая. |
| `POST /api/v1/payment-methods/{pm_id}/recover` | require_donor | Merge по конкретной карте. 404 (чужая) / `422 PM_NO_FINGERPRINT` (нет отпечатка). |

**Бизнес-логика.**
1. Собрать набор `card_fingerprint` (по всем картам пользователя либо по одной `pm_id`); для варианта
   с `pm_id` — проверить принадлежность и наличие отпечатка (иначе `NotFoundError` / `PM_NO_FINGERPRINT`).
2. Найти кандидатов: `User` с `is_anonymous=true`, `is_deleted=false`, `id != current`, у которых есть
   непросроченная карта с тем же отпечатком.
3. Для `orphans` — вернуть превью (агрегаты по каждому кандидату), ничего не меняя.
4. Для `recover` — для каждого кандидата выполнить `merge_anonymous_into(source=кандидат, target=текущий)`
   (та же процедура слияния, что в §4.1.4: перенос донатов/подписок/карт/логов, дедуп подписок и карт,
   агрегаты, soft-delete источника, отзыв его токенов). Вернуть сводку.

> Это та же механика слияния, что и при привязке email (§4.1.4), но триггер — совпадение отпечатка карты,
> а не email. Источник всегда анонимный аккаунт; целевой — текущий авторизованный.

---

### 4.7 Подписки (регулярные пожертвования)

#### 4.7.1 Создание подписки

**User Story.**
**TL;DR для заказчика:** пользователь оформляет регулярные микро-донаты (например, 1 ₽/день,
списание раз в неделю или месяц) и выбирает, куда направлять деньги: в конкретный сбор, в пул
фонда или в общий пул платформы. Подписка активируется после первой успешной оплаты (привязки карты).
**Как** донор, **я хочу** настроить регулярную помощь, **чтобы** помогать системно, не задумываясь.
**Критерии приёмки:**
- Дано допустимая сумма (100/300/500/1000 коп./день) и валидная стратегия, тогда `201` с
  `status=pending_payment_method` (ждёт привязки карты).
- Дано стратегия `specific_campaign` без `campaign_id` (или `foundation_pool` без `foundation_id`) → `422 VALIDATION_ERROR`.
- Дано сумма не из набора → `400 INVALID_AMOUNT`.
- Дано у пользователя уже 5 активных/приостановленных/ожидающих подписок → `422 SUBSCRIPTION_LIMIT_EXCEEDED`.
- Дано `specific_campaign` с неактивным сбором → `422 CAMPAIGN_NOT_ACTIVE`.

**API.** `POST /api/v1/subscriptions` · require_donor.

| Поле (`CreateSubscriptionRequest`) | Тип | Обяз. | Ограничения |
|---|---|---|---|
| `amount_kopecks` | int | да | ∈ {100, 300, 500, 1000} (в день) |
| `billing_period` | str | да | `weekly` \| `monthly` |
| `allocation_strategy` | str | да | `platform_pool` \| `foundation_pool` \| `specific_campaign` |
| `campaign_id` | UUID? | усл. | обязателен для `specific_campaign` |
| `foundation_id` | UUID? | усл. | обязателен для `foundation_pool` |

Ответ `201` (`SubscriptionResponse`): `id`, `amount_kopecks`, `billing_period`, `allocation_strategy`,
`campaign_id`/`campaign_title`, `foundation_id`/`foundation_name`, `status`, `paused_reason`,
`paused_at`, `next_billing_at`, `created_at`.

**Бизнес-логика.**
1. Валидация суммы (`INVALID_AMOUNT`).
2. Проверка лимита (`SELECT COUNT ... FOR UPDATE` по статусам active/paused/pending; ≥5 → `SUBSCRIPTION_LIMIT_EXCEEDED`).
3. `specific_campaign`: требуется `campaign_id`, сбор должен быть `active` (`CAMPAIGN_NOT_ACTIVE`).
   `foundation_pool`: требуется `foundation_id`.
4. Создать `Subscription(status=pending_payment_method, payment_method_id=null, next_billing_at=null)`.

> Активация — только после успешной первой оплаты (см. 4.7.3 bind-card + §5).

#### 4.7.2 Управление подпиской

| Метод / путь | Auth | Назначение / правила |
|---|---|---|
| `GET /api/v1/subscriptions` | require_donor | Список своих подписок (active/paused/pending), DESC по `created_at`. |
| `GET /api/v1/subscriptions/active` | require_donor | `ActiveSubscriptionResponse`{`has_active`, `subscription?`}. |
| `PATCH /api/v1/subscriptions/{id}` | require_donor | Обновить `amount_kopecks`/стратегию/`campaign_id`/`foundation_id`. 404; `400 INVALID_AMOUNT`. |
| `POST /api/v1/subscriptions/{id}/pause` | require_donor | `active → paused`, `paused_reason=user_request`, `next_billing_at=null`. Иначе `422 SUBSCRIPTION_NOT_ACTIVE`. |
| `POST /api/v1/subscriptions/{id}/resume` | require_donor | `paused → active`, `next_billing_at=now+период`. Если не на паузе → `422 SUBSCRIPTION_NOT_ACTIVE`. |
| `DELETE /api/v1/subscriptions/{id}` | require_donor | `→ cancelled`, `cancelled_at=now`, `next_billing_at=null`. `204`. Необратимо. |

#### 4.7.3 Привязка карты (первая оплата подписки)

**User Story.** Как донор, я хочу привязать карту к созданной подписке, чтобы активировать
регулярные списания.

**API.** `POST /api/v1/subscriptions/{id}/bind-card` · require_donor. Ответ `201` (`BindCardResponse`):
`payment_url`, `confirmation_type="redirect"`, `subscription_id`, `amount_kopecks` (= дневная × множитель
периода), `description`.
**Ошибки:** `404 NOT_FOUND`; `422 SUBSCRIPTION_ALREADY_ACTIVE` (если статус ≠ `pending_payment_method`).

**Бизнес-логика.**
1. Загрузить подписку; статус должен быть `pending_payment_method`.
2. Сумма первого платежа = `billing_amount(daily, period)` = `daily × {weekly:7, monthly:30}`.
3. `calculate_fees`, `idempotence_key=uuid7()`, создать `Transaction(status=pending)`, `flush`.
4. ЮKassa `create_payment(save_payment_method=true, return_url=.../payment-result?transaction_id=...&subscription_id=...,
   metadata={type:"transaction", entity_id, subscription_id})`.
5. Записать `provider_payment_id`, вернуть `payment_url`.
6. **При успехе (вебхук):** подписка → `active`, сохраняется `payment_method_id` для будущих списаний,
   выставляется `next_billing_at`.

#### 4.7.4 Аллокация и автоматическое списание (фон)

- **Поиск целевого сбора** (`find_campaign_for_subscription`): `specific_campaign` → если сбор всё ещё
  активен, он; иначе fallback в пул фонда → пул платформы. `foundation_pool` → самый срочный активный
  сбор фонда (`urgency_level DESC, sort_order ASC`); fallback — пул платформы. `platform_pool` →
  самый срочный активный сбор по всей платформе (с учётом доли сбора).
- **Реаллокация** при завершении сбора (`reallocate_campaign_subscriptions` / `reallocate_subscription`):
  подписка переводится на новый сбор и пишется запись в `allocation_changes`; если активных сборов нет —
  подписка авто-ставится на паузу с `paused_reason=no_campaigns`, `next_billing_at=null`.
- **Списание** (крон `process_recurring_billing`, каждые 30 мин): берёт `active`-подписки с
  `next_billing_at <= now` и непустым `payment_method_id`; **резолвит целевой сбор** через
  `find_campaign_for_subscription`, создаёт `Transaction(campaign_id=<resolved>)` и вызывает рекуррентный
  платёж ЮKassa. Если активных сборов нет — `Transaction(status=skipped, skipped_reason=no_active_campaigns)`
  без списания, стрик сохраняется (`mark_streak_no_campaigns`), `next_billing_at` сдвигается на период вперёд.
  Подробнее — §5 и §7.
- **Ретраи** при «мягком отказе»: `SOFT_DECLINE_RETRY_DAYS = (1, 3, 7, 14)` дней; до 4 попыток.

> ✅ **Исправлено (ветка `fix/spec-gaps`).** Ранее целевой сбор при списании не резолвился: у пуловых
> подписок (`platform_pool`/`foundation_pool`) `campaign_id` оставался `NULL`, деньги списывались, но не
> аллоцировались (импакт/стрик не росли). Теперь сбор резолвится при каждом списании и при `bind-card`;
> при отсутствии активных сборов списание не производится (`skipped`). Покрыто `test_billing_allocation.py`.

---

### 4.8 Транзакции (история списаний по подпискам)

| Метод / путь | Auth | Назначение |
|---|---|---|
| `GET /api/v1/transactions` | require_donor | query: `status`, `campaign_id`, `subscription_id`, `date_from`, `date_to`, `limit`, `cursor`. Пагинированный список `TransactionListItem`. |
| `GET /api/v1/transactions/{id}` | require_donor | path `transaction_id` UUID. `TransactionDetailResponse`. 404 если чужая. |

- **`TransactionListItem`:** `id`, `subscription_id`, `campaign_id?`, `campaign_title?`, `campaign_status?`, `campaign_thumbnail_url?`, `foundation_name?`, `amount_kopecks`, `status`, `skipped_reason?`, `created_at`.
- **`TransactionDetailResponse`** = list-item + `foundation_id?`, `foundation_logo_url?`, `platform_fee_kopecks`, `nco_amount_kopecks`, `cancellation_reason?`, `attempt_number`, `next_retry_at?`.

---

### 4.9 Геймификация: impact, стрик, достижения

**User Story.**
**TL;DR для заказчика:** пользователь видит свой «вклад» — сколько всего пожертвовал, сколько раз и
свою серию дней подряд (стрик). За достижение порогов (серия дней, суммарная сумма, число донатов)
он получает ачивки. Это удерживает и мотивирует жертвовать регулярно.
**Как** жертвователь, **я хочу** видеть прогресс и получать достижения, **чтобы** помогать регулярно
и чувствовать вклад.
**Критерии приёмки:**
- Дано успешная оплата (донат или списание по подписке), тогда обновляются кэш-счётчики пользователя
  и пересчитывается стрик; при выполнении условия выдаётся новое достижение.
- Дано донат сегодня при `last_streak_date = вчера`, тогда `current_streak_days += 1`.
- Дано первый донат за период (не вчера), тогда `current_streak_days = 1`.
- Дано несколько донатов за один день, тогда стрик не растёт повторно (идемпотентность по дню).

**API.**

| Метод / путь | Auth | Ответ |
|---|---|---|
| `GET /api/v1/impact` | require_donor | `ImpactResponse`: `total_donated_kopecks`, `streak_days`, `donations_count` (кэш-поля `User`), `streak_includes_skipped` (bool, дефолт true). 404 если нет. |
| `GET /api/v1/impact/achievements` | require_donor | `list[AchievementResponse]`{`id`, `code`, `title`, `description`, `icon_url`, `earned_at`} — все активные достижения; `earned_at=null` = не получено. |

**Бизнес-логика (триггерится из `process_successful_payment` после успешной оплаты).**
1. **Импакт** (`update_user_impact`): `total_donated_kopecks += amount`, `total_donations_count += 1`.
2. **Стрик** (`update_user_streak`): `last_streak_date = сегодня` → без изменений;
   `= вчера` → `current_streak_days += 1`; иначе → `current_streak_days = 1`. Затем `last_streak_date = сегодня`.
   (Пропуск списания по причине «нет активных сборов» стрик не ломает — `mark_streak_no_campaigns`.)
3. **Достижения** (`check_and_award_achievements`): для каждого неполученного активного достижения
   проверить условие по `condition_type` (`streak_days` → `current_streak_days`; `total_amount_kopecks`
   → `total_donated_kopecks`; `donations_count` → `total_donations_count`) `≥ condition_value`; при
   выполнении создать `UserAchievement` (уникальность `(user_id, achievement_id)`).

> Счётчики денормализованы (кэш в `users`) ради скорости чтения; ночная реконсиляция (§7) сверяет и
> исправляет их по фактическим успешным донатам/транзакциям. При возврате средств они откатываются (§5.3).

---

### 4.10 Благодарности

| Метод / путь | Auth | Назначение |
|---|---|---|
| `GET /api/v1/thanks/unseen` | require_donor | Непросмотренные благодарности (видео/аудио) по сборам, которым пользователь донатил, с его вкладом. |
| `GET /api/v1/thanks/{id}` | require_donor | Конкретная благодарность + вклад пользователя (сумма/кол-во/первый/последний донат). **Побочный эффект:** помечает как просмотренную (`thanks_content_shown`, UPSERT). 404 «Благодарность не найдена». |

---

### 4.11 Патрон-ссылки

> Доступно только роли `patron`. Патрон создаёт ссылку на оплату конкретной суммы в конкретный сбор
> (например, для сбора офлайн-пожертвований). Под капотом создаётся `Donation` с `source=patron_link`.

| Метод / путь | Auth | Назначение |
|---|---|---|
| `POST /api/v1/patron/payment-links` | require_patron | Создать ссылку (`{campaign_id, amount_kopecks}`) → `PaymentLinkResponse` (`payment_url`, `expires_at=now+24ч`, `status=pending`). Сбор должен быть `active` (`422 CAMPAIGN_NOT_ACTIVE`). |
| `GET /api/v1/patron/payment-links` | require_patron | Список своих ссылок (фильтр `status`, курсор). ⚠️ **list-ответ отдаёт сырую модель** — поля `PaymentLinkResponse` **плюс** `donation_id` и `created_by_user_id` (в отличие от `POST`-ответа, который строго по схеме). |
| `GET /api/v1/patron/payment-links/{id}` | require_patron | Детали ссылки (`PaymentLinkResponse`). 404 «Ссылка не найдена». |

Истёкшие неоплаченные ссылки переводятся в `expired` фоновой задачей (см. §7).

> ✅ **Исправлено (ветка `fix/spec-gaps`).** Создаётся реальный платёж ЮKassa (`patron.py`):
> `donation.provider_payment_id` и `payment_url` заполняются из ответа провайдера, `metadata.type=patron_link`.
> Подтверждение приходит вебхуком (тип `patron_link` → `Donation.success` + `PatronPaymentLink.paid`),
> а зависшие `pending` теперь подбирает крон-реконсиляция (у доната есть `provider_payment_id`).

---

### 4.12 Платёжный результат и вебхуки

- **`GET /payment-result`** (без префикса `/api/v1`) · auth: нет. Query: `donation_id` /
  `transaction_id` / `subscription_id`. Возвращает HTML-страницу (`Cache-Control: no-store`), которая
  открывает deep-link `porublyu://payment-result?...` и через 1.5 с показывает запасную кнопку.
  Используется как HTTPS-мост после редиректа ЮKassa обратно в приложение.
- **`POST /api/v1/webhooks/yookassa`** · auth: проверка IP из официальных диапазонов ЮKassa
  (в `DEBUG` отключена), иначе `403`. Обрабатывает `payment.succeeded` / `payment.canceled` —
  см. §5.

---

### 4.13 Медиа-прокси

- **`GET /media/{s3_key}`** и **`HEAD /media/{s3_key}`** · auth: нет. Проксирует файлы из S3/MinIO с
  поддержкой HTTP Range (`206 Partial Content`, чанки по 256 КБ), `404` если нет, `416` при некорректном
  Range. В проде запросы обычно перехватывает nginx; ручка — запасной путь.

---

### 4.14 Служебные эндпоинты

- **`GET /api/v1/health`** · auth: нет. Проверка доступности сервиса (для load-balancer / мониторинга).

---

### 4.15 Push-уведомления (сквозная функциональность)

> У push нет отдельного API для клиента — токен устройства передаётся при `device-register`/`PATCH /me`,
> а настройки управляются `PATCH /me/notifications`. Отправка инициируется событиями и фоновыми задачами.
> Провайдер — Firebase (FCM/APNS); при `NOTIFICATION_PROVIDER != firebase` или отсутствии токена пуш
> логируется как `mock`. Каждая отправка пишется в `notification_logs` (`sent`/`mock`/`failed`).

**Типы уведомлений и триггеры:**

| `notification_type` | Когда | Уважает настройку |
|---|---|---|
| `donation_success` | успешный разовый донат (вебхук) | `push_on_payment` |
| `payment_success` | успешное списание по подписке (вебхук) | `push_on_payment` |
| `campaign_completed` | сбор завершён/закрыт админом (рассылка донорам) | `push_campaign_completed` |
| `thanks_content` | в активный сбор добавлена благодарность (рассылка донорам) | `push_on_campaign_change` |
| `streak_daily` | ежедневный пуш по стрику (крон `send_streak_pushes`) | `push_daily_streak` |
| `donation_reminder` | по истечении кулдауна напомнить про сбор (крон) | `push_on_donation_reminder` |
| `subscription_expired_inactive` | подписки отменены при зачистке неактивного анонима (крон) | — |

**Бизнес-логика отправки (`send_push`).** Если провайдер Firebase и есть `push_token` — отправить FCM
(high priority, sound/badge); статус `sent`. При ошибке — статус `failed`; если ошибка вида
`Unregistered`/`SenderIdMismatch`/`InvalidArgument` — **очистить `push_token`** пользователя (токен
протух). Без провайдера/токена — `mock`. Любой исход фиксируется в `notification_logs`.

> Пуши настраиваются и отключаются пользователем через `PATCH /api/v1/me/notifications` (§4.2);
> отправка каждого типа проверяет соответствующий флаг `notification_preferences`.

---

### 4.16 Снимки авторизованных экранов (проверено на живом инстансе)

> Все экраны, требующие входа, прогнаны на локальном инстансе под реальной авторизацией
> (OTP-вход dev-кодом `111111`, см. §2.4а) как donor и patron. **Пропущенных эндпоинтов/экранов
> не выявлено** — каждый документированный авторизованный эндпоинт отвечает `200` (или ожидаемой
> ошибкой). Ниже — фактические ответы (сокращённо) как эталон для фронта.

**`GET /me`** — профиль с кэш-метриками:
```json
{ "id":"…","email":"donor@example.com","name":"Иван Донор","role":"donor","timezone":"Europe/Moscow",
  "is_anonymous":false,"is_email_verified":true,
  "notification_preferences":{"push_on_payment":true,"push_on_campaign_change":true,"push_daily_streak":true,"push_campaign_completed":true,"push_on_donation_reminder":true},
  "current_streak_days":10,"total_donated_kopecks":150000,"total_donations_count":12,"donation_cooldown_hours":8,"created_at":"…" }
```

**`GET /campaigns` (авторизовано) — per-user поля заполнены:**
```json
{ "id":"…","title":"Лечение Маши","thumbnail_url":"http://localhost:8000/media/thumbnails/campaign_0.jpg",
  "status":"active","goal_amount":500000,"collected_amount":127500,"donors_count":3,"urgency_level":5,
  "foundation":{"id":"…","name":"Фонд «Добрый дом»","logo_url":null},
  "donated_today":false,"has_any_donation":true,
  "last_donation":{"id":"…","amount_kopecks":50000,"status":"success","created_at":"…"},
  "next_available_at":null,"can_donate_now":true,"next_available_in_seconds":null,"server_time_utc":"…" }
```

**`GET /impact`** → `{ "total_donated_kopecks":150000, "streak_days":10, "donations_count":12, "streak_includes_skipped":true }`
**`GET /impact/achievements`** → массив с `earned_at` у полученных (`amount_1000`, `count_10`, `streak_7`).
**`GET /donations`** → элементы с `campaign_title`/`campaign_status`/`campaign_thumbnail_url`/`foundation_name`/`amount_kopecks`/`status` (success/pending/failed/refunded).
**`GET /subscriptions`** → 3 шт. со статусами `active`/`paused`/`cancelled`.
**`GET /transactions`** → success/failed/skipped с `skipped_reason`/`next_retry_at`.

**`POST /donations`** — успех `201` (`status=pending`, `payment_url`), повтор в тот же сбор → `429`:
```json
{ "error":{ "code":"DONATION_COOLDOWN","message":"В этот сбор можно снова помочь позже.",
  "details":{ "retry_after":28792,"next_available_in_seconds":28792,
  "next_available_at":"2026-06-01T20:03:08Z","server_time_utc":"2026-06-01T12:03:15Z","last_donation_id":"…" } } }
```

**`GET /patron/payment-links` (patron)** — list отдаёт сырую модель (видны `donation_id`, `created_by_user_id`):
```json
{ "data":[{ "id":"…","campaign_id":"…","amount_kopecks":10000,"status":"pending",
  "payment_url":"…","expires_at":"…","created_at":"…","donation_id":"…","created_by_user_id":"…" }],
  "pagination":{"next_cursor":null,"has_more":false,"total":null} }
```

> Прочие авторизованные экраны (`/subscriptions/active`, `/donations/{id}`, `/transactions/{id}`,
> `/thanks/unseen`, `/payment-methods`, `/payment-methods/orphans`, `/campaigns/{id}` детально,
> `/campaigns/{id}/share`) также проверены — `200`, форма соответствует §4.2–4.11.

---

## 5. Платёжный поток end-to-end (ЮKassa)

### 5.1 Разовый донат

1. `POST /donations` → создаётся `Donation(pending)`, платёж в ЮKassa, клиент получает `payment_url`.
2. Клиент открывает `payment_url`, пользователь платит; ЮKassa редиректит на `/payment-result` → deep-link обратно в приложение.
3. ЮKassa шлёт вебхук `payment.succeeded` (`metadata.type=donation`):
   - найти донат по `provider_payment_id`; `pending → success`;
   - `process_successful_payment(campaign_id, user_id, amount)`:
     - атомарно `collected_amount += amount`; если новый донор — `INSERT campaign_donors` + `donors_count += 1`;
     - `check_campaign_auto_complete` (если `collected ≥ goal` и не `is_permanent` → `completed`);
     - обновить стрик и `total_donated_kopecks`/`total_donations_count` пользователя;
   - если `save_payment_method=1` — сохранить карту (`save_from_yookassa`, расчёт `card_fingerprint`, дефолт если первая);
   - выдать достижения, отметить непросмотренные благодарности, отправить пуш (если включено).
4. `payment.canceled` → `Donation → failed`.
5. **Подстраховка:** крон `reconcile_pending_donations` (каждые 5 мин) добивает `pending`-донаты старше
   5 мин, опрашивая статус в ЮKassa; старше 24 ч и всё ещё pending → `failed` (брошенные).

### 5.3 Возврат средств (refund)

1. Админ вызывает `POST /api/v1/admin/donations/{id}/refund` → ЮKassa `create_refund(payment_id, amount)`.
2. При `succeeded` донат → `refunded`, счётчики откатываются (`collected_amount`, импакт пользователя,
   и `donors_count` — если у пользователя не осталось других успешных вкладов в этот сбор). Стрик **не** откатывается.
3. Вебхук `refund.succeeded` обрабатывается идемпотентно (действует только если сущность ещё `success`) —
   как подстраховка и для возвратов, инициированных вне приложения. Аналогично работает для транзакций подписок.

### 5.2 Подписка (рекуррент)

1. `POST /subscriptions` → `pending_payment_method`.
2. `POST /subscriptions/{id}/bind-card` → `Transaction(pending)` + платёж с `save_payment_method=true`.
3. Вебхук `payment.succeeded` (`type=transaction`): `Transaction → success`; подписка
   `pending_payment_method → active`, сохраняется `payment_method_id`, выставляется
   `next_billing_at = now + {7|30} дней`; начисления как в 5.1.
4. Крон `process_recurring_billing` (каждые 30 мин): для `active`-подписок с наступившим
   `next_billing_at` резолвит целевой сбор (`find_campaign_for_subscription`), создаёт `Transaction` и делает
   рекуррентный платёж по сохранённому `payment_method_id`. Нет активных сборов → `skipped`-транзакция без
   списания (см. §4.7.4).
5. `payment.canceled` (`type=transaction`): `Transaction → failed`, при `attempt_number <
   len(SOFT_DECLINE_RETRY_DAYS)` назначается `next_retry_at`; крон `retry_failed_transactions`
   (каждые 6 ч) повторяет попытку (инкремент `attempt_number`, новый `idempotence_key`).

---

# ЧАСТЬ B. Бэкенд для админ-панели

> Всё, что нужно фронту админ-панели: управление фондами, сборами, контентом, медиа,
> пользователями, выплатами, статистикой, документами. Базовый префикс `/api/v1/admin`.
> **Все ручки требуют `require_admin`** (JWT с `role=admin` и админской audience `porubly-admin`,
> §2.4) — **кроме** `auth/login`, `auth/refresh`, `auth/logout`.
> Формат ошибок и курсорная пагинация — общие (§2.5, §2.6): списки возвращают
> `{ "data": [...], "pagination": { "next_cursor", "has_more", "total": null } }`.
> Пагинация-параметры везде: `limit` (1–100, дефолт 20), `cursor` (base64).
>
> ⚠️ **Конфликты (409) в админ-API** приходят с верхнеуровневым `error.code = "CONFLICT"`, а конкретный
> идентификатор лежит в `error.details.code` (например `INN_ALREADY_EXISTS`, `ADMIN_EMAIL_EXISTS`,
> `ACHIEVEMENT_CODE_EXISTS`, `SLUG_ALREADY_EXISTS`, `VERSION_CONFLICT`, `DUPLICATE_OFFLINE_PAYMENT`).
> В таблицах ниже такие ошибки помечены как `409 CONFLICT/details.code=…`. Ошибки уровня бизнес-правил
> (422) и `INVALID_STATUS_TRANSITION` приходят как верхнеуровневый `error.code`.

## 6. Админ-API

### 6.1 Авторизация админа (`/api/v1/admin/auth`)

| Метод / путь | Auth | Запрос | Ответ |
|---|---|---|---|
| `POST /login` | нет | `AdminLoginRequest`{`email`: EmailStr, `password`: str} | `200` `AdminTokenResponse`{`access_token`, `refresh_token`, `token_type="bearer"`, `admin`{`id`, `email`, `name?`}} |
| `POST /refresh` | нет | `RefreshRequest`{`refresh_token`: str} | `200` `TokenResponse`{`access_token`, `refresh_token`, `token_type`} |
| `POST /logout` | нет | `LogoutRequest`{`refresh_token`: str} | `204` |

**Ошибки:** `401 ADMIN_AUTH_FAILED` («Неверный email или пароль» / аккаунт деактивирован).
Админский access-токен подписывается отдельной audience `porubly-admin` (см. §2.4, §9.1).

### 6.2 Фонды (`/api/v1/admin/foundations`)

| Метод / путь | Path/Query | Запрос | Ответ / ошибки |
|---|---|---|---|
| `GET /` | query: `status`(enum FoundationStatus), `search`, `limit`, `cursor` | — | `200` список `FoundationAdminResponse` |
| `POST /` | — | `FoundationCreate` | `201` `FoundationAdminResponse`; `409 CONFLICT/details.code=INN_ALREADY_EXISTS` |
| `GET /{foundation_id}` | path: `foundation_id` UUID | — | `200` `FoundationAdminResponse`; `404 NOT_FOUND` |
| `PATCH /{foundation_id}` | path: `foundation_id` | `FoundationUpdate` | `200` `FoundationAdminResponse`; `404`; `409 CONFLICT/details.code=INN_ALREADY_EXISTS` |

**`FoundationCreate`:** `name`* str, `legal_name`* str, `inn`* str (уникален), `description?`, `logo_url?`, `website_url?`.
**`FoundationUpdate`** (все опц.): `name?`, `legal_name?`, `inn?` (ре-валидация уникальности), `description?`,
`logo_url?`, `logo_media_asset_id?` UUID (резолвится в `logo_url`), `website_url?`, `status?`, `yookassa_shop_id?`.
**`FoundationAdminResponse`:** `id`, `name`, `description?`, `logo_url?`, `website_url?`, `status`,
`legal_name`, `inn`, `yookassa_shop_id?`, `verified_at?`, `created_at`, `updated_at`.
**Побочное:** перевод `status→active` при пустом `verified_at` → `verified_at=now`.

### 6.3 Сборы (`/api/v1/admin/campaigns`)

**CRUD:**

| Метод / путь | Path/Query | Запрос | Ответ / ошибки |
|---|---|---|---|
| `GET /` | query: `status`(enum), `foundation_id`, `search`, `limit`, `cursor` | — | `200` список `AdminCampaignResponse` |
| `POST /` | — | `AdminCampaignCreate` | `201` `AdminCampaignResponse`; `404 NOT_FOUND` (фонд) |
| `GET /{campaign_id}` | path: `campaign_id` | — | `200` `AdminCampaignDetailResponse`; `404` |
| `PATCH /{campaign_id}` | path: `campaign_id` | `AdminCampaignUpdate` | `200` `AdminCampaignResponse`; `404` |
| `POST /backfill-thumbnails` | query: `limit`(1–500, деф.100) | — | `200` `{scanned, filled, failed, filled_ids[], failed_items[]}` |

**`AdminCampaignCreate`:** `foundation_id`* UUID, `title`* str, `description?`, `video_url?`, `thumbnail_url?`,
`goal_amount?` int, `urgency_level` int (деф.3), `is_permanent` bool (деф.false), `ends_at?` datetime, `sort_order` int (деф.0).
**`AdminCampaignUpdate`** (все опц.): `foundation_id?`, `title?`, `description?`, `video_url?`, `thumbnail_url?`,
`video_media_asset_id?` / `thumbnail_media_asset_id?` UUID (резолвятся в URL), `goal_amount?`, `urgency_level?`,
`is_permanent?`, `ends_at?`, `sort_order?`.
**`AdminCampaignResponse`:** `id`, `foundation_id`, `foundation_name?`, `title`, `description?`, `video_url?`,
`thumbnail_url?`, `status`, `goal_amount?`, `collected_amount`, `donors_count`, `urgency_level`, `is_permanent`,
`ends_at?`, `sort_order`, `closed_early`, `close_note?`, `created_at`, `updated_at`.
**`AdminCampaignDetailResponse`** = `AdminCampaignResponse` + `documents[]`{`id`,`title`,`file_url`,`sort_order`}
+ `thanks_contents[]`{`id`,`type`,`media_url`,`title?`,`description?`}.
**Побочное:** при `video_url` без `thumbnail_url` — авто-генерация превью из первого кадра (best-effort).

**Переходы статуса** (валидируются `validate_status_transition`; ошибка → `422 INVALID_STATUS_TRANSITION`):

| Метод / путь | Переход | Запрос | Побочные эффекты |
|---|---|---|---|
| `POST /{id}/publish` | draft→active (и paused→active) | — | — |
| `POST /{id}/pause` | active→paused | — | — |
| `POST /{id}/complete` | active\|paused→completed | — | реаллокация подписок (`campaign_completed`) + пуш донорам «Сбор завершён» |
| `POST /{id}/close-early` | active\|paused→completed | `CloseEarlyRequest`{`close_note`* str} | `closed_early=true`, сохранить `close_note`; реаллокация (`campaign_closed_early`) + пуш донорам |
| `POST /{id}/archive` | completed→archived | — | — |
| `POST /{id}/force-realloc` | — | — | `200` `{reallocated_subscriptions: int}`; реаллокация всех активных подписок (`manual_by_admin`) |

Допустимая матрица: `draft→active`, `active→paused\|completed`, `paused→active\|completed`, `completed→archived` (archived — терминальный).

**Офлайн-платежи:**

| Метод / путь | Запрос | Ответ / ошибки |
|---|---|---|
| `POST /{id}/offline-payment` | `OfflinePaymentCreate`{`amount_kopecks`* int>0, `payment_method`* (`cash`\|`bank_transfer`\|`other`), `payment_date`* date, `description?`, `external_reference?`} | `201` `OfflinePaymentResponse`{`id`,`campaign_id`,`amount_kopecks`,`payment_method`,`description?`,`external_reference?`,`payment_date`,`recorded_by_admin_id`,`created_at`}; `404`; `409 CONFLICT/details.code=DUPLICATE_OFFLINE_PAYMENT` (дедуп по `campaign+external_reference+date+amount`) |
| `GET /{id}/offline-payments` | query: `limit`,`cursor` | `200` список `OfflinePaymentResponse` |

**Побочное офлайн-платежа:** атомарный `collected_amount += amount`, авто-complete при достижении цели.

**Документы сбора:**

| Метод / путь | Запрос | Ответ |
|---|---|---|
| `POST /{id}/documents` | `CampaignDocumentCreate`{`title`* str, `file_url`* str, `sort_order` int (деф.0)} | `201` `CampaignDocumentResponse`{`id`,`title`,`file_url`,`sort_order`}; `404` |
| `DELETE /{id}/documents/{doc_id}` | — | `204`; `404` |

**Благодарности:**

| Метод / путь | Запрос | Ответ / побочное |
|---|---|---|
| `POST /{id}/thanks` | `ThanksContentCreate`{`type`* (`video`\|`audio`), `media_url`* str, `title?`, `description?`} | `201` `ThanksContentBrief`; если сбор `active` — пуш донорам «Благодарность от фонда» |
| `PATCH /{id}/thanks/{thanks_id}` | `ThanksContentUpdate` (все опц.) | `200` `ThanksContentBrief`; `404` |
| `DELETE /{id}/thanks/{thanks_id}` | — | `204`; `404` |

### 6.3a Возвраты (`/api/v1/admin/donations`)

| Метод / путь | Запрос | Ответ / ошибки |
|---|---|---|
| `POST /{donation_id}/refund` | — | `200` `{donation_id, refund_id, refund_status, donation_status}`; `404`; `422 REFUND_NOT_ALLOWED` (статус ≠ success); `422 REFUND_NO_PAYMENT` (нет `provider_payment_id`) |

При `refund.status=succeeded` донат → `refunded`, счётчики откатываются (`reverse_successful_payment`, см. §5.3).
Вебхук `refund.succeeded` идемпотентно подстраховывает.

### 6.4 Медиа (`/api/v1/admin/media`)

| Метод / путь | Path/Query | Запрос | Ответ / ошибки |
|---|---|---|---|
| `GET /` | query: `type`(`video`\|`document`\|`audio`\|`image`), `search`, `limit`, `cursor` | — | `200` список `MediaAssetListItem`{`id`,`key`,`url`,`type`,`filename`,`size_bytes`,`content_type`,`created_at`}; `422 INVALID_MEDIA_TYPE` |
| `GET /{media_id}` | path: `media_id` | — | `200` `MediaAssetDetailResponse` (+`download_url`, `uploaded_by_admin_id?`); `404` |
| `GET /{media_id}/download` | path: `media_id` | — | `302` редирект на public URL; `404` |
| `POST /upload` | multipart | form: `file`*, `type`* (enum) | `201` `{id,key,url,filename,size_bytes,content_type}`; `422 INVALID_MEDIA_TYPE`/`FILE_TOO_LARGE`/`INVALID_FILE_FORMAT` |
| `POST /reindex-urls` | — | — | `200` `{updated_assets, updated_campaigns, updated_foundations, updated_documents, updated_thanks}` |

**Лимиты загрузки:** video ≤500 МБ (`video/mp4`), document ≤10 МБ (`application/pdf`), audio ≤50 МБ
(`audio/mpeg|mp4|ogg|webm`), image ≤20 МБ (`image/jpeg|png|webp|gif|svg+xml`).

### 6.5 Пользователи (`/api/v1/admin/users`)

| Метод / путь | Path/Query | Ответ / побочное |
|---|---|---|
| `GET /` | query: `role`(`donor`\|`patron`), `search`, `limit`, `cursor` | `200` список `AdminUserListItem`{`id`,`email`,`phone?`,`name?`,`avatar_url?`,`role`,`is_active`,`current_streak_days`,`total_donated_kopecks`,`total_donations_count`,`created_at`,`updated_at`} |
| `GET /{user_id}` | path: `user_id` | `200` `AdminUserListItem` + `subscriptions[]`{`id`,`amount_kopecks`,`billing_period`,`allocation_strategy`,`campaign_id?`,`foundation_id?`,`status`,`next_billing_at?`,`created_at`} + `recent_donations[]`{`id`,`campaign_id`,`amount_kopecks`,`status`,`source`,`created_at`}; `404` |
| `POST /{user_id}/grant-patron` | path | `200` `{id, role:"patron"}`; `404` |
| `POST /{user_id}/revoke-patron` | path | `200` `{id, role:"donor"}`; `404` |
| `POST /{user_id}/deactivate` | path | `200` `{id, is_active:false}`; `404`. Побочное: отзыв всех refresh-токенов + пауза активных подписок |
| `POST /{user_id}/activate` | path | `200` `{id, is_active:true}`; `404` |

### 6.6 Статистика (`/api/v1/admin/stats`)

| Метод / путь | Query | Ответ |
|---|---|---|
| `GET /overview` | `period_from?` date, `period_to?` date | `200` `OverviewStatsResponse`{`gmv_kopecks`, `platform_fee_kopecks`, `active_subscriptions`, `total_donors`, `new_donors_period`, `retention_30d` float, `retention_90d` float, `period_from?`, `period_to?`} |
| `GET /campaigns/{campaign_id}` | path: `campaign_id` | `200` `CampaignStatsResponse`{`campaign_id`, `campaign_title`, `collected_amount`, `donors_count`, `average_check_kopecks`, `subscriptions_count`, `donations_count`, `offline_payments_amount`}; `404` |

### 6.7 Выплаты (`/api/v1/admin/payouts`)

| Метод / путь | Path/Query | Запрос | Ответ / ошибки |
|---|---|---|---|
| `GET /` | query: `foundation_id?`, `period_from?`, `period_to?`, `limit`, `cursor` | — | `200` список `PayoutResponse` (+`foundation_name?`) |
| `POST /` | — | `PayoutCreateRequest`{`foundation_id`* UUID, `amount_kopecks`* int, `period_from`* date, `period_to`* date, `transfer_reference?`, `note?`} | `201` `PayoutResponse`; `404 NOT_FOUND` (фонд) |
| `GET /balance` | query: `period_from?`, `period_to?` | — | `200` `{balances:[{foundation_id, foundation_name, total_nco_kopecks, total_paid_kopecks, due_kopecks}]}` |

**`PayoutResponse`:** `id`, `foundation_id`, `foundation_name?`, `amount_kopecks`, `period_from`, `period_to`,
`transfer_reference?`, `note?`, `created_by_admin_id`, `created_at`.

### 6.8 Достижения (`/api/v1/admin/achievements`)

| Метод / путь | Запрос | Ответ / ошибки |
|---|---|---|
| `GET /` | — | `200` `{data:[AchievementAdminResponse]}` (без пагинации) |
| `POST /` | `AchievementCreateRequest`{`code`* str (уник.), `title`* str, `description?`, `icon_url?`, `condition_type`* (`streak_days`\|`total_amount_kopecks`\|`donations_count`), `condition_value`* int} | `201` `AchievementAdminResponse`; `409 CONFLICT/details.code=ACHIEVEMENT_CODE_EXISTS` |
| `PATCH /{achievement_id}` | `AchievementUpdateRequest` (все опц., +`is_active?`) | `200`; `404`; `409 CONFLICT/details.code=ACHIEVEMENT_CODE_EXISTS` |

**`AchievementAdminResponse`:** `id`, `code`, `title`, `description?`, `icon_url?`, `condition_type`, `condition_value`, `is_active`, `created_at`.

### 6.9 Логи (`/api/v1/admin/logs`)

| Метод / путь | Query | Ответ |
|---|---|---|
| `GET /allocation-logs` | `subscription_id?`, `reason?`(enum AllocationChangeReason), `limit`, `cursor` | `200` список `AllocationLogResponse`{`id`,`subscription_id`,`from_campaign_id?`,`from_campaign_title?`,`to_campaign_id?`,`to_campaign_title?`,`reason`,`notified_at?`,`created_at`} |
| `GET /notification-logs` | `user_id?`, `notification_type?`, `status?`(`sent`\|`mock`\|`failed`), `limit`, `cursor` | `200` список `NotificationLogResponse`{`id`,`user_id?`,`push_token?`,`notification_type`,`title`,`body`,`data?`,`status`,`provider_response?`,`created_at`} |

### 6.10 Админы (`/api/v1/admin/admins`)

| Метод / путь | Path/Query | Запрос | Ответ / ошибки |
|---|---|---|---|
| `GET /` | query: `is_active?` bool, `limit`, `cursor` | — | `200` список `AdminResponse`{`id`,`email`,`name?`,`is_active`,`created_at`,`updated_at`} |
| `POST /` | — | `AdminCreateRequest`{`email`* EmailStr, `password`* str, `name?`} | `201` `AdminResponse`; `409 CONFLICT/details.code=ADMIN_EMAIL_EXISTS` |
| `GET /{admin_id}` | path | — | `200` `AdminResponse`; `404` |
| `PATCH /{admin_id}` | path | `AdminUpdateRequest`{`name?`, `email?`, `password?`} | `200`; `404`; `409 CONFLICT/details.code=ADMIN_EMAIL_EXISTS` |
| `POST /{admin_id}/deactivate` | path | — | `200` `{id, is_active:false}`; `403 FORBIDDEN` (нельзя себя); `404`. Побочное: отзыв всех refresh-токенов |
| `POST /{admin_id}/activate` | path | — | `200` `{id, is_active:true}`; `404` |

### 6.11 Публичные документы (`/api/v1/admin/documents`)

| Метод / путь | Path/Query | Запрос | Ответ / ошибки |
|---|---|---|---|
| `GET /` | query: `status?`(`draft`\|`published`\|`archived`), `search`, `limit`, `cursor` | — | `200` список `DocumentAdminResponse`; `422 INVALID_STATUS` |
| `POST /` | — | `DocumentCreate` | `201` `DocumentAdminResponse`; `409 CONFLICT/details.code=SLUG_ALREADY_EXISTS`; `422 INVALID_STATUS` |
| `GET /{document_id}` | path | — | `200`; `404` |
| `PATCH /{document_id}` | path | `DocumentUpdate` (+`version`* int) | `200`; `404`; `409 CONFLICT/details.code=VERSION_CONFLICT` (+`details.current_version`) или `=SLUG_ALREADY_EXISTS`; `422 INVALID_STATUS` |
| `DELETE /{document_id}` | path | — | `204` (soft-delete); `404` |
| `POST /{document_id}/publish` | path | — | `200` (status→published, `published_at`, version++) ; `404` |
| `POST /{document_id}/unpublish` | path | — | `200` (status→draft, version++); `404` |
| `POST /{document_id}/file` | multipart | form: `file`* (PDF/DOC/XLS/PPT/TXT/CSV, ≤50 МБ) | `200`; `404`; `422 INVALID_FILE_FORMAT`/`FILE_TOO_LARGE` |
| `DELETE /{document_id}/file` | path | — | `200` (очистить `file_url`); `404`; `422 NO_FILE` |

**`DocumentCreate`:** `title`* (1–255), `slug`* (2–255, уник.), `excerpt?` (≤500), `content?`, `status`(деф.`draft`),
`document_version?` (≤50), `document_date?` date, `sort_order` int (деф.0).
**`DocumentUpdate`** (все опц. + `version`* для оптимистичной блокировки): те же поля.
**`DocumentAdminResponse`:** `id`, `title`, `slug`, `excerpt?`, `content?`, `status`, `document_version?`,
`document_date?`, `published_at?`, `file_url?`, `sort_order`, `version`, `created_at`, `updated_at`.
**Оптимистичная блокировка:** в `PATCH` обязателен `version` из последнего `GET`; несовпадение → `409`
с `error.code="CONFLICT"`, `error.details.code="VERSION_CONFLICT"` и `error.details.current_version`
(актуальная версия); при успехе сервер инкрементит `version`.

### 6.12 Способы оплаты — обслуживание (`/api/v1/admin/payment-methods`)

| Метод / путь | Ответ |
|---|---|
| `POST /backfill-fingerprints` | `200` `{scanned, filled, failed, failed_items[]}` — дозаполнить `card_fingerprint` по данным ЮKassa (идемпотентно) |
| `POST /dedupe` | `200` `{soft_deleted, affected_users}` — схлопнуть дубли карт по `(user_id, card_fingerprint)`, оставить новейшую, гарантировать один `is_default` на юзера |

---

# ЧАСТЬ C. Сквозные процессы и справочник

> Относится к обеим частям: фоновые задачи, справочник констант/ошибок, нефункциональные
> требования и открытые вопросы.

---

## 7. Фоновые задачи (cron)

Taskiq + Redis. Планировщик: `taskiq scheduler app.tasks.scheduler:scheduler`.

| Задача | Cron | Что делает |
|--------|------|-----------|
| `process_recurring_billing` | `*/30 * * * *` | Списания по `active`-подпискам с наступившим `next_billing_at`. |
| `retry_failed_transactions` | `0 */6 * * *` | Повтор неудачных транзакций по расписанию `(1,3,7,14)` дней. |
| `reconcile_pending_donations` | `*/5 * * * *` | Сверка `pending`-донатов с ЮKassa (батч 100; старше 24 ч → failed). |
| `cleanup_otp_codes` | `0 * * * *` | Удаление OTP старше 1 ч. |
| `expire_patron_links` | `15 * * * *` | `pending`-ссылки с истёкшим сроком → `expired`. |
| `send_donation_reminders` | `5 * * * *` | Напоминания донорам после окончания кулдауна (если включено). |
| `auto_close_expired_campaigns` | `0 0 * * *` | Авто-закрытие сборов с истёкшим `ends_at` (не permanent) → `completed`. |
| `send_streak_pushes` | `*/15 * * * *` | Пуши по «стрикам» (до 500 юзеров за прогон; пересчёт `next_streak_push_at` на 12:00 след. дня в таймзоне юзера). |
| `cleanup_refresh_tokens` | `30 3 * * *` | Удаление refresh-токенов, истёкших >7 дней назад. |
| `cleanup_notification_logs` | `0 4 * * *` | Удаление логов пушей старше 90 дней. |
| `cleanup_thanks_content_shown` | `0 4 * * 0` | Чистка `thanks_content_shown` старше 90 дней (еженедельно). |
| `cleanup_inactive_anonymous_users` | `30 4 * * *` | Зачистка анонимов, неактивных 180 дней (отмена подписок, soft/hard-delete). |
| `reconcile_collected_amount` | `0 5 * * *` | Сверка+коррекция `campaigns.collected_amount` к источнику истины. |
| `reconcile_donors_count` | `5 5 * * *` | Сверка+коррекция `campaigns.donors_count`. |
| `reconcile_user_impact` | `10 5 * * *` | Сверка+коррекция агрегатов пользователей. |

> Задачи реконсиляции (`reconcile_*_amount/count/impact`) логируют каждое расхождение **и
> авто-корректируют** кэш-счётчик к фактической сумме/количеству по успешным донатам/транзакциям
> (исправлено в ветке `fix/spec-gaps`, см. §9.1).

---

## 8. Справочник

### 8.1 Константы (`app/domain/constants.py`)

| Константа | Значение | Смысл |
|-----------|----------|-------|
| `PLATFORM_FEE_PERCENT` | 15 | Комиссия платформы, % |
| `MIN_DONATION_AMOUNT_KOPECKS` | 1000 | Мин. разовый донат (10 ₽) |
| `ALLOWED_SUBSCRIPTION_AMOUNTS` | {100, 300, 500, 1000} | Допустимые суммы подписки, коп./день |
| `BILLING_PERIOD_MULTIPLIER` | weekly=7, monthly=30 | Множитель периода списания |
| `MAX_ACTIVE_SUBSCRIPTIONS` | 5 | Лимит активных подписок на юзера |
| `OTP_TTL_MINUTES` | 10 | Срок жизни OTP |
| `OTP_MAX_ATTEMPTS` | 5 | Попыток ввода OTP |
| `OTP_RATE_LIMIT_SECONDS` | 60 | Окно rate-limit отправки OTP (≤5/окно) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15 | TTL access-токена |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 30 | TTL refresh (зарегистрированный) |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS_ANONYMOUS` | 180 | TTL refresh (анонимный) |
| `DONATION_COOLDOWN_HOURS` | 8 | Кулдаун повторного доната в сбор |
| `PATRON_LINK_TTL_HOURS` | 24 | Срок жизни патрон-ссылки |
| `SOFT_DECLINE_RETRY_DAYS` | (1, 3, 7, 14) | Расписание ретраев списаний |
| `ANONYMOUS_INACTIVE_DAYS` | 180 | Порог зачистки анонимов |
| `LAST_SEEN_THROTTLE_MINUTES` | 15 | Троттлинг обновления `last_seen_at` |
| Лимиты медиа | video 500 МБ / doc 10 МБ / audio 50 МБ / image 20 МБ | Загрузка файлов |

### 8.2 Сводка кодов ошибок (бизнес)

| `error.code` | HTTP | Домен |
|---|---|---|
| `AUTH_REQUIRED` | 401 | донат без токена |
| `USER_NOT_FOUND` | 401 | привязка email |
| `INVALID_REFRESH_TOKEN` / `REPLAY_ATTACK_DETECTED` | 401 | refresh |
| `OTP_RATE_LIMIT` | 422 | отправка OTP |
| `OTP_EXPIRED` / `OTP_INVALID` / `OTP_MAX_ATTEMPTS` | 422 | проверка OTP |
| `EMAIL_ALREADY_LINKED` / `MERGE_NOT_ALLOWED` | 422 | привязка email |
| `DONATION_COOLDOWN` | 429 | донат |
| `MIN_DONATION_AMOUNT` | 422 | донат |
| `CAMPAIGN_NOT_ACTIVE` | 422 | донат / подписка / патрон-ссылка |
| `INVALID_AMOUNT` | 400 | подписка |
| `VALIDATION_ERROR` | 422 | подписка (стратегия) |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | 422 | подписка |
| `SUBSCRIPTION_NOT_ACTIVE` | 422 | пауза/возобновление |
| `SUBSCRIPTION_ALREADY_ACTIVE` | 422 | bind-card |
| `PM_NO_FINGERPRINT` | 422 | восстановление аккаунта |
| `REFUND_NOT_ALLOWED` / `REFUND_NO_PAYMENT` | 422 | возврат (админ) |
| `FILE_TOO_LARGE` / `INVALID_FILE_FORMAT` | 422 | загрузка медиа |
| `INVALID_MEDIA_ASSET_TYPE` | 422 | привязка медиа |
| `VERSION_CONFLICT` | 409 | админ-документы (optimistic lock) |
| `NOT_FOUND` / `CONFLICT` / `FORBIDDEN` | 404 / 409 / 403 | общие |

---

## 9. Нефункциональные требования и открытые вопросы

**Нефункциональные (как реализовано):**
- Идемпотентность всех платёжных операций (uuid7 + unique-индексы) — защита от двойных списаний.
- Двойная гарантия подтверждения платежа: вебхук + крон-реконсиляция.
- Безопасность: JWT RS256, refresh с ротацией и детектом replay, argon2 для OTP/паролей, sha256 для
  хранения refresh, IP-allowlist вебхуков ЮKassa.
- Приватность: анонимизация PII при удалении (ФЗ-152), зачистка неактивных анонимов.
- Денормализованные счётчики (`collected_amount`, `donors_count`, агрегаты юзера) с ночной сверкой.

### 9.1 Исправлено в ветке `fix/spec-gaps`

| # | Что было | Что сделано |
|---|----------|-------------|
| 1 | Патрон-ссылки не создавали реальный платёж (заглушка) → донаты висли `pending` | `patron.py` создаёт платёж ЮKassa (`type=patron_link`), заполняет `provider_payment_id`/`payment_url`; подтверждение по вебхуку, реконсиляция работает |
| 2 | Админский JWT не изолирован (`# TODO`), та же audience что у юзеров | Введена отдельная audience `JWT_ADMIN_AUDIENCE=porubly-admin`; `require_admin` проверяет её + `type=access` + `role`. Юзерский токен на админ-ручках отклоняется на уровне подписи/audience, и наоборот |
| 3 | Возвраты (`refunded`) только в enum, без флоу | Добавлены: `yookassa.create_refund`, `reverse_successful_payment` (откат счётчиков), вебхук `refund.succeeded`, админ-ручка `POST /admin/donations/{id}/refund` |
| 4 | Реконсиляция только логировала расхождения | `reconcile_*` теперь авто-корректируют кэш-счётчики к источнику истины (с логированием каждой коррекции) |
| 5 | **Пуловые подписки не аллоцировались при списании** (`campaign_id=NULL` → деньги списаны, но не привязаны к сбору; импакт/стрик не росли). `skipped` не создавался | `billing.py:_charge_subscription` и `subscription.py:bind_card` резолвят целевой сбор через `find_campaign_for_subscription`. Нет активных сборов → `Transaction(status=skipped, skipped_reason=no_active_campaigns)` без списания + `mark_streak_no_campaigns` + сдвиг `next_billing_at`. Покрыто тестом `test_billing_allocation.py` |
| 6 | **`GET /admin/users` (и карточка/действия) падал 500 для анонимов** — `email: str` обязателен, а у анонимных пользователей (дефолт) `email=NULL`. В анонимо-первом приложении список пользователей в админке падал почти всегда | `schemas/user.py`: `email` сделан опциональным в `AdminUserListItem`, `UserRoleResponse`, `UserActiveResponse` (`str | None = None`). Проверено пробером всех читаемых ручек |
| 7 | **`GET /admin/logs/notification-logs` падал 500** — `NotificationLogResponse.provider_response: str`, а `send_push` всегда пишет dict | `schemas/notification.py`: `provider_response: dict | None` |

> Все правки покрыты прогоном тестов (**324 passed**) и дымовым пробером всех читаемых эндпоинтов
> (45 ручек — **0 ответов 5xx**). Изменения в `core/security.py`, `core/config.py`,
> `services/{auth,patron,yookassa,payment,webhook,refund,subscription,allocation}.py`,
> `schemas/{user,notification}.py`, `tasks/{reconciliation,billing}.py`,
> `api/v1/admin/{__init__,donations}.py`, `tests/conftest.py`, `tests/integration/test_billing_allocation.py`.

### 9.2 Решения для заказчика (⚠️ зафиксировать)

1. **Acquiring fee = 0** — комиссия эквайринга сейчас не вычитается из суммы фонду. Это финальное правило
   распределения денег или эквайринг должен ложиться на фонд/донора?
2. **CORS открыт для всех origin** — для прод-окружения ограничить список доменов?
3. **Подпись вебхука ЮKassa не проверяется** — доверие основано только на IP-allowlist (отключается в `DEBUG`).
   Нужна ли дополнительная проверка (HMAC/подпись), особенно если IP-фильтр может обходиться за прокси/CDN?
4. **Часть списочных ручек без пагинации** возвращают полный список (`GET /foundations`,
   `GET /subscriptions`, `GET /impact/achievements`, `GET /thanks/unseen`). Для пользователя объёмы малы
   (подписок ≤5), но `foundations` — публичный и потенциально растущий: ввести пагинацию на будущее?
5. **Поле `email` в донате помечено как deprecated** в коде — подтвердить, что чек/квитанция уходит по
   данным аккаунта, а не по этому полю.

---

*Документ сгенерирован на основе фактического кода `fondback/backend`. При изменениях в коде —
обновлять соответствующие разделы.*
