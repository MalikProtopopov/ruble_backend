# API «По Рублю» — Админ-панель

> **Base URL:** `/api/v1/admin`
> **Аутентификация:** `Authorization: Bearer <access_token>` (Admin JWT, email + пароль, отдельный secret).
> **Все суммы** — в копейках (integer). **Все даты** — ISO 8601 UTC.
> **Формат ошибок и пагинация** — как в публичном API (см. `api_public.md`, §0).

---

## 0. Дополнительные коды ошибок (только Admin)

| Код | HTTP | Описание |
|-----|------|----------|
| `ADMIN_AUTH_FAILED` | 401 | Неверный email или пароль |
| `FOUNDATION_NOT_FOUND` | 404 | Фонд не найден |
| `CAMPAIGN_NOT_FOUND` | 404 | Кампания не найдена |
| `USER_NOT_FOUND` | 404 | Пользователь не найден |
| `INVALID_STATUS_TRANSITION` | 422 | Недопустимый переход статуса (например, archive из draft) |
| `CAMPAIGN_ALREADY_COMPLETED` | 422 | Кампания уже завершена |
| `INN_ALREADY_EXISTS` | 409 | Фонд с таким ИНН уже существует |
| `FILE_TOO_LARGE` | 422 | Файл превышает лимит |
| `INVALID_FILE_FORMAT` | 422 | Недопустимый формат файла |
| `DUPLICATE_OFFLINE_PAYMENT` | 409 | Офлайн-платёж с такими реквизитами уже зафиксирован |
| `ADMIN_NOT_FOUND` | 404 | Администратор не найден |
| `ADMIN_EMAIL_EXISTS` | 409 | Администратор с таким email уже существует |
| `WEAK_PASSWORD` | 422 | Пароль не соответствует требованиям безопасности |
| `CANNOT_DEACTIVATE_SELF` | 422 | Нельзя деактивировать собственный аккаунт |
| `USER_ALREADY_DEACTIVATED` | 422 | Пользователь уже деактивирован |
| `USER_ALREADY_ACTIVE` | 422 | Пользователь уже активен |

---

## 1. Аутентификация админа

### 1.1 POST `/admin/auth/login` — Вход администратора

**Требование:** AUTH-05

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `email` | string (email) | required | Email админа |
| `password` | string | required | Пароль |

```json
{ "email": "admin@porubly.ru", "password": "..." }
```

**Ответ 200:**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "admin": {
    "id": "uuid",
    "email": "admin@porubly.ru",
    "name": "Администратор"
  }
}
```

**Ошибки:** `401` ADMIN_AUTH_FAILED

---

### 1.2 POST `/admin/auth/refresh` — Обновить admin access-токен

**Требование:** AUTH-06

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

Старый refresh-токен помечается is_used=true. Повторное использование → REPLAY_ATTACK_DETECTED → все admin-сессии отозваны.

**Ошибки:** 401 INVALID_REFRESH_TOKEN / REPLAY_ATTACK_DETECTED

---

### 1.3 POST `/admin/auth/logout` — Выход администратора

**Требование:** AUTH-07

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `refresh_token` | string | required | Текущий refresh token для отзыва |

```json
{ "refresh_token": "eyJ..." }
```

**Ответ 204:** No Content

**Ошибки:** 401 UNAUTHORIZED

---

## 2. Фонды (ADM-01)

### 2.1 GET `/admin/foundations` — Список фондов

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `status` | string | null | `pending_verification`, `active`, `suspended` |
| `search` | string | null | Поиск по name, legal_name, inn |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "name": "Фонд помощи",
      "legal_name": "ООО «Фонд помощи»",
      "inn": "7712345678",
      "description": "...",
      "logo_url": "https://...",
      "website_url": "https://...",
      "status": "active",
      "yookassa_shop_id": null,
      "verified_at": "2026-01-01T00:00:00Z",
      "created_at": "2025-12-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 2.2 POST `/admin/foundations` — Создать фонд

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `name` | string(255) | required | Публичное название |
| `legal_name` | string(500) | required | Юридическое название |
| `inn` | string(12) | required | ИНН |
| `description` | string | optional | Описание (до 2000 символов) |
| `logo_url` | string | optional | URL логотипа |
| `website_url` | string | optional | Официальный сайт |

```json
{
  "name": "Фонд помощи",
  "legal_name": "ООО «Фонд помощи»",
  "inn": "7712345678",
  "description": "Благотворительный фонд..."
}
```

**Ответ 201:** Полный объект фонда (как в списке, status=pending_verification)

**Ошибки:** `409` INN_ALREADY_EXISTS, `400` VALIDATION_ERROR

---

### 2.3 GET `/admin/foundations/{id}` — Деталь фонда

**Ответ 200:** Полный объект фонда

**Ошибки:** `404` FOUNDATION_NOT_FOUND

---

### 2.4 PATCH `/admin/foundations/{id}` — Обновить фонд

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `name` | string(255) | optional | |
| `legal_name` | string(500) | optional | |
| `description` | string | optional | |
| `logo_url` | string | optional | Публичный URL логотипа |
| `logo_media_asset_id` | uuid | optional | Альтернатива `logo_url`: ID из `GET /admin/media` / ответа upload; тип файла — `video` или `document`. Если указано вместе с `logo_url`, приоритет у `logo_media_asset_id`. |
| `website_url` | string | optional | |
| `status` | string | optional | `pending_verification`, `active`, `suspended` |
| `yookassa_shop_id` | string | optional | |

**Ответ 200:** Обновлённый объект фонда

**Ошибки:** `404` FOUNDATION_NOT_FOUND

---

## 3. Кампании (ADM-02, ADM-08, ADM-13, ADM-14)

### 3.1 GET `/admin/campaigns` — Список кампаний

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `status` | string | null | `draft`, `active`, `paused`, `completed`, `archived` |
| `foundation_id` | uuid | null | Фильтр по фонду |
| `search` | string | null | Поиск по title |

**Ответ 200:** Список объектов кампаний (включая все поля + foundation.name)

---

### 3.2 POST `/admin/campaigns` — Создать кампанию

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `foundation_id` | uuid | required | ID фонда |
| `title` | string(255) | required | Заголовок |
| `description` | string | optional | До 5000 символов |
| `video_url` | string | optional | URL видео |
| `thumbnail_url` | string | optional | URL превью |
| `goal_amount` | integer | optional | Целевая сумма (копейки). Null для бессрочных |
| `urgency_level` | integer | optional | 1–5, по умолчанию 3 |
| `is_permanent` | boolean | optional | По умолчанию false |
| `ends_at` | datetime | optional | Дата окончания |
| `sort_order` | integer | optional | По умолчанию 0 |

**Ответ 201:** Объект кампании (status=draft)

**Ошибки:** `404` FOUNDATION_NOT_FOUND, `400` VALIDATION_ERROR

---

### 3.3 GET `/admin/campaigns/{id}` — Деталь кампании

**Ответ 200:** Полный объект кампании + documents + thanks_contents

---

### 3.4 PATCH `/admin/campaigns/{id}` — Обновить кампанию

**Тело запроса:** Все поля из POST `/admin/campaigns` — optional.

Дополнительно:

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `urgency_level` | integer | optional | ADM-08: 1–5 |
| `sort_order` | integer | optional | ADM-08: ручная сортировка |
| `video_media_asset_id` | uuid | optional | Подставить `video_url` из библиотеки медиа; допустим только тип `video`. Если указано вместе с `video_url`, приоритет у `video_media_asset_id`. |
| `thumbnail_media_asset_id` | uuid | optional | Подставить `thumbnail_url` из библиотеки; допустимы типы `video` или `document`. Приоритет над `thumbnail_url`, если оба переданы. |

**Ответ 200:** Обновлённый объект кампании

---

### Граф переходов статуса кампании

| Текущий | → | Эндпоинт | Примечание |
|---------|---|----------|------------|
| draft | active | POST /publish | |
| active | paused | POST /pause | |
| active | completed | POST /complete | ALLOC-04 + push |
| active | completed | POST /close-early | closed_early=true |
| paused | active | PATCH (статус) | |
| completed | archived | POST /archive | |

Все прочие переходы → 422 INVALID_STATUS_TRANSITION

---

### 3.5 POST `/admin/campaigns/{id}/publish` — Опубликовать (draft → active)

**Требование:** ADM-02

**Ответ 200:** Объект кампании (status=active)

**Ошибки:** `422` INVALID_STATUS_TRANSITION

---

### 3.6 POST `/admin/campaigns/{id}/pause` — Приостановить (active → paused)

**Ответ 200:** Объект кампании (status=paused)

---

### 3.7 POST `/admin/campaigns/{id}/complete` — Завершить (active → completed)

**Ответ 200:** Объект кампании (status=completed)

Запускает ALLOC-04 для всех привязанных подписок (CLOSE-02). Push всем донорам (CLOSE-03).

---

### 3.8 POST `/admin/campaigns/{id}/archive` — Архивировать (completed → archived)

**Ответ 200:** Объект кампании (status=archived)

---

### 3.9 POST `/admin/campaigns/{id}/close-early` — Досрочное закрытие

**Требование:** CLOSE-01, ADM-13

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `close_note` | string | required | Комментарий для пользователей |

```json
{ "close_note": "Нам удалось собрать 45 000₽ из 100 000₽. Все средства переданы фонду." }
```

**Ответ 200:** Объект кампании (status=completed, closed_early=true, close_note=...)

Запускает ALLOC-04 + CLOSE-03.

**Ошибки:** `422` CAMPAIGN_ALREADY_COMPLETED

---

### 3.10 POST `/admin/campaigns/{id}/force-realloc` — Принудительное перераспределение

**Требование:** ADM-11

Запускает ALLOC-04 для всех подписок данной кампании.

**Ответ 200:**

```json
{ "reallocated_subscriptions": 15 }
```

---

### 3.11 POST `/admin/campaigns/{id}/offline-payment` — Запись офлайн-платежа

**Требование:** CLOSE-04, ADM-14

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `amount_kopecks` | integer | required | Сумма (> 0) |
| `payment_method` | string | required | `cash`, `bank_transfer`, `other` |
| `description` | string | optional | Комментарий (откуда, от кого) |
| `external_reference` | string | optional | Номер платёжного поручения, банковской квитанции. **Рекомендуется заполнять**, особенно для bank_transfer. При наличии — защита от дублей (409 при повторе). |
| `payment_date` | date | required | Дата поступления |

```json
{
  "amount_kopecks": 500000,
  "payment_method": "bank_transfer",
  "description": "Перевод от ООО Пример",
  "external_reference": "ПП-12345",
  "payment_date": "2026-03-25"
}
```

**Ответ 201:**

```json
{
  "id": "uuid",
  "campaign_id": "uuid",
  "amount_kopecks": 500000,
  "payment_method": "bank_transfer",
  "description": "Перевод от ООО Пример",
  "external_reference": "ПП-12345",
  "payment_date": "2026-03-25",
  "recorded_by_admin_id": "uuid",
  "created_at": "2026-03-28T12:00:00Z"
}
```

Атомарно увеличивает `collected_amount`. Комиссия **не** начисляется.

**Ошибки:** `404` CAMPAIGN_NOT_FOUND, `400` VALIDATION_ERROR, `409` DUPLICATE_OFFLINE_PAYMENT

---

### 3.12 GET `/admin/campaigns/{id}/offline-payments` — Список офлайн-платежей кампании

**Требование:** ADM-14

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "campaign_id": "uuid",
      "amount_kopecks": 500000,
      "payment_method": "bank_transfer",
      "description": "Перевод от ООО Пример",
      "external_reference": "ПП-12345",
      "payment_date": "2026-03-25",
      "recorded_by_admin_id": "uuid",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

## 4. Медиа (ADM-03)

После загрузки запись попадает в таблицу `media_assets` и доступна в списке `GET /admin/media`. Старые файлы, загруженные до появления библиотеки, в списке не отображаются.

### 4.1 POST `/admin/media/upload` — Загрузка файла в S3

**Content-Type:** `multipart/form-data` (не JSON). Поля формы: `file`, `type`.

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `file` | file | required | Файл |
| `type` | string | required | `video`, `document` или `audio` |

**Ограничения:**
- video: max 500 MB, формат mp4 (`video/mp4`)
- document: max 10 MB, формат pdf (`application/pdf`)
- audio: max 50 MB, MIME: `audio/mpeg`, `audio/mp4`, `audio/ogg`, `audio/webm`

**Ответ 200:**

```json
{
  "id": "0195a1b2-c3d4-7e5f-8a90-abcdef123456",
  "key": "videos/a1b2c3d4e5f6789012345678abcdef.mp4",
  "url": "https://backend.porublyu.parmenid.tech/s3/porubly/videos/a1b2c3d4e5f6789012345678abcdef.mp4",
  "filename": "video.mp4",
  "size_bytes": 15000000,
  "content_type": "video/mp4"
}
```

| Поле | Описание |
|------|----------|
| `id` | UUID записи в библиотеке медиа |
| `key` | Ключ объекта в S3 (префикс `videos/`, `documents/` или `audio/`) |
| `url` | Публичный URL — его указывают в `video_url`, `thumbnail_url`, `file_url`, `media_url`, `logo_url` при создании/обновлении сущностей |

**Ошибки:** `422` FILE_TOO_LARGE / INVALID_FILE_FORMAT / INVALID_MEDIA_TYPE

---

### 4.2 GET `/admin/media` — Список загруженных файлов

**Query-параметры:** `limit`, `cursor` (как в других списках), опционально `type` (`video` | `document` | `audio`), `search` (подстрока в имени файла или `s3_key`).

**Ответ 200:** `{ "data": [...], "pagination": { "next_cursor", "has_more", "total": null } }`

Элемент `data`:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | uuid | |
| `key` | string | S3 key |
| `url` | string | Публичный URL |
| `type` | string | `video` / `document` / `audio` |
| `filename` | string | Оригинальное имя |
| `size_bytes` | int | |
| `content_type` | string | |
| `created_at` | string | ISO 8601 |

---

### 4.3 GET `/admin/media/{id}` — Деталь медиа

**Ответ 200:** те же поля, что в элементе списка, плюс `download_url` (при публичном бакете совпадает с `url`) и `uploaded_by_admin_id` (uuid или null).

**Ошибки:** `404` NOT_FOUND

---

### 4.4 GET `/admin/media/{id}/download` — Скачивание (редирект)

**Ответ 302:** `Location` = публичный URL файла.

**Ошибки:** `404` NOT_FOUND

---

## 5. Документы кампании (ADM-02)

### 5.1 POST `/admin/campaigns/{id}/documents` — Добавить документ

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `title` | string(255) | required | Название документа |
| `file_url` | string | required | URL (из media/upload) |
| `sort_order` | integer | optional | Порядок, по умолчанию 0 |

**Ответ 201:** Объект CampaignDocument

---

### 5.2 DELETE `/admin/campaigns/{id}/documents/{doc_id}` — Удалить документ

**Ответ 204:** No Content

---

## 6. Благодарности (ADM-04)

### 6.1 POST `/admin/campaigns/{id}/thanks` — Добавить благодарность

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `type` | string | required | `video` или `audio` |
| `media_url` | string | required | URL медиа: после `POST /admin/media/upload` с тем же смыслом — для видео-благодарности поле формы `type=video`, для аудио — **`type=audio`**, затем подставить `url` из ответа |
| `title` | string(255) | optional | Заголовок |
| `description` | string | optional | Текст |

**Ответ 201:** Объект ThanksContent

---

### 6.2 PATCH `/admin/campaigns/{id}/thanks/{t_id}` — Обновить благодарность

Все поля из POST — optional.

**Ответ 200:** Обновлённый объект ThanksContent

---

### 6.3 DELETE `/admin/campaigns/{id}/thanks/{t_id}` — Удалить благодарность

**Ответ 204:** No Content

---

## 7. Пользователи (ADM-05, ADM-12)

### 7.1 GET `/admin/users` — Список пользователей

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `role` | string | null | `donor`, `patron` |
| `search` | string | null | Поиск по email, name |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "name": "Иван",
      "role": "donor",
      "is_active": true,
      "total_donated_kopecks": 150000,
      "total_donations_count": 35,
      "current_streak_days": 42,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 7.2 GET `/admin/users/{id}` — Деталь пользователя

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
  "is_active": true,
  "is_deleted": false,
  "deleted_at": null,
  "total_donated_kopecks": 150000,
  "total_donations_count": 35,
  "current_streak_days": 42,
  "created_at": "2026-01-15T10:00:00Z",
  "subscriptions": [
    {
      "id": "uuid",
      "amount_kopecks": 300,
      "billing_period": "monthly",
      "status": "active",
      "next_billing_at": "2026-04-28T12:00:00Z"
    }
  ],
  "recent_donations": [
    {
      "id": "uuid",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 50000,
      "status": "success",
      "created_at": "2026-03-20T10:00:00Z"
    }
  ]
}
```

---

### 7.3 POST `/admin/users/{id}/grant-patron` — Назначить мецената

**Требование:** PAT-05, ADM-12

**Ответ 200:**

```json
{ "id": "uuid", "email": "user@example.com", "role": "patron" }
```

**Ошибки:** `404` USER_NOT_FOUND

---

### 7.4 POST `/admin/users/{id}/revoke-patron` — Отозвать статус мецената

**Требование:** PAT-06, ADM-12

**Ответ 200:**

```json
{ "id": "uuid", "email": "user@example.com", "role": "donor" }
```

**Ошибки:** `404` USER_NOT_FOUND

---

### 7.5 POST `/admin/users/{id}/deactivate` — Деактивировать пользователя

**Требование:** ADM-05

Деактивирует аккаунт пользователя (`is_active = false`). Все активные refresh-токены отзываются. Активные подписки приостанавливаются (`paused_reason = user_request`).

**Ответ 200:**

```json
{ "id": "uuid", "email": "user@example.com", "is_active": false }
```

**Ошибки:** `404` USER_NOT_FOUND, `422` USER_ALREADY_DEACTIVATED

---

### 7.6 POST `/admin/users/{id}/activate` — Активировать пользователя

Восстанавливает аккаунт пользователя (`is_active = true`). Подписки **не** возобновляются автоматически — пользователь должен сделать это вручную.

**Ответ 200:**

```json
{ "id": "uuid", "email": "user@example.com", "is_active": true }
```

**Ошибки:** `404` USER_NOT_FOUND, `422` USER_ALREADY_ACTIVE

---

## 8. Статистика (ADM-06, ADM-07)

### 8.1 GET `/admin/stats/overview` — Общая статистика

**Требование:** ADM-07

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `period_from` | date | null | Начало периода |
| `period_to` | date | null | Конец периода |

**Ответ 200:**

```json
{
  "gmv_kopecks": 25000000,
  "platform_fee_kopecks": 3750000,
  "active_subscriptions": 342,
  "total_donors": 1250,
  "new_donors_period": 85,
  "retention_30d": 0.72,
  "retention_90d": 0.45,
  "period_from": "2026-03-01",
  "period_to": "2026-03-28"
}
```

---

### 8.2 GET `/admin/stats/campaigns/{id}` — Статистика кампании

**Требование:** ADM-06

**Ответ 200:**

```json
{
  "campaign_id": "uuid",
  "campaign_title": "Помощь детям",
  "collected_amount": 4500000,
  "donors_count": 128,
  "average_check_kopecks": 35156,
  "subscriptions_count": 45,
  "donations_count": 83,
  "offline_payments_amount": 500000
}
```

---

## 9. Выплаты фондам (ADM-15, PAY-01 — PAY-04)

### 9.1 GET `/admin/payouts` — Список выплат

**Требование:** PAY-02

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `foundation_id` | uuid | null | Фильтр по фонду |
| `period_from` | date | null | Начало периода |
| `period_to` | date | null | Конец периода |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "foundation_id": "uuid",
      "foundation_name": "Фонд помощи",
      "amount_kopecks": 1500000,
      "period_from": "2026-02-01",
      "period_to": "2026-02-28",
      "transfer_reference": "ПП-789",
      "note": "Ежемесячный перевод",
      "created_by_admin_id": "uuid",
      "created_at": "2026-03-05T10:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 9.2 POST `/admin/payouts` — Создать запись о выплате

**Требование:** PAY-01

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `foundation_id` | uuid | required | ID фонда |
| `amount_kopecks` | integer | required | Сумма перевода (> 0) |
| `period_from` | date | required | Начало периода |
| `period_to` | date | required | Конец периода |
| `transfer_reference` | string | optional | Номер платёжки |
| `note` | string | optional | Комментарий |

**Ответ 201:** Объект PayoutRecord

**Ошибки:** `404` FOUNDATION_NOT_FOUND, `400` VALIDATION_ERROR

---

### 9.3 GET `/admin/payouts/balance` — Баланс к выплате по фондам

**Требование:** PAY-03, PAY-04

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `period_from` | date | null | Начало периода |
| `period_to` | date | null | Конец периода |

**Ответ 200:**

```json
{
  "data": [
    {
      "foundation_id": "uuid",
      "foundation_name": "Фонд помощи",
      "collected_nco_kopecks": 3200000,
      "paid_kopecks": 1500000,
      "due_kopecks": 1700000
    }
  ]
}
```

**Формула:** `due = SUM(nco_amount_kopecks WHERE status=success) - SUM(payout_records.amount_kopecks)` за период.

---

## 10. Достижения (ADM-10)

### 10.1 GET `/admin/achievements` — Список достижений

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
      "condition_type": "donations_count",
      "condition_value": 1,
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

### 10.2 POST `/admin/achievements` — Создать достижение

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `code` | string | required | Уникальный код (FIRST_DONATION, STREAK_30, ...) |
| `title` | string(255) | required | Название |
| `description` | string | optional | Условие получения |
| `icon_url` | string | optional | URL иконки |
| `condition_type` | string | required | `streak_days`, `total_amount_kopecks`, `donations_count` |
| `condition_value` | integer | required | Порог |

**Ответ 201:** Объект Achievement

**Ошибки:** `409` CONFLICT (duplicate code)

---

### 10.3 PATCH `/admin/achievements/{id}` — Обновить достижение

Все поля из POST — optional.

**Ответ 200:** Обновлённый объект Achievement

---

## 11. Логи (ADM-09)

### 11.1 GET `/admin/allocation-logs` — Логи перераспределений

**Требование:** ADM-09

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `subscription_id` | uuid | null | Фильтр по подписке |
| `reason` | string | null | `campaign_completed`, `campaign_closed_early`, `no_campaigns_in_foundation`, `no_campaigns_on_platform`, `manual_by_admin` |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "subscription_id": "uuid",
      "from_campaign_id": "uuid",
      "from_campaign_title": "Кампания А",
      "to_campaign_id": "uuid",
      "to_campaign_title": "Кампания Б",
      "reason": "campaign_completed",
      "notified_at": "2026-03-28T12:00:00Z",
      "created_at": "2026-03-28T11:55:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 11.2 GET `/admin/notification-logs` — Логи уведомлений

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `user_id` | uuid | null | Фильтр по пользователю |
| `notification_type` | string | null | Фильтр по типу |
| `status` | string | null | `sent`, `mock`, `failed` |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "notification_type": "payment_success",
      "title": "Списание 3₽",
      "body": "Помощь детям. Стрик: 42 дня!",
      "status": "mock",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

## 12. Управление администраторами (ADM-16)

### 12.1 GET `/admin/admins` — Список администраторов

**Требование:** ADM-16

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `limit` | integer | 20 | 1–100 |
| `cursor` | string | null | Курсор |
| `is_active` | boolean | null | Фильтр по статусу |

**Ответ 200:**

```json
{
  "data": [
    {
      "id": "uuid",
      "email": "admin@porubly.ru",
      "name": "Администратор",
      "is_active": true,
      "created_at": "2025-12-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "pagination": { "next_cursor": null, "has_more": false, "total": null }
}
```

---

### 12.2 POST `/admin/admins` — Создать администратора

**Требование:** ADM-16

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `email` | string (email) | required | Email нового администратора |
| `password` | string | required | Пароль (мин. 8 символов, буквы + цифры) |
| `name` | string(100) | optional | Имя |

```json
{
  "email": "new-admin@porubly.ru",
  "password": "SecureP@ss123",
  "name": "Новый Администратор"
}
```

**Ответ 201:**

```json
{
  "id": "uuid",
  "email": "new-admin@porubly.ru",
  "name": "Новый Администратор",
  "is_active": true,
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Ошибки:** `409` ADMIN_EMAIL_EXISTS, `422` WEAK_PASSWORD, `400` VALIDATION_ERROR

---

### 12.3 GET `/admin/admins/{id}` — Деталь администратора

**Ответ 200:** Полный объект администратора (как в списке)

**Ошибки:** `404` ADMIN_NOT_FOUND

---

### 12.4 PATCH `/admin/admins/{id}` — Обновить администратора

**Тело запроса:**

| Ключ | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `name` | string(100) | optional | Имя |
| `email` | string (email) | optional | Email |
| `password` | string | optional | Новый пароль |

**Ответ 200:** Обновлённый объект администратора

**Ошибки:** `404` ADMIN_NOT_FOUND, `409` ADMIN_EMAIL_EXISTS, `422` WEAK_PASSWORD

---

### 12.5 POST `/admin/admins/{id}/deactivate` — Деактивировать администратора

Деактивирует аккаунт администратора. Все активные refresh-токены отзываются. Нельзя деактивировать свой собственный аккаунт.

**Ответ 200:**

```json
{ "id": "uuid", "email": "admin@porubly.ru", "is_active": false }
```

**Ошибки:** `404` ADMIN_NOT_FOUND, `422` CANNOT_DEACTIVATE_SELF

---

### 12.6 POST `/admin/admins/{id}/activate` — Активировать администратора

**Ответ 200:**

```json
{ "id": "uuid", "email": "admin@porubly.ru", "is_active": true }
```

**Ошибки:** `404` ADMIN_NOT_FOUND

---

## Сводка: все Admin-эндпоинты

| # | Метод | Путь | Требование | Описание |
|---|-------|------|-----------|----------|
| 1 | POST | `/admin/auth/login` | AUTH-05 | Вход админа |
| 2 | GET | `/admin/foundations` | ADM-01 | Список фондов |
| 3 | POST | `/admin/foundations` | ADM-01 | Создать фонд |
| 4 | GET | `/admin/foundations/{id}` | ADM-01 | Деталь фонда |
| 5 | PATCH | `/admin/foundations/{id}` | ADM-01 | Обновить фонд |
| 6 | GET | `/admin/campaigns` | ADM-02 | Список кампаний |
| 7 | POST | `/admin/campaigns` | ADM-02 | Создать кампанию |
| 8 | GET | `/admin/campaigns/{id}` | ADM-02 | Деталь кампании |
| 9 | PATCH | `/admin/campaigns/{id}` | ADM-02, 08 | Обновить кампанию |
| 10 | POST | `/admin/campaigns/{id}/publish` | ADM-02 | draft → active |
| 11 | POST | `/admin/campaigns/{id}/pause` | ADM-02 | active → paused |
| 12 | POST | `/admin/campaigns/{id}/complete` | ADM-02 | active → completed |
| 13 | POST | `/admin/campaigns/{id}/archive` | ADM-02 | completed → archived |
| 14 | POST | `/admin/campaigns/{id}/close-early` | CLOSE-01, ADM-13 | Досрочное закрытие |
| 15 | POST | `/admin/campaigns/{id}/force-realloc` | ADM-11 | Принудительная реаллокация |
| 16 | POST | `/admin/campaigns/{id}/offline-payment` | CLOSE-04, ADM-14 | Офлайн-платёж |
| 17 | POST | `/admin/media/upload` | ADM-03 | Загрузка медиа |
| 17a | GET | `/admin/media` | ADM-03 | Список медиа (библиотека) |
| 17b | GET | `/admin/media/{id}` | ADM-03 | Деталь медиа |
| 17c | GET | `/admin/media/{id}/download` | ADM-03 | Редирект на файл |
| 18 | POST | `/admin/campaigns/{id}/documents` | ADM-02 | Добавить документ |
| 19 | DELETE | `/admin/campaigns/{id}/documents/{doc_id}` | ADM-02 | Удалить документ |
| 20 | POST | `/admin/campaigns/{id}/thanks` | ADM-04 | Добавить благодарность |
| 21 | PATCH | `/admin/campaigns/{id}/thanks/{t_id}` | ADM-04 | Обновить благодарность |
| 22 | DELETE | `/admin/campaigns/{id}/thanks/{t_id}` | ADM-04 | Удалить благодарность |
| 23 | GET | `/admin/users` | ADM-05 | Список пользователей |
| 24 | GET | `/admin/users/{id}` | ADM-05 | Деталь пользователя |
| 25 | POST | `/admin/users/{id}/grant-patron` | PAT-05, ADM-12 | Назначить мецената |
| 26 | POST | `/admin/users/{id}/revoke-patron` | PAT-06, ADM-12 | Отозвать мецената |
| 27 | GET | `/admin/stats/overview` | ADM-07 | Общая статистика |
| 28 | GET | `/admin/stats/campaigns/{id}` | ADM-06 | Статистика кампании |
| 29 | GET | `/admin/payouts` | PAY-02 | Список выплат |
| 30 | POST | `/admin/payouts` | PAY-01 | Создать выплату |
| 31 | GET | `/admin/payouts/balance` | PAY-03 | Баланс к выплате |
| 32 | GET | `/admin/achievements` | ADM-10 | Список достижений |
| 33 | POST | `/admin/achievements` | ADM-10 | Создать достижение |
| 34 | PATCH | `/admin/achievements/{id}` | ADM-10 | Обновить достижение |
| 35 | GET | `/admin/allocation-logs` | ADM-09 | Логи перераспределений |
| 36 | GET | `/admin/notification-logs` | — | Логи уведомлений |
| 37 | POST | `/admin/auth/refresh` | AUTH-06 | Обновить admin access-токен |
| 38 | POST | `/admin/auth/logout` | AUTH-07 | Выход администратора |
| 39 | POST | `/admin/users/{id}/deactivate` | ADM-05 | Деактивировать пользователя |
| 40 | POST | `/admin/users/{id}/activate` | ADM-05 | Активировать пользователя |
| 41 | GET | `/admin/campaigns/{id}/offline-payments` | ADM-14 | Список офлайн-платежей |
| 42 | GET | `/admin/admins` | ADM-16 | Список администраторов |
| 43 | POST | `/admin/admins` | ADM-16 | Создать администратора |
| 44 | GET | `/admin/admins/{id}` | ADM-16 | Деталь администратора |
| 45 | PATCH | `/admin/admins/{id}` | ADM-16 | Обновить администратора |
| 46 | POST | `/admin/admins/{id}/deactivate` | ADM-16 | Деактивировать администратора |
| 47 | POST | `/admin/admins/{id}/activate` | ADM-16 | Активировать администратора |

**Итого: 47 эндпоинтов admin API.**
