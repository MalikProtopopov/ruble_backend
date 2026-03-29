# API «По Рублю» — Публичная часть (Guest / Donor / Patron)

> **Base URL:** `/api/v1`
> **Все суммы** — в копейках (integer). **Все даты** — ISO 8601 UTC.
> **Аутентификация** — `Authorization: Bearer <access_token>` (JWT RS256, TTL 15 мин).

---

## 0. Общие стандарты

### 0.1 Формат ошибки (единый для всего API)

Все ошибки возвращаются в формате:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Человекочитаемое описание",
    "details": {}
  }
}
```

### 0.2 Стандартные HTTP-коды

| Код | Когда |
|-----|-------|
| 200 | Успешный GET / PATCH |
| 201 | Успешный POST (создание ресурса) |
| 204 | Успешный DELETE |
| 400 | Ошибка валидации (неправильный формат, отсутствует поле) |
| 401 | Не авторизован (нет токена, истёк, невалидный) |
| 403 | Нет прав (роль не совпадает) |
| 404 | Ресурс не найден |
| 409 | Конфликт (дублирование) |
| 422 | Ошибка бизнес-логики |
| 429 | Превышен rate limit |
| 500 | Внутренняя ошибка сервера |

### 0.3 Стандартные коды ошибок (error.code)

| Код | HTTP | Описание |
|-----|------|----------|
| `VALIDATION_ERROR` | 400 | Невалидные входные данные |
| `UNAUTHORIZED` | 401 | Токен отсутствует, истёк или невалиден |
| `TOKEN_EXPIRED` | 401 | Access token истёк |
| `INVALID_REFRESH_TOKEN` | 401 | Refresh token использован, отозван или истёк |
| `REPLAY_ATTACK_DETECTED` | 401 | Повторное использование refresh token — все сессии отозваны |
| `FORBIDDEN` | 403 | Нет прав доступа |
| `PATRON_REQUIRED` | 403 | Требуется роль patron |
| `NOT_FOUND` | 404 | Ресурс не найден |
| `CONFLICT` | 409 | Конфликт данных |
| `OTP_EXPIRED` | 422 | OTP код истёк |
| `OTP_MAX_ATTEMPTS` | 422 | Превышено число попыток ввода OTP |
| `OTP_INVALID` | 422 | Неверный OTP код |
| `OTP_ALREADY_USED` | 422 | OTP код уже использован |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | 422 | Превышен лимит подписок (макс. 5) |
| `CAMPAIGN_NOT_ACTIVE` | 422 | Кампания не активна |
| `MIN_DONATION_AMOUNT` | 422 | Сумма доната ниже минимума (1000 коп = 10 руб) |
| `INVALID_AMOUNT` | 422 | Недопустимая сумма подписки |
| `SUBSCRIPTION_NOT_ACTIVE` | 422 | Подписка не активна для данной операции |
| `RATE_LIMIT_EXCEEDED` | 429 | Превышен rate limit |
| `ACCOUNT_DEACTIVATED` | 403 | Аккаунт деактивирован администратором |
| `EMAIL_REQUIRED` | 400 | Email обязателен для неавторизованных пользователей |
| `AUTH_REQUIRED` | 401 | Требуется авторизация (пользователь с таким email уже существует) |
| `SUBSCRIPTION_ALREADY_ACTIVE` | 422 | Карта уже привязана к подписке |
| `DUPLICATE_OFFLINE_PAYMENT` | 409 | Офлайн-платёж с такими реквизитами уже записан |
| `INTERNAL_ERROR` | 500 | Внутренняя ошибка |

### 0.4 Пагинация (cursor-based)

Все list-эндпоинты используют cursor-based пагинацию:

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | Количество записей (1–100) |
| `cursor` | string | null | Base64-encoded cursor для следующей страницы |

**Формат ответа:**

```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6IjE0MyJ9",
    "has_more": true,
    "total": null
  }
}
```

### 0.5 Rate Limiting

| Endpoint | Лимит |
|----------|-------|
| `POST /auth/send-otp` | 3 запроса / 10 мин / IP |
| `POST /auth/verify-otp` | 5 попыток / 15 мин / email |
| `POST /subscriptions` | 10 запросов / час / user |
| Все остальные | 100 запросов / мин / user |

При превышении: `429` + заголовок `Retry-After: {seconds}`.

### 0.6 Push Notification Data Payloads

Все push-уведомления содержат JSON-payload в поле `data`:

| type | Поля | Описание |
|------|------|----------|
| `payment_success` | `type`, `transaction_id` | Успешное списание по подписке |
| `donation_success` | `type`, `donation_id` | Успешный разовый донат |
| `thanks_content` | `type`, `thanks_content_id`, `campaign_id`, `campaign_title` | Благодарность от фонда |
| `campaign_changed` | `type`, `subscription_id`, `new_campaign_id`, `new_campaign_title` | Смена кампании в подписке |
| `achievement_earned` | `type`, `achievement_id`, `achievement_code`, `achievement_title` | Получено достижение |
| `payment_failed_soft` | `type`, `subscription_id` | Мягкий сбой оплаты (будет retry) |
| `payment_failed_hard` | `type`, `subscription_id` | Жёсткий сбой оплаты (подписка приостановлена) |
| `campaign_completed` | `type`, `campaign_id`, `campaign_title`, `closed_early` | Кампания завершена |
| `streak_reminder` | `type`, `current_streak_days` | Напоминание о стрике |

---

## 1. Аутентификация

### 1.1 POST `/auth/send-otp` — Запросить OTP код на email

**Требование:** AUTH-01
**Роль:** Guest
**Rate limit:** 3 запроса / 10 мин / IP

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `email` | string (email) | required | Email пользователя |

```json
{ "email": "user@example.com" }
```

**Ответ 200:**

```json
{
  "message": "OTP код отправлен",
  "expires_in_seconds": 600
}
```

**Ошибки:** `400` VALIDATION_ERROR, `403` ACCOUNT_DEACTIVATED (если пользователь с таким email существует и `is_active = false` — OTP не отправляется), `429` RATE_LIMIT_EXCEEDED

---

### 1.2 POST `/auth/verify-otp` — Верификация OTP, получение JWT

**Требование:** AUTH-02
**Роль:** Guest
**Rate limit:** 5 попыток / 15 мин / email

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `email` | string (email) | required | Email |
| `code` | string | required | 6-значный OTP код |

```json
{ "email": "user@example.com", "code": "123456" }
```

**Ответ 200:**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": null,
    "role": "donor",
    "is_new": true
  }
}
```

`is_new: true` — если пользователь создан при первой авторизации.

**Ошибки:** `403` ACCOUNT_DEACTIVATED (см. ниже), `422` OTP_EXPIRED / OTP_MAX_ATTEMPTS / OTP_INVALID / OTP_ALREADY_USED, `429` RATE_LIMIT_EXCEEDED

**Проверка is_active:** Если `User.is_active = false` — возвращать `403 ACCOUNT_DEACTIVATED` с сообщением «Ваш аккаунт деактивирован. Обратитесь в поддержку.» Пользователь не получает JWT.

---

### 1.3 POST `/auth/refresh` — Обновить access-токен

**Требование:** AUTH-03
**Роль:** Donor

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `refresh_token` | string | required | Текущий refresh token |

```json
{ "refresh_token": "eyJ..." }
```

**Ответ 200:**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

Старый refresh-токен инвалидируется (rotation). Повторное использование → `REPLAY_ATTACK_DETECTED`, все сессии отозваны.

**Ошибки:** `401` INVALID_REFRESH_TOKEN / REPLAY_ATTACK_DETECTED

---

### 1.4 POST `/auth/logout` — Выход

**Требование:** AUTH-04
**Роль:** Donor (JWT)

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `refresh_token` | string | required | Текущий refresh token для отзыва |

```json
{ "refresh_token": "eyJ..." }
```

**Ответ 204:** No Content

**Ошибки:** `401` UNAUTHORIZED

---

## 2. Профиль пользователя

### 2.1 GET `/me` — Получить профиль

**Роль:** Donor (JWT)

**Ответ 200:**

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "phone": "+79001234567",
  "name": "Иван",
  "avatar_url": "https://...",
  "role": "donor",
  "timezone": "Europe/Moscow",
  "notification_preferences": {
    "push_on_payment": true,
    "push_on_campaign_change": true,
    "push_daily_streak": false,
    "push_campaign_completed": true
  },
  "created_at": "2026-01-15T10:00:00Z"
}
```

---

### 2.2 PATCH `/me` — Обновить профиль

**Роль:** Donor (JWT)

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `name` | string(100) | optional | Имя |
| `phone` | string(20) | optional | Телефон E.164 |
| `avatar_url` | string | optional | URL аватара |
| `timezone` | string(50) | optional | IANA timezone |
| `push_token` | string | optional | FCM/APNs токен |
| `push_platform` | string | optional | `fcm` или `apns` |

```json
{ "name": "Иван", "timezone": "Europe/Moscow" }
```

**Ответ 200:** Полный объект профиля (как GET `/me`)

---

### 2.3 PATCH `/me/notifications` — Настройки уведомлений

**Требование:** NOTIF-09
**Роль:** Donor (JWT)

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `push_on_payment` | boolean | optional | Push при списании |
| `push_on_campaign_change` | boolean | optional | Push при смене кампании |
| `push_daily_streak` | boolean | optional | Ежедневный push стрика |
| `push_campaign_completed` | boolean | optional | Push при закрытии кампании |

```json
{ "push_daily_streak": true }
```

**Ответ 200:**

```json
{
  "push_on_payment": true,
  "push_on_campaign_change": true,
  "push_daily_streak": true,
  "push_campaign_completed": true
}
```

---

### 2.4 DELETE `/me` — Анонимизация аккаунта

**Требование:** ФЗ-152
**Роль:** Donor (JWT)

Анонимизирует персональные данные. Транзакции сохраняются. Подписки отменяются.

**Ответ 204:** No Content

---

## 3. Кампании (публичные)

### 3.1 GET `/campaigns` — Лента активных кампаний

**Требование:** CAMP-01
**Роль:** Guest / Donor

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор пагинации |

**Сортировка:** `urgency_level DESC`, `(collected_amount / goal_amount) DESC`, `sort_order ASC`

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "foundation_id": "uuid",
      "foundation": {
        "id": "uuid",
        "name": "Фонд помощи",
        "logo_url": "https://..."
      },
      "title": "Помощь детям",
      "description": "...",
      "thumbnail_url": "https://...",
      "status": "active",
      "goal_amount": 10000000,
      "collected_amount": 4500000,
      "donors_count": 128,
      "urgency_level": 5,
      "is_permanent": false,
      "ends_at": "2026-06-01T00:00:00Z",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJ...",
    "has_more": true,
    "total": null
  }
}
```

---

### 3.2 GET `/campaigns/{id}` — Деталь кампании

**Требование:** CAMP-02
**Роль:** Guest / Donor

**Ответ 200:**

```json
{
  "id": "uuid",
  "foundation_id": "uuid",
  "foundation": {
    "id": "uuid",
    "name": "Фонд помощи",
    "logo_url": "https://...",
    "website_url": "https://..."
  },
  "title": "Помощь детям",
  "description": "Подробное описание...",
  "video_url": "https://...",
  "thumbnail_url": "https://...",
  "status": "active",
  "goal_amount": 10000000,
  "collected_amount": 4500000,
  "donors_count": 128,
  "urgency_level": 5,
  "is_permanent": false,
  "closed_early": false,
  "close_note": null,
  "ends_at": "2026-06-01T00:00:00Z",
  "documents": [
    { "id": "uuid", "title": "Отчёт", "file_url": "https://...", "sort_order": 0 }
  ],
  "thanks_contents": [
    { "id": "uuid", "type": "video", "media_url": "https://...", "title": "Спасибо!", "description": null }
  ],
  "created_at": "2026-01-01T00:00:00Z"
}
```

Если `closed_early = true` — отображается `close_note`.

**Ошибки:** `404` NOT_FOUND

---

### 3.3 GET `/campaigns/{id}/documents` — Документы кампании

**Требование:** CAMP-03
**Роль:** Guest / Donor

**Ответ 200:**

```json
{
  "data": [
    { "id": "uuid", "title": "Отчёт", "file_url": "https://...", "sort_order": 0 }
  ]
}
```

---

### 3.4 GET `/campaigns/{id}/share` — Deeplink для шеринга

**Требование:** CAMP-05
**Роль:** Donor (JWT)

**Ответ 200:**

```json
{
  "share_url": "https://porubly.ru/campaigns/uuid",
  "title": "Помощь детям",
  "description": "Собрано 45 000 ₽ из 100 000 ₽"
}
```

---

### 3.5 GET `/foundations/{id}` — Страница фонда

**Требование:** CAMP-04
**Роль:** Guest / Donor

INN и legal_name **не показываются** публично.

**Ответ 200:**

```json
{
  "id": "uuid",
  "name": "Фонд помощи",
  "description": "Описание фонда...",
  "logo_url": "https://...",
  "website_url": "https://fond.ru",
  "status": "active"
}
```

**Ошибки:** `404` NOT_FOUND

---

## 4. Разовые донаты

### 4.1 POST `/donations` — Создать разовый донат

**Требование:** DON-01
**Роль:** Donor (JWT) / Guest (с email)

**Логика авторизации при оплате:**
1. Если запрос содержит `Authorization: Bearer <token>` — донат привязывается к авторизованному пользователю.
2. Если Bearer-токена нет — поле `email` в теле запроса **обязательно**:
   - Система ищет пользователя по `email` в базе.
   - Если пользователь **найден** и `is_active = true` — возвращается `401 AUTH_REQUIRED` с `{"error": {"code": "AUTH_REQUIRED", "message": "Пользователь с таким email уже зарегистрирован. Пожалуйста, авторизуйтесь.", "details": {"email": "user@example.com"}}}`. Клиент перенаправляет на OTP-авторизацию.
   - Если пользователь **найден** и `is_active = false` — возвращается `403 ACCOUNT_DEACTIVATED`.
   - Если пользователь **не найден** — система автоматически создаёт нового пользователя с `role=donor`, `is_new=true`, создаёт донат и возвращает `payment_url`. После успешной оплаты (webhook) отправляется OTP на email для активации аккаунта.

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `campaign_id` | uuid | required | ID кампании |
| `amount_kopecks` | integer | required | Сумма в копейках (>= 1000 для source=app) |
| `email` | string (email) | conditional | Обязателен если нет Bearer-токена |

```json
{ "campaign_id": "uuid", "amount_kopecks": 50000 }
```

**Ответ 201:**

```json
{
  "id": "uuid",
  "campaign_id": "uuid",
  "amount_kopecks": 50000,
  "status": "pending",
  "source": "app",
  "payment_url": "https://yookassa.ru/pay/...",
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Ошибки:** `422` MIN_DONATION_AMOUNT / CAMPAIGN_NOT_ACTIVE, `401` AUTH_REQUIRED, `403` ACCOUNT_DEACTIVATED, `400` EMAIL_REQUIRED, `404` NOT_FOUND

---

### 4.2 GET `/donations` — История разовых донатов

**Требование:** DON-03
**Роль:** Donor (JWT)

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `status` | string | null | Фильтр: `pending`, `success`, `failed`, `refunded` |
| `campaign_id` | uuid | null | Фильтр по кампании |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "campaign_id": "uuid",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 50000,
      "status": "success",
      "source": "app",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 4.3 GET `/donations/{id}` — Деталь доната

**Роль:** Donor (JWT)

**Ответ 200:**

```json
{
  "id": "uuid",
  "campaign_id": "uuid",
  "campaign_title": "Помощь детям",
  "foundation_id": "uuid",
  "foundation_name": "Фонд помощи",
  "amount_kopecks": 50000,
  "status": "success",
  "source": "app",
  "payment_url": "https://...",
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Ошибки:** `404` NOT_FOUND

---

## 5. Подписки

> **Важно: суммы подписки и списания.** Поле `amount_kopecks` при создании подписки — это **дневная ставка**. Фактическая сумма списания рассчитывается как:
> - `weekly`: `amount_kopecks × 7` (например, 300 коп/день → 2 100 коп/неделю = 21 ₽)
> - `monthly`: `amount_kopecks × 30` (например, 300 коп/день → 9 000 коп/месяц = 90 ₽)
>
> В ответах подписки `amount_kopecks` — дневная ставка. В транзакциях `amount_kopecks` — фактическая сумма списания.

### 5.1 POST `/subscriptions` — Создать подписку

**Требование:** SUB-01
**Роль:** Donor (JWT)
**Rate limit:** 10 запросов / час / user

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `amount_kopecks` | integer | required | Только: 100, 300, 500 или 1000 |
| `billing_period` | string | required | `weekly` или `monthly` |
| `allocation_strategy` | string | required | `platform_pool`, `foundation_pool`, `specific_campaign` |
| `campaign_id` | uuid | optional | Обязателен при `specific_campaign` |
| `foundation_id` | uuid | optional | Обязателен при `foundation_pool` |

```json
{
  "amount_kopecks": 300,
  "billing_period": "monthly",
  "allocation_strategy": "platform_pool"
}
```

**Ответ 201:**

```json
{
  "id": "uuid",
  "amount_kopecks": 300,
  "billing_period": "monthly",
  "allocation_strategy": "platform_pool",
  "campaign_id": null,
  "foundation_id": null,
  "status": "pending_payment_method",
  "next_billing_at": null,
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Ошибки:** `422` SUBSCRIPTION_LIMIT_EXCEEDED / INVALID_AMOUNT / CAMPAIGN_NOT_ACTIVE, `404` NOT_FOUND

---

### 5.2 GET `/subscriptions` — Список подписок

**Требование:** SUB-03
**Роль:** Donor (JWT)

Возвращает active, paused, pending_payment_method. Не возвращает cancelled.

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "amount_kopecks": 300,
      "billing_period": "monthly",
      "allocation_strategy": "platform_pool",
      "campaign_id": null,
      "campaign_title": null,
      "foundation_id": null,
      "foundation_name": null,
      "status": "active",
      "paused_reason": null,
      "paused_at": null,
      "next_billing_at": "2026-04-28T12:00:00Z",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ]
}
```

---

### 5.3 PATCH `/subscriptions/{id}` — Изменить подписку

**Требование:** SUB-04
**Роль:** Donor (JWT)

Изменение суммы применяется с **следующего** биллинга.

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `amount_kopecks` | integer | optional | 100, 300, 500 или 1000 |
| `allocation_strategy` | string | optional | `platform_pool`, `foundation_pool`, `specific_campaign` |
| `campaign_id` | uuid | optional | Для `specific_campaign` |
| `foundation_id` | uuid | optional | Для `foundation_pool` |

**Ответ 200:** Полный объект подписки

**Ошибки:** `422` INVALID_AMOUNT / CAMPAIGN_NOT_ACTIVE, `404` NOT_FOUND

---

### 5.4 POST `/subscriptions/{id}/pause` — Пауза подписки

**Требование:** SUB-05
**Роль:** Donor (JWT)

`paused_reason = user_request`, `next_billing_at = null`.

**Ответ 200:** Полный объект подписки (status=paused)

**Ошибки:** `422` SUBSCRIPTION_NOT_ACTIVE, `404` NOT_FOUND

---

### 5.5 POST `/subscriptions/{id}/resume` — Возобновить подписку

**Требование:** SUB-06
**Роль:** Donor (JWT)

`status = active`, `next_billing_at = now + period`.

**Ответ 200:** Полный объект подписки (status=active)

**Ошибки:** `422` SUBSCRIPTION_NOT_ACTIVE, `404` NOT_FOUND

---

### 5.6 DELETE `/subscriptions/{id}` — Отменить подписку

**Требование:** SUB-07
**Роль:** Donor (JWT)

Отмена в один клик (обязательно по закону). `status=cancelled`, `cancelled_at=now`.

**Ответ 204:** No Content

**Ошибки:** `404` NOT_FOUND

---

### 5.7 POST `/subscriptions/{id}/bind-card` — Привязать карту (первый платёж)

**Требование:** SUB-02
**Роль:** Donor (JWT)

Инициирует первый платёж через ЮKassa с `save_payment_method=true` и обязательной 3DS-аутентификацией. При успешной оплате:
- Токен платёжного метода сохраняется в `subscription.payment_method_id`
- Статус подписки меняется: `pending_payment_method → active`
- Устанавливается `next_billing_at = now + billing_period`
- Создаётся первая Transaction со статусом `pending`

**Ответ 201:**

```json
{
  "payment_url": "https://yookassa.ru/pay/...",
  "confirmation_type": "redirect",
  "subscription_id": "uuid",
  "amount_kopecks": 2100,
  "description": "Подписка «По Рублю» — 3₽/день (еженедельно)"
}
```

`amount_kopecks` — фактическая сумма первого списания (дневная ставка × множитель периода).

**Ошибки:** `404` NOT_FOUND, `422` SUBSCRIPTION_ALREADY_ACTIVE

---

## 6. Транзакции (рекуррентные платежи)

### 6.1 GET `/transactions` — История транзакций

**Требование:** SUB-08
**Роль:** Donor (JWT)

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `status` | string | null | Фильтр: `pending`, `success`, `failed`, `skipped`, `refunded` |
| `campaign_id` | uuid | null | Фильтр по кампании |
| `subscription_id` | uuid | null | Фильтр по подписке |
| `date_from` | date | null | Начало периода (включительно) |
| `date_to` | date | null | Конец периода (включительно) |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "subscription_id": "uuid",
      "campaign_id": "uuid",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 9000,
      "status": "success",
      "skipped_reason": null,
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 6.2 GET `/transactions/{id}` — Деталь транзакции

**Требование:** SUB-09
**Роль:** Donor (JWT)

**Ответ 200:**

```json
{
  "id": "uuid",
  "subscription_id": "uuid",
  "campaign_id": "uuid",
  "campaign_title": "Помощь детям",
  "foundation_id": "uuid",
  "foundation_name": "Фонд помощи",
  "amount_kopecks": 9000,
  "platform_fee_kopecks": 1350,
  "nco_amount_kopecks": 7650,
  "status": "success",
  "skipped_reason": null,
  "cancellation_reason": null,
  "attempt_number": 1,
  "created_at": "2026-03-28T12:00:00Z"
}
```

`skipped_reason: null | "no_active_campaigns"` — означает, что в момент биллинга не было ни одной активной кампании. Стрик при этом не прерывается.

**Ошибки:** `404` NOT_FOUND

---

## 7. Импакт и геймификация

### 7.1 GET `/impact` — Персональный импакт

**Требование:** IMPACT-01
**Роль:** Donor (JWT)

**Ответ 200:**

```json
{
  "total_donated_kopecks": 150000,
  "streak_days": 42,
  "donations_count": 35
}
```

---

### 7.2 GET `/impact/achievements` — Достижения пользователя

**Требование:** IMPACT-03
**Роль:** Donor (JWT)

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "code": "FIRST_DONATION",
      "title": "Первый шаг",
      "description": "Сделай первое пожертвование",
      "icon_url": "https://...",
      "earned_at": "2026-01-15T10:00:00Z"
    },
    {
      "id": "uuid",
      "code": "STREAK_30",
      "title": "30 дней подряд",
      "description": "Помогай 30 дней без перерыва",
      "icon_url": "https://...",
      "earned_at": null
    }
  ]
}
```

`earned_at: null` — ещё не получено. Возвращаются все активные ачивки.

---

## 8. Благодарности

### 8.1 GET `/thanks/{id}` — Получить благодарность

**Требование:** THANKS-02
**Роль:** Donor (JWT)

Вызывается клиентом после нажатия на push или из списка непросмотренных. Возвращает медиа-контент благодарности с контекстом кампании и вкладом пользователя. Фиксирует просмотр в `thanks_content_shown` (INSERT ON CONFLICT DO NOTHING).

Доступ к записи разрешён только если текущий пользователь есть в `campaign_donors` для `campaign_id` этой благодарности (то есть после успешного платежа по кампании). Иначе — `404 NOT_FOUND`.

**Ответ 200:**
```json
{
  "id": "uuid-v7",
  "campaign_id": "uuid-v7",
  "campaign_title": "Помощь детям",
  "foundation_id": "uuid-v7",
  "foundation_name": "Фонд помощи",
  "type": "video",
  "media_url": "https://cdn.porubly.ru/thanks/uuid.mp4",
  "title": "Спасибо за вашу поддержку!",
  "description": "Благодаря вам мы смогли помочь 15 семьям.",
  "deep_link": "porubly://thanks/uuid-v7",
  "campaign_share_url": "https://porubly.ru/campaigns/uuid-v7",
  "user_contribution": {
    "total_donated_kopecks": 45000,
    "donations_count": 15,
    "first_donation_at": "2026-01-15T10:00:00Z",
    "last_donation_at": "2026-03-20T10:00:00Z"
  }
}
```

Блок `user_contribution` — сводка по вкладу текущего пользователя в эту кампанию (сумма всех success-транзакций и донатов).

**Медиа (CDN):** прямые публичные URL без проверки прав не использовать для приватного контента. Предпочтительно: подписанные URL с коротким TTL, выдаваемые после проверки JWT и членства в `campaign_donors`, либо прокси через API.

**Ошибки:** 404 NOT_FOUND, 401 UNAUTHORIZED

---

### 8.2 GET `/thanks/unseen` — Непросмотренные благодарности

**Требование:** THANKS-03
**Роль:** Donor (JWT)

Возвращает список благодарностей, которые пользователь ещё не просмотрел (те же правила доступа, что и для GET `/thanks/{id}`: только кампании, где пользователь в `campaign_donors`). Используется клиентом при открытии приложения для показа пропущенных благодарностей. Сортировка: `created_at DESC`.

**Ответ 200:**
```json
{
  "data": [
    {
      "id": "uuid-v7",
      "campaign_id": "uuid-v7",
      "campaign_title": "Помощь детям",
      "foundation_name": "Фонд помощи",
      "type": "video",
      "media_url": "https://cdn.porubly.ru/thanks/uuid.mp4",
      "title": "Спасибо за вашу поддержку!",
      "description": "Благодаря вам мы смогли помочь 15 семьям.",
      "deep_link": "porubly://thanks/uuid-v7",
      "campaign_share_url": "https://porubly.ru/campaigns/uuid-v7",
      "user_contribution": {
        "total_donated_kopecks": 45000,
        "donations_count": 15,
        "first_donation_at": "2026-01-15T10:00:00Z",
        "last_donation_at": "2026-03-20T10:00:00Z"
      },
      "created_at": "2026-03-25T10:00:00Z"
    }
  ]
}
```

**SQL-логика:**
```sql
SELECT tc.* FROM thanks_contents tc
JOIN campaign_donors cd ON cd.campaign_id = tc.campaign_id AND cd.user_id = :user_id
LEFT JOIN thanks_content_shown tcs ON tcs.thanks_content_id = tc.id AND tcs.user_id = :user_id
WHERE tcs.id IS NULL
ORDER BY tc.created_at DESC;
```

---

## 9. Меценаты (Patron)

### 9.1 POST `/patron/payment-links` — Создать платёжную ссылку

**Требование:** PAT-01
**Роль:** Patron (JWT, role=patron)

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `campaign_id` | uuid | required | ID кампании |
| `amount_kopecks` | integer | required | Сумма |

```json
{ "campaign_id": "uuid", "amount_kopecks": 5000000 }
```

**Ответ 201:**

```json
{
  "id": "uuid",
  "campaign_id": "uuid",
  "amount_kopecks": 5000000,
  "payment_url": "https://yookassa.ru/pay/...",
  "expires_at": "2026-03-29T12:00:00Z",
  "status": "pending",
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Ошибки:** `403` PATRON_REQUIRED, `422` CAMPAIGN_NOT_ACTIVE, `404` NOT_FOUND

---

### 9.2 GET `/patron/payment-links` — Мои ссылки

**Требование:** PAT-04
**Роль:** Patron (JWT)

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `status` | string | null | `pending`, `paid`, `expired` |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "campaign_id": "uuid",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 5000000,
      "payment_url": "https://...",
      "expires_at": "2026-03-29T12:00:00Z",
      "status": "paid",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 9.3 GET `/patron/payment-links/{id}` — Деталь ссылки

**Роль:** Patron (JWT)

**Ответ 200:** Полный объект ссылки (как в списке)

**Ошибки:** `404` NOT_FOUND

---

## 10. Вебхуки

Подробности протокола ЮKassa, `metadata`, идемпотентность и переменные окружения — в [yookassa_integration.md](yookassa_integration.md).

### 10.1 POST `/webhooks/yookassa` — Вебхук ЮKassa

**Требование:** DON-02, BILL-04, BILL-05, PAT-03

Обрабатывает события: `payment.succeeded`, `payment.canceled`.

**Заголовки:** Подпись ЮKassa для верификации.

**Тело запроса:** Стандартный формат вебхука ЮKassa (определяется провайдером).

**Логика:**

| Событие | Действие |
|---------|----------|
| `payment.succeeded` (donation) | `Donation.status = success`, атомарно `collected_amount++`, `donors_count` через campaign_donors, user streak/impact |
| `payment.succeeded` (transaction) | `Transaction.status = success`, обновить счётчики, `next_billing_at += period` |
| `payment.succeeded` (patron_link) | `PatronPaymentLink.status = paid`, donation → success, обновить счётчики |
| `payment.succeeded` (любой, есть user_id) | + Проверить наличие непоказанного thanks_content для кампании и пользователя → если есть, отправить push `{type: "thanks_content", thanks_content_id, campaign_id, campaign_title}` |
| `payment.canceled` (transaction) | `Transaction.status = failed`, сохранить `cancellation_reason`, запустить retry |

**Ответ 200:** `{ "status": "ok" }`
