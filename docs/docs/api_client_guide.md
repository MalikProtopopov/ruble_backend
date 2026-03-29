# API Guide: мобильное приложение "По Рублю" (Flutter)

> Полное руководство для Flutter-разработчика. Содержит все эндпоинты, форматы запросов/ответов, коды ошибок и бизнес-правила.

---

## 0. Общая информация

### Base URL

```
https://backend.porublyu.parmenid.tech/api/v1
```

### Формат сумм

Все денежные суммы передаются и возвращаются **в копейках** (`int`).

| Отображение | Значение в API |
|---|---|
| 10 руб | `1000` |
| 3 руб | `300` |
| 1 руб | `100` |

### Формат дат

Все даты в формате **ISO 8601 UTC**: `2026-03-28T12:00:00Z`

### Аутентификация

Bearer-токен в заголовке `Authorization`:

```
Authorization: Bearer <access_token>
```

- Access token: JWT RS256, срок жизни **15 минут**
- Refresh token: JWT RS256, срок жизни **30 дней**
- Payload access token: `{"sub": "<user_uuid>", "role": "donor|patron", "type": "access", ...}`

### Формат ошибок (единый)

Все ошибки API возвращаются в едином формате:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Человекочитаемое описание",
    "details": {}
  }
}
```

Коды HTTP статусов:
- `400` -- ошибка валидации / бизнес-правило
- `401` -- не авторизован / невалидный токен
- `403` -- доступ запрещён (роль / деактивация)
- `404` -- ресурс не найден
- `409` -- конфликт
- `422` -- ошибка бизнес-логики

Ошибка валидации Pydantic (FastAPI) возвращается в стандартном формате FastAPI:

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Пагинация

Все списки используют **cursor-based** пагинацию.

**Query-параметры:**

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `limit` | int (1--100) | 20 | Количество элементов на странице |
| `cursor` | string \| null | null | Курсор для следующей страницы (opaque base64-строка) |

**Формат ответа списка:**

```json
{
  "data": [ ... ],
  "pagination": {
    "next_cursor": "eyJpZCI6ICIuLi4ifQ==",
    "has_more": true,
    "total": null
  }
}
```

- `next_cursor` -- передать в следующий запрос как `?cursor=...`. `null` если больше данных нет.
- `has_more` -- `true` если есть ещё страницы.
- `total` -- всегда `null` (не подсчитывается для производительности).

### Роли пользователей

| Роль | Описание |
|---|---|
| Guest | Неавторизованный пользователь. Может просматривать кампании и фонды. |
| Donor | Авторизованный пользователь. Может делать донаты, подписки, просматривать историю. |
| Patron | Меценат. Все права Donor + создание платёжных ссылок. |

### Медиа-файлы (видео, аудио, документы, изображения)

Все медиа-файлы доступны по базовому URL:

```
https://backend.porublyu.parmenid.tech/media/
```

Полный URL файла формируется как `{base}/media/{s3_key}`, например:
- `https://backend.porublyu.parmenid.tech/media/videos/4fba9bc5ea594768ba5b052662bcfeef.mp4`
- `https://backend.porublyu.parmenid.tech/media/documents/67715fc6733244b3855a708983ca10ed.pdf`
- `https://backend.porublyu.parmenid.tech/media/audio/184456ef9aa54178bc0b3519ddd684b2.mp3`

Клиенту **не нужно** самостоятельно конструировать URL медиа. API возвращает готовые ссылки в полях `video_url`, `thumbnail_url`, `media_url`, `file_url`, `logo_url` и т.д.

### Админка и библиотека медиа

Эндпоинты загрузки и списка медиа (`/api/v1/admin/media/...`) доступны **только админам**. Для мобильного клиента **контракт публичного API не меняется**: в ответах приходят готовые строки URL. Отдельно получать «библиотеку» или ключи S3 клиенту не требуется.

---

## 1. Аутентификация

Аутентификация построена на **email OTP** (одноразовый код, 6 цифр).

Флоу:
1. Клиент вызывает `send-otp` с email пользователя.
2. Сервер отправляет OTP-код на email (TTL -- 10 минут, макс. 5 попыток ввода).
3. Клиент вызывает `verify-otp` с email + кодом.
4. Сервер возвращает `access_token`, `refresh_token` и данные пользователя.
5. Если пользователя с таким email нет, он создаётся автоматически (поле `is_new: true`).
6. Access token живёт 15 мин, refresh token -- 30 дней.

---

### 1.1 POST /auth/send-otp

Отправить OTP-код на email.

| | |
|---|---|
| **URL** | `POST /auth/send-otp` |
| **Роль** | Guest (без авторизации) |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `email` | string (email) | да | Email пользователя |

**Пример запроса:**

```json
{
  "email": "donor@example.com"
}
```

**Response 200:**

```json
{
  "message": "OTP код отправлен",
  "expires_in_seconds": 600
}
```

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `OTP_RATE_LIMIT` | 422 | Повторная отправка раньше чем через 60 секунд |
| (validation) | 422 | Невалидный email |

**Пример curl:**

```bash
curl -X POST https://backend.porublyu.parmenid.tech/api/v1/auth/send-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "donor@example.com"}'
```

**Бизнес-правила:**
- Rate limit: 1 запрос в 60 секунд на один email (через Redis).
- OTP живёт 10 минут.
- Максимум 5 попыток ввода кода.

---

### 1.2 POST /auth/verify-otp

Проверить OTP-код и получить токены.

| | |
|---|---|
| **URL** | `POST /auth/verify-otp` |
| **Роль** | Guest (без авторизации) |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `email` | string (email) | да | Email, на который был отправлен код |
| `code` | string | да | 6-значный OTP-код |

**Пример запроса:**

```json
{
  "email": "donor@example.com",
  "code": "123456"
}
```

**Response 200:**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "01912345-6789-7abc-def0-123456789abc",
    "email": "donor@example.com",
    "name": null,
    "role": "donor",
    "is_new": true
  }
}
```

- `is_new: true` -- пользователь создан только что (первый вход). Можно показать экран онбординга.
- `is_new: false` -- пользователь существовал ранее.

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `OTP_EXPIRED` | 422 | OTP-код истёк или не найден |
| `OTP_MAX_ATTEMPTS` | 422 | Превышено число попыток ввода (5 попыток) |
| `OTP_INVALID` | 422 | Неверный OTP-код |
| `FORBIDDEN` | 403 | Аккаунт деактивирован |

**Пример curl:**

```bash
curl -X POST https://backend.porublyu.parmenid.tech/api/v1/auth/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "donor@example.com", "code": "123456"}'
```

---

### 1.3 POST /auth/refresh

Обновить пару токенов по refresh token.

| | |
|---|---|
| **URL** | `POST /auth/refresh` |
| **Роль** | Любая (токен проверяется по базе) |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `refresh_token` | string | да | Текущий refresh token |

**Пример запроса:**

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

**Response 200:**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...(новый)",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...(новый)",
  "token_type": "bearer"
}
```

> **Важно:** Используется **ротация refresh token**. Каждый вызов `/refresh` выдаёт новый refresh token и инвалидирует старый. Старый refresh token повторно использовать нельзя.

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `INVALID_REFRESH_TOKEN` | 401 | Refresh token не найден / отозван / истёк / пользователь деактивирован |
| `REPLAY_ATTACK_DETECTED` | 401 | Повторное использование уже ротированного токена. Все сессии пользователя отозваны. |

**Пример curl:**

```bash
curl -X POST https://backend.porublyu.parmenid.tech/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJSUzI1NiIs..."}'
```

**Бизнес-правила:**
- При обнаружении повторного использования токена (replay attack) сервер отзывает ВСЕ refresh-токены пользователя. Клиент должен перенаправить на экран логина.

---

### 1.4 POST /auth/logout

Выйти из системы (отозвать refresh token).

| | |
|---|---|
| **URL** | `POST /auth/logout` |
| **Роль** | Donor / Patron |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `refresh_token` | string | да | Refresh token для отзыва |

**Пример запроса:**

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

**Response 204:** No Content (пустое тело)

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Access token невалиден или отсутствует |

**Пример curl:**

```bash
curl -X POST https://backend.porublyu.parmenid.tech/api/v1/auth/logout \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGci..."}'
```

---

## 2. Профиль пользователя

---

### 2.1 GET /me

Получить профиль текущего пользователя.

| | |
|---|---|
| **URL** | `GET /me` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 200:**

```json
{
  "id": "01912345-6789-7abc-def0-123456789abc",
  "email": "donor@example.com",
  "phone": "+79991234567",
  "name": "Иван Иванов",
  "avatar_url": "https://backend.porublyu.parmenid.tech/media/avatars/abc.jpg",
  "role": "donor",
  "timezone": "Europe/Moscow",
  "notification_preferences": {
    "push_on_payment": true,
    "push_on_campaign_change": true,
    "push_daily_streak": false,
    "push_campaign_completed": true
  },
  "created_at": "2026-01-15T10:30:00Z"
}
```

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID пользователя |
| `email` | string | Email |
| `phone` | string \| null | Телефон |
| `name` | string \| null | Имя |
| `avatar_url` | string \| null | URL аватарки |
| `role` | string | `"donor"` или `"patron"` |
| `timezone` | string | IANA-таймзона (default `"Europe/Moscow"`) |
| `notification_preferences` | object | Настройки push-уведомлений |
| `created_at` | datetime | Дата регистрации |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный или отсутствующий токен |
| `NOT_FOUND` | 404 | Пользователь не найден |

**Пример curl:**

```bash
curl https://backend.porublyu.parmenid.tech/api/v1/me \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 2.2 PATCH /me

Обновить профиль (частичное обновление).

| | |
|---|---|
| **URL** | `PATCH /me` |
| **Роль** | Donor / Patron |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body (все поля опциональны):**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `name` | string \| null | нет | Имя пользователя |
| `phone` | string \| null | нет | Телефон |
| `avatar_url` | string \| null | нет | URL аватарки |
| `timezone` | string \| null | нет | IANA-таймзона (`Europe/Moscow`, `Asia/Novosibirsk`, ...) |
| `push_token` | string \| null | нет | Firebase push token устройства |
| `push_platform` | string \| null | нет | Платформа (`ios` или `android`) |

> **Важно:** При первом запуске приложения после авторизации отправьте `push_token` и `push_platform` через этот эндпоинт, чтобы получать push-уведомления.

**Пример запроса:**

```json
{
  "name": "Иван Иванов",
  "push_token": "dGVzdC1wdXNoLXRva2Vu...",
  "push_platform": "ios"
}
```

**Response 200:**

```json
{
  "id": "01912345-6789-7abc-def0-123456789abc",
  "email": "donor@example.com",
  "phone": null,
  "name": "Иван Иванов",
  "avatar_url": null,
  "role": "donor",
  "timezone": "Europe/Moscow",
  "notification_preferences": {
    "push_on_payment": true,
    "push_on_campaign_change": true,
    "push_daily_streak": false,
    "push_campaign_completed": true
  },
  "created_at": "2026-01-15T10:30:00Z"
}
```

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Пользователь не найден |

**Пример curl:**

```bash
curl -X PATCH https://backend.porublyu.parmenid.tech/api/v1/me \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"name": "Иван Иванов", "push_token": "abc123", "push_platform": "ios"}'
```

---

### 2.3 PATCH /me/notifications

Обновить настройки push-уведомлений.

| | |
|---|---|
| **URL** | `PATCH /me/notifications` |
| **Роль** | Donor / Patron |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body (все поля опциональны):**

| Поле | Тип | Обязательное | Default | Описание |
|---|---|---|---|---|
| `push_on_payment` | bool | нет | true | Уведомление при списании / успешном донате |
| `push_on_campaign_change` | bool | нет | true | Уведомления об изменениях в кампаниях |
| `push_daily_streak` | bool | нет | false | Ежедневное уведомление о стрике |
| `push_campaign_completed` | bool | нет | true | Уведомление о завершении кампании |

**Пример запроса:**

```json
{
  "push_daily_streak": true,
  "push_on_payment": false
}
```

**Response 200:** (возвращает обновлённые настройки, формат идентичен GET /me)

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Пользователь не найден |

**Пример curl:**

```bash
curl -X PATCH https://backend.porublyu.parmenid.tech/api/v1/me/notifications \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"push_daily_streak": true}'
```

---

### 2.4 DELETE /me

Удалить аккаунт (анонимизация данных).

| | |
|---|---|
| **URL** | `DELETE /me` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 204:** No Content (пустое тело)

> **Важно:** Аккаунт анонимизируется (email, имя, телефон заменяются), а не удаляется физически. Подписки отменяются. Действие необратимо.

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |

**Пример curl:**

```bash
curl -X DELETE https://backend.porublyu.parmenid.tech/api/v1/me \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 3. Кампании

---

### 3.1 GET /campaigns

Список активных кампаний. Доступен без авторизации.

| | |
|---|---|
| **URL** | `GET /campaigns` |
| **Роль** | Guest / Donor / Patron |

**Request Headers:**

```
(нет обязательных заголовков)
```

**Query-параметры:**

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `limit` | int (1--100) | 20 | Количество элементов |
| `cursor` | string \| null | null | Курсор пагинации |

**Response 200:**

```json
{
  "data": [
    {
      "id": "01912345-0000-7abc-def0-000000000001",
      "foundation_id": "01912345-0000-7abc-def0-000000000100",
      "foundation": {
        "id": "01912345-0000-7abc-def0-000000000100",
        "name": "Фонд помощи",
        "logo_url": "https://backend.porublyu.parmenid.tech/media/logos/fond.png"
      },
      "title": "Помощь детям",
      "description": "Сбор средств для детского дома",
      "thumbnail_url": "https://backend.porublyu.parmenid.tech/media/images/campaign1.jpg",
      "status": "active",
      "goal_amount": 10000000,
      "collected_amount": 3500000,
      "donors_count": 42,
      "urgency_level": 5,
      "is_permanent": false,
      "ends_at": "2026-06-01T00:00:00Z",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6ICIuLi4ifQ==",
    "has_more": true,
    "total": null
  }
}
```

**Поля элемента списка (`CampaignListItem`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID кампании |
| `foundation_id` | UUID | ID фонда |
| `foundation` | object \| null | Краткая информация о фонде (`id`, `name`, `logo_url`) |
| `title` | string | Название кампании |
| `description` | string \| null | Описание |
| `thumbnail_url` | string \| null | URL превью-изображения |
| `status` | string | `"active"` |
| `goal_amount` | int \| null | Цель сбора в копейках. `null` если бессрочная кампания без цели. |
| `collected_amount` | int | Собрано в копейках |
| `donors_count` | int | Число уникальных жертвователей |
| `urgency_level` | int | Срочность (1-5, где 5 -- самая срочная) |
| `is_permanent` | bool | Бессрочная кампания |
| `ends_at` | datetime \| null | Дата окончания. `null` если бессрочная. |
| `created_at` | datetime | Дата создания |

**Коды ошибок:** нет специфических

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/campaigns?limit=10"
```

---

### 3.2 GET /campaigns/{campaign_id}

Детальная информация о кампании. Доступен без авторизации.

| | |
|---|---|
| **URL** | `GET /campaigns/{campaign_id}` |
| **Роль** | Guest / Donor / Patron |

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | ID кампании |

**Request Headers:**

```
(нет обязательных заголовков)
```

**Response 200:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000001",
  "foundation_id": "01912345-0000-7abc-def0-000000000100",
  "foundation": {
    "id": "01912345-0000-7abc-def0-000000000100",
    "name": "Фонд помощи",
    "logo_url": "https://backend.porublyu.parmenid.tech/media/logos/fond.png"
  },
  "title": "Помощь детям",
  "description": "Сбор средств для детского дома",
  "thumbnail_url": "https://backend.porublyu.parmenid.tech/media/images/campaign1.jpg",
  "status": "active",
  "goal_amount": 10000000,
  "collected_amount": 3500000,
  "donors_count": 42,
  "urgency_level": 5,
  "is_permanent": false,
  "ends_at": "2026-06-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "video_url": "https://backend.porublyu.parmenid.tech/media/videos/campaign1.mp4",
  "closed_early": false,
  "close_note": null,
  "documents": [
    {
      "id": "01912345-0000-7abc-def0-000000000200",
      "title": "Отчёт за январь",
      "file_url": "https://backend.porublyu.parmenid.tech/media/documents/report-jan.pdf",
      "sort_order": 0
    }
  ],
  "thanks_contents": [
    {
      "id": "01912345-0000-7abc-def0-000000000300",
      "type": "video",
      "media_url": "https://backend.porublyu.parmenid.tech/media/videos/thanks-video1.mp4",
      "title": "Спасибо от подопечных",
      "description": "Дети благодарят за помощь"
    }
  ]
}
```

**Дополнительные поля (сверх `CampaignListItem`):**

| Поле | Тип | Описание |
|---|---|---|
| `video_url` | string \| null | URL видео кампании |
| `closed_early` | bool | Была ли кампания закрыта досрочно |
| `close_note` | string \| null | Причина досрочного закрытия |
| `documents` | array | Список документов кампании |
| `thanks_contents` | array | Список благодарностей от фонда |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `NOT_FOUND` | 404 | Кампания не найдена |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/campaigns/01912345-0000-7abc-def0-000000000001"
```

---

### 3.3 GET /campaigns/{campaign_id}/documents

Получить документы кампании (отчёты, PDF).

| | |
|---|---|
| **URL** | `GET /campaigns/{campaign_id}/documents` |
| **Роль** | Guest / Donor / Patron |

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | ID кампании |

**Response 200:**

```json
[
  {
    "id": "01912345-0000-7abc-def0-000000000200",
    "title": "Отчёт за январь",
    "file_url": "https://backend.porublyu.parmenid.tech/media/documents/report-jan.pdf",
    "sort_order": 0
  },
  {
    "id": "01912345-0000-7abc-def0-000000000201",
    "title": "Отчёт за февраль",
    "file_url": "https://backend.porublyu.parmenid.tech/media/documents/report-feb.pdf",
    "sort_order": 1
  }
]
```

**Поля элемента:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID документа |
| `title` | string | Заголовок |
| `file_url` | string | URL для скачивания (PDF) |
| `sort_order` | int | Порядок сортировки |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `NOT_FOUND` | 404 | Кампания не найдена |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/campaigns/01912345-.../documents"
```

---

### 3.4 GET /campaigns/{campaign_id}/share

Получить данные для шаринга кампании (deep link, текст).

| | |
|---|---|
| **URL** | `GET /campaigns/{campaign_id}/share` |
| **Роль** | Donor / Patron (требуется авторизация) |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | ID кампании |

**Response 200:**

```json
{
  "share_url": "https://porublyu.parmenid.tech/c/01912345-0000-7abc-def0-000000000001",
  "title": "Помощь детям",
  "description": "Сбор средств для детского дома"
}
```

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `share_url` | string | URL для шаринга (deep link) |
| `title` | string | Заголовок для шаринга |
| `description` | string | Описание для шаринга |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Кампания не найдена |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/campaigns/01912345-.../share" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 4. Фонды

---

### 4.1 GET /foundations/{foundation_id}

Получить публичную информацию о фонде. Доступен без авторизации.

| | |
|---|---|
| **URL** | `GET /foundations/{foundation_id}` |
| **Роль** | Guest / Donor / Patron |

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `foundation_id` | UUID | ID фонда |

**Request Headers:**

```
(нет обязательных заголовков)
```

**Response 200:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000100",
  "name": "Фонд помощи",
  "description": "Благотворительный фонд, помогающий детям",
  "logo_url": "https://backend.porublyu.parmenid.tech/media/logos/fond.png",
  "website_url": "https://fond-pomosch.ru",
  "status": "active"
}
```

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID фонда |
| `name` | string | Название |
| `description` | string \| null | Описание |
| `logo_url` | string \| null | URL логотипа |
| `website_url` | string \| null | Ссылка на сайт |
| `status` | string | Статус фонда (`"active"`) |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `NOT_FOUND` | 404 | Фонд не найден |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/foundations/01912345-0000-7abc-def0-000000000100"
```

---

## 5. Разовые донаты

---

### Гостевой флоу (Guest Donation Flow)

Если пользователь не авторизован, но хочет сделать донат:

1. Клиент вызывает `POST /donations` с `email` и **без** Bearer token.
2. Сервер проверяет:
   - Если пользователь с таким email **существует** -- возвращает `AUTH_REQUIRED` с `details: {"email": "..."}`.
   - Если пользователя **нет** -- возвращает `AUTH_REQUIRED` с `details: {"email": "...", "is_new": true}`.
3. Клиент перенаправляет на OTP-флоу (`send-otp` -> `verify-otp`).
4. После получения токенов клиент повторяет `POST /donations` с Bearer token (поле `email` уже не нужно).

```
Пользователь нажимает "Пожертвовать"
          |
     Есть token?
      /       \
    Да        Нет
     |          |
  POST с     POST с email
  Bearer     (без Bearer)
     |          |
   201      401 AUTH_REQUIRED
             |
        OTP-флоу
             |
       Получен token
             |
        POST с Bearer
             |
           201
```

---

### 5.1 POST /donations

Создать разовый донат.

| | |
|---|---|
| **URL** | `POST /donations` |
| **Роль** | Guest (с email) / Donor / Patron |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>   (опционально для гостевого флоу)
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `campaign_id` | UUID | да | ID кампании |
| `amount_kopecks` | int | да | Сумма в копейках (мин. 1000 = 10 руб) |
| `email` | string (email) \| null | условно | Обязательно если нет Bearer token |

**Пример запроса (авторизованный):**

```json
{
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "amount_kopecks": 50000
}
```

**Пример запроса (гостевой):**

```json
{
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "amount_kopecks": 50000,
  "email": "donor@example.com"
}
```

**Response 201:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000400",
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "amount_kopecks": 50000,
  "status": "pending",
  "source": "app",
  "payment_url": "https://yookassa.ru/checkout/...",
  "created_at": "2026-03-28T12:00:00Z"
}
```

> **Важно:** После создания доната клиент должен открыть `payment_url` в WebView или внешнем браузере для оплаты через YooKassa. После оплаты сервер получит вебхук и обновит статус на `success` или `failed`.

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID доната |
| `campaign_id` | UUID | ID кампании |
| `amount_kopecks` | int | Сумма в копейках |
| `status` | string | `"pending"` -- ожидает оплаты |
| `source` | string | `"app"` -- из мобильного приложения |
| `payment_url` | string \| null | URL для оплаты через YooKassa |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| `NOT_FOUND` | 404 | Кампания не найдена |
| `CAMPAIGN_NOT_ACTIVE` | 422 | Кампания не активна (завершена/архив) |
| `EMAIL_REQUIRED` | 400 | Гостевой запрос без email |
| `AUTH_REQUIRED` | 401 | Пользователь с таким email существует -- нужна авторизация. `details.email` содержит email. |
| `AUTH_REQUIRED` (is_new) | 401 | Пользователя нет -- нужна регистрация через OTP. `details.email` + `details.is_new: true`. |
| `ACCOUNT_DEACTIVATED` | 403 | Аккаунт деактивирован |
| `MIN_DONATION_AMOUNT` | 422 | Сумма меньше 1000 копеек (10 руб) |

**Пример curl:**

```bash
curl -X POST https://backend.porublyu.parmenid.tech/api/v1/donations \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"campaign_id": "01912345-...", "amount_kopecks": 50000}'
```

**Бизнес-правила:**
- Минимальная сумма: 1000 копеек (10 руб) для донатов из приложения.
- Комиссия платформы: 15% (не видна клиенту, рассчитывается на сервере).
- Статусы: `pending` -> `success` / `failed` (обновляется через вебхук YooKassa).

---

### 5.2 GET /donations

Список донатов текущего пользователя.

| | |
|---|---|
| **URL** | `GET /donations` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Query-параметры:**

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `limit` | int (1--100) | 20 | Количество элементов |
| `cursor` | string \| null | null | Курсор пагинации |
| `status` | string \| null | null | Фильтр по статусу (`pending`, `success`, `failed`) |
| `campaign_id` | UUID \| null | null | Фильтр по кампании |

**Response 200:**

```json
{
  "data": [
    {
      "id": "01912345-0000-7abc-def0-000000000400",
      "campaign_id": "01912345-0000-7abc-def0-000000000001",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 50000,
      "status": "success",
      "source": "app",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Поля элемента списка (`DonationListItem`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID доната |
| `campaign_id` | UUID | ID кампании |
| `campaign_title` | string \| null | Название кампании |
| `amount_kopecks` | int | Сумма |
| `status` | string | `"pending"`, `"success"`, `"failed"` |
| `source` | string | `"app"`, `"patron_link"` |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/donations?status=success&limit=10" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 5.3 GET /donations/{donation_id}

Детальная информация о донате.

| | |
|---|---|
| **URL** | `GET /donations/{donation_id}` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `donation_id` | UUID | ID доната |

**Response 200:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000400",
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "campaign_title": "Помощь детям",
  "foundation_id": "01912345-0000-7abc-def0-000000000100",
  "foundation_name": "Фонд помощи",
  "amount_kopecks": 50000,
  "status": "success",
  "source": "app",
  "payment_url": "https://yookassa.ru/checkout/...",
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Поля ответа (`DonationDetailResponse`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID доната |
| `campaign_id` | UUID | ID кампании |
| `campaign_title` | string \| null | Название кампании |
| `foundation_id` | UUID | ID фонда |
| `foundation_name` | string \| null | Название фонда |
| `amount_kopecks` | int | Сумма |
| `status` | string | `"pending"`, `"success"`, `"failed"` |
| `source` | string | `"app"`, `"patron_link"` |
| `payment_url` | string \| null | URL для оплаты (если `pending`) |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Донат не найден (или принадлежит другому пользователю) |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/donations/01912345-..." \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 6. Подписки

Подписка -- это рекуррентное пожертвование. Пользователь выбирает сумму в день и период списания.

### Расчёт суммы списания

Подписка задаётся как **дневная сумма** (`amount_kopecks`). Фактическое списание происходит за период:

| billing_period | Множитель | Пример: 100 коп/день |
|---|---|---|
| `weekly` | x7 | 700 копеек (7 руб) за списание |
| `monthly` | x30 | 3000 копеек (30 руб) за списание |

**Допустимые суммы в день:** 100, 300, 500, 1000 копеек (1, 3, 5, 10 руб/день).

### Стратегии распределения

| allocation_strategy | Описание | Обязательные поля |
|---|---|---|
| `platform_pool` | Платформа сама распределяет между кампаниями | -- |
| `foundation_pool` | Все средства идут конкретному фонду | `foundation_id` |
| `specific_campaign` | Все средства идут на конкретную кампанию | `campaign_id` |

### Статусы подписки

| Статус | Описание |
|---|---|
| `pending_payment_method` | Создана, ожидает привязки карты |
| `active` | Активна, списания по расписанию |
| `paused` | На паузе (пользователем) |
| `canceled` | Отменена |

### Максимум подписок

Максимум **5 активных подписок** на пользователя (статусы `active`, `paused`, `pending_payment_method`).

---

### 6.1 POST /subscriptions

Создать подписку.

| | |
|---|---|
| **URL** | `POST /subscriptions` |
| **Роль** | Donor / Patron |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `amount_kopecks` | int | да | Сумма в день: `100`, `300`, `500` или `1000` |
| `billing_period` | string | да | `"weekly"` или `"monthly"` |
| `allocation_strategy` | string | да | `"platform_pool"`, `"foundation_pool"` или `"specific_campaign"` |
| `campaign_id` | UUID \| null | условно | Обязательно если `allocation_strategy = "specific_campaign"` |
| `foundation_id` | UUID \| null | условно | Обязательно если `allocation_strategy = "foundation_pool"` |

**Пример запроса:**

```json
{
  "amount_kopecks": 300,
  "billing_period": "weekly",
  "allocation_strategy": "specific_campaign",
  "campaign_id": "01912345-0000-7abc-def0-000000000001"
}
```

**Response 201:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000500",
  "amount_kopecks": 300,
  "billing_period": "weekly",
  "allocation_strategy": "specific_campaign",
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "campaign_title": "Помощь детям",
  "foundation_id": null,
  "foundation_name": null,
  "status": "pending_payment_method",
  "paused_reason": null,
  "paused_at": null,
  "next_billing_at": null,
  "created_at": "2026-03-28T12:00:00Z"
}
```

> **Важно:** После создания подписка в статусе `pending_payment_method`. Необходимо вызвать `POST /subscriptions/{id}/bind-card` для привязки карты.

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `INVALID_AMOUNT` | 422 | Недопустимая сумма (не 100/300/500/1000) |
| `VALIDATION_ERROR` | 422 | Не указан `campaign_id` для `specific_campaign` или `foundation_id` для `foundation_pool` |
| `CAMPAIGN_NOT_ACTIVE` | 422 | Выбранная кампания не активна |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | 422 | Превышен лимит 5 активных подписок |

**Пример curl:**

```bash
curl -X POST https://backend.porublyu.parmenid.tech/api/v1/subscriptions \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"amount_kopecks": 300, "billing_period": "weekly", "allocation_strategy": "platform_pool"}'
```

---

### 6.2 GET /subscriptions

Список подписок текущего пользователя.

| | |
|---|---|
| **URL** | `GET /subscriptions` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Response 200:**

```json
[
  {
    "id": "01912345-0000-7abc-def0-000000000500",
    "amount_kopecks": 300,
    "billing_period": "weekly",
    "allocation_strategy": "specific_campaign",
    "campaign_id": "01912345-0000-7abc-def0-000000000001",
    "campaign_title": "Помощь детям",
    "foundation_id": null,
    "foundation_name": null,
    "status": "active",
    "paused_reason": null,
    "paused_at": null,
    "next_billing_at": "2026-04-04T12:00:00Z",
    "created_at": "2026-03-28T12:00:00Z"
  }
]
```

> **Примечание:** Этот эндпоинт возвращает **массив** (не paginated response), так как у пользователя максимум 5 подписок.

**Поля элемента (`SubscriptionResponse`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID подписки |
| `amount_kopecks` | int | Дневная сумма |
| `billing_period` | string | `"weekly"` или `"monthly"` |
| `allocation_strategy` | string | Стратегия распределения |
| `campaign_id` | UUID \| null | ID кампании (если `specific_campaign`) |
| `campaign_title` | string \| null | Название кампании |
| `foundation_id` | UUID \| null | ID фонда (если `foundation_pool`) |
| `foundation_name` | string \| null | Название фонда |
| `status` | string | Статус подписки |
| `paused_reason` | string \| null | Причина паузы |
| `paused_at` | datetime \| null | Время постановки на паузу |
| `next_billing_at` | datetime \| null | Дата следующего списания |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/subscriptions" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 6.3 PATCH /subscriptions/{subscription_id}

Обновить подписку (сумму, стратегию).

| | |
|---|---|
| **URL** | `PATCH /subscriptions/{subscription_id}` |
| **Роль** | Donor / Patron |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `subscription_id` | UUID | ID подписки |

**Request Body (все поля опциональны):**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `amount_kopecks` | int \| null | нет | Новая дневная сумма (100/300/500/1000) |
| `allocation_strategy` | string \| null | нет | Новая стратегия |
| `campaign_id` | UUID \| null | нет | Новая кампания |
| `foundation_id` | UUID \| null | нет | Новый фонд |

**Пример запроса:**

```json
{
  "amount_kopecks": 500
}
```

**Response 200:** объект `SubscriptionResponse` (формат как в GET /subscriptions)

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Подписка не найдена |
| `INVALID_AMOUNT` | 422 | Недопустимая сумма |

**Пример curl:**

```bash
curl -X PATCH "https://backend.porublyu.parmenid.tech/api/v1/subscriptions/01912345-.../amount" \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"amount_kopecks": 500}'
```

---

### 6.4 POST /subscriptions/{subscription_id}/pause

Поставить подписку на паузу.

| | |
|---|---|
| **URL** | `POST /subscriptions/{subscription_id}/pause` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 200:** объект `SubscriptionResponse` со статусом `"paused"`

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Подписка не найдена |
| `SUBSCRIPTION_NOT_ACTIVE` | 422 | Подписка не в статусе `active` |

**Пример curl:**

```bash
curl -X POST "https://backend.porublyu.parmenid.tech/api/v1/subscriptions/01912345-.../pause" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 6.5 POST /subscriptions/{subscription_id}/resume

Возобновить подписку с паузы.

| | |
|---|---|
| **URL** | `POST /subscriptions/{subscription_id}/resume` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 200:** объект `SubscriptionResponse` со статусом `"active"`

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Подписка не найдена |
| `SUBSCRIPTION_NOT_ACTIVE` | 422 | Подписка не на паузе |

**Пример curl:**

```bash
curl -X POST "https://backend.porublyu.parmenid.tech/api/v1/subscriptions/01912345-.../resume" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 6.6 DELETE /subscriptions/{subscription_id}

Отменить подписку.

| | |
|---|---|
| **URL** | `DELETE /subscriptions/{subscription_id}` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 204:** No Content (пустое тело)

> Подписка переходит в статус `canceled`. Уже запланированные транзакции не отменяются.

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Подписка не найдена |

**Пример curl:**

```bash
curl -X DELETE "https://backend.porublyu.parmenid.tech/api/v1/subscriptions/01912345-..." \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 6.7 POST /subscriptions/{subscription_id}/bind-card

Привязать карту к подписке. Возвращает URL для оплаты через YooKassa.

| | |
|---|---|
| **URL** | `POST /subscriptions/{subscription_id}/bind-card` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 201:**

```json
{
  "payment_url": "https://yookassa.ru/checkout/...",
  "confirmation_type": "redirect",
  "subscription_id": "01912345-0000-7abc-def0-000000000500",
  "amount_kopecks": 2100,
  "description": "Привязка карты к подписке По Рублю"
}
```

> **Важно:** `amount_kopecks` -- это сумма первого списания (дневная сумма x множитель периода). Клиент должен открыть `payment_url` в WebView для оплаты. После успешной оплаты подписка автоматически перейдёт в статус `active`.

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `payment_url` | string | URL для оплаты / привязки карты |
| `confirmation_type` | string | Всегда `"redirect"` |
| `subscription_id` | UUID | ID подписки |
| `amount_kopecks` | int | Сумма первого списания |
| `description` | string | Описание платежа |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Подписка не найдена |
| `SUBSCRIPTION_ALREADY_ACTIVE` | 422 | Карта уже привязана (подписка уже активна) |

**Пример curl:**

```bash
curl -X POST "https://backend.porublyu.parmenid.tech/api/v1/subscriptions/01912345-.../bind-card" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 7. Транзакции

Транзакции -- это отдельные списания по подписке. Каждое списание создаёт транзакцию.

---

### 7.1 GET /transactions

Список транзакций текущего пользователя.

| | |
|---|---|
| **URL** | `GET /transactions` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Query-параметры:**

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `limit` | int (1--100) | 20 | Количество элементов |
| `cursor` | string \| null | null | Курсор пагинации |
| `status` | string \| null | null | Фильтр по статусу (`pending`, `success`, `failed`, `skipped`) |
| `campaign_id` | UUID \| null | null | Фильтр по кампании |
| `subscription_id` | UUID \| null | null | Фильтр по подписке |
| `date_from` | datetime \| null | null | Начало периода (ISO 8601) |
| `date_to` | datetime \| null | null | Конец периода (ISO 8601) |

**Response 200:**

```json
{
  "data": [
    {
      "id": "01912345-0000-7abc-def0-000000000600",
      "subscription_id": "01912345-0000-7abc-def0-000000000500",
      "campaign_id": "01912345-0000-7abc-def0-000000000001",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 2100,
      "status": "success",
      "skipped_reason": null,
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Поля элемента списка (`TransactionListItem`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID транзакции |
| `subscription_id` | UUID | ID подписки |
| `campaign_id` | UUID \| null | ID кампании (null если platform_pool без выбранной кампании) |
| `campaign_title` | string \| null | Название кампании |
| `amount_kopecks` | int | Сумма списания |
| `status` | string | `"pending"`, `"success"`, `"failed"`, `"skipped"` |
| `skipped_reason` | string \| null | Причина пропуска (если `skipped`) |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/transactions?status=success&limit=50" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 7.2 GET /transactions/{transaction_id}

Детальная информация о транзакции.

| | |
|---|---|
| **URL** | `GET /transactions/{transaction_id}` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `transaction_id` | UUID | ID транзакции |

**Response 200:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000600",
  "subscription_id": "01912345-0000-7abc-def0-000000000500",
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "campaign_title": "Помощь детям",
  "foundation_id": "01912345-0000-7abc-def0-000000000100",
  "foundation_name": "Фонд помощи",
  "amount_kopecks": 2100,
  "platform_fee_kopecks": 315,
  "nco_amount_kopecks": 1785,
  "status": "success",
  "skipped_reason": null,
  "cancellation_reason": null,
  "attempt_number": 1,
  "next_retry_at": null,
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Поля ответа (`TransactionDetailResponse`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID транзакции |
| `subscription_id` | UUID | ID подписки |
| `campaign_id` | UUID \| null | ID кампании |
| `campaign_title` | string \| null | Название кампании |
| `foundation_id` | UUID \| null | ID фонда |
| `foundation_name` | string \| null | Название фонда |
| `amount_kopecks` | int | Полная сумма списания |
| `platform_fee_kopecks` | int | Комиссия платформы (15%) |
| `nco_amount_kopecks` | int | Сумма, получаемая НКО |
| `status` | string | Статус транзакции |
| `skipped_reason` | string \| null | Причина пропуска |
| `cancellation_reason` | string \| null | Причина отмены платежа (от YooKassa) |
| `attempt_number` | int | Номер попытки списания (1 = первая) |
| `next_retry_at` | datetime \| null | Дата следующей попытки списания (если `status = "failed"`). `null` если попытки исчерпаны или статус не `failed`. |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Транзакция не найдена |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/transactions/01912345-..." \
  -H "Authorization: Bearer eyJhbGci..."
```

**Бизнес-правила:**
- Комиссия платформы: 15% от суммы.
- `nco_amount_kopecks = amount_kopecks - platform_fee_kopecks`
- При неудачном списании (soft decline) сервер повторяет попытки по расписанию: через 1, 3, 7, 14 дней.

---

## 8. Импакт и достижения

---

### 8.1 GET /impact

Сводка импакта пользователя (общая сумма, стрик, количество донатов).

| | |
|---|---|
| **URL** | `GET /impact` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 200:**

```json
{
  "total_donated_kopecks": 150000,
  "streak_days": 42,
  "donations_count": 15,
  "streak_includes_skipped": true
}
```

**Поля ответа:**

| Поле | Тип | Описание |
|---|---|---|
| `total_donated_kopecks` | int | Общая сумма пожертвований в копейках |
| `streak_days` | int | Текущий стрик в днях (непрерывная серия дней с пожертвованиями) |
| `donations_count` | int | Общее количество успешных донатов |
| `streak_includes_skipped` | bool | Учитываются ли пропущенные транзакции в стрике (всегда `true`) |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Пользователь не найден |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/impact" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 8.2 GET /impact/achievements

Список достижений пользователя.

| | |
|---|---|
| **URL** | `GET /impact/achievements` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 200:**

```json
[
  {
    "id": "01912345-0000-7abc-def0-000000000700",
    "code": "first_donation",
    "title": "Первый шаг",
    "description": "Сделали первое пожертвование",
    "icon_url": "https://backend.porublyu.parmenid.tech/media/achievements/first.png",
    "earned_at": "2026-01-15T10:30:00Z"
  },
  {
    "id": "01912345-0000-7abc-def0-000000000701",
    "code": "streak_7",
    "title": "Неделя добра",
    "description": "Стрик 7 дней подряд",
    "icon_url": "https://backend.porublyu.parmenid.tech/media/achievements/streak7.png",
    "earned_at": null
  }
]
```

> Если `earned_at` равно `null`, достижение ещё не получено (можно показать в UI как "серое"/"заблокированное").

**Поля элемента (`AchievementResponse`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID достижения |
| `code` | string | Уникальный код достижения |
| `title` | string | Заголовок |
| `description` | string \| null | Описание |
| `icon_url` | string \| null | URL иконки |
| `earned_at` | datetime \| null | Дата получения. `null` = ещё не получено. |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/impact/achievements" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 9. Благодарности

Благодарности -- это видео/аудио контент от фондов для жертвователей. Появляются после достижения целей кампаний.

---

### 9.1 GET /thanks/unseen

Получить список непросмотренных благодарностей.

| | |
|---|---|
| **URL** | `GET /thanks/unseen` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Request Body:** нет

**Response 200:**

```json
[
  {
    "id": "01912345-0000-7abc-def0-000000000800",
    "campaign_id": "01912345-0000-7abc-def0-000000000001",
    "campaign_title": "Помощь детям",
    "foundation_name": "Фонд помощи",
    "type": "video",
    "media_url": "https://backend.porublyu.parmenid.tech/media/videos/thanks-video1.mp4",
    "title": "Спасибо от подопечных",
    "description": "Дети из детского дома благодарят за помощь",
    "user_contribution": {
      "total_donated_kopecks": 50000,
      "donations_count": 3,
      "first_donation_at": "2026-01-15T10:30:00Z",
      "last_donation_at": "2026-03-20T14:00:00Z"
    },
    "created_at": "2026-03-25T08:00:00Z"
  }
]
```

**Поля элемента (`UnseenThanksItem`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID благодарности |
| `campaign_id` | UUID | ID кампании |
| `campaign_title` | string | Название кампании |
| `foundation_name` | string | Название фонда |
| `type` | string | `"video"` или `"audio"` |
| `media_url` | string | URL медиаконтента |
| `title` | string \| null | Заголовок |
| `description` | string \| null | Описание |
| `user_contribution` | object | Вклад текущего пользователя в эту кампанию |
| `created_at` | datetime | Дата создания |

**Поля `user_contribution`:**

| Поле | Тип | Описание |
|---|---|---|
| `total_donated_kopecks` | int | Сколько пользователь пожертвовал на эту кампанию |
| `donations_count` | int | Количество донатов в эту кампанию |
| `first_donation_at` | datetime \| null | Дата первого доната |
| `last_donation_at` | datetime \| null | Дата последнего доната |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/thanks/unseen" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 9.2 GET /thanks/{thanks_id}

Получить детали благодарности (и пометить как просмотренную).

| | |
|---|---|
| **URL** | `GET /thanks/{thanks_id}` |
| **Роль** | Donor / Patron |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `thanks_id` | UUID | ID благодарности |

**Response 200:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000800",
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "campaign_title": "Помощь детям",
  "foundation_id": "01912345-0000-7abc-def0-000000000100",
  "foundation_name": "Фонд помощи",
  "type": "video",
  "media_url": "https://backend.porublyu.parmenid.tech/media/videos/thanks-video1.mp4",
  "title": "Спасибо от подопечных",
  "description": "Дети из детского дома благодарят за помощь",
  "user_contribution": {
    "total_donated_kopecks": 50000,
    "donations_count": 3,
    "first_donation_at": "2026-01-15T10:30:00Z",
    "last_donation_at": "2026-03-20T14:00:00Z"
  }
}
```

**Поля ответа (`ThanksResponse`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID благодарности |
| `campaign_id` | UUID | ID кампании |
| `campaign_title` | string | Название кампании |
| `foundation_id` | UUID | ID фонда |
| `foundation_name` | string | Название фонда |
| `type` | string | `"video"` или `"audio"` |
| `media_url` | string | URL медиаконтента |
| `title` | string \| null | Заголовок |
| `description` | string \| null | Описание |
| `user_contribution` | object | Вклад пользователя в кампанию |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| `NOT_FOUND` | 404 | Благодарность не найдена |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/thanks/01912345-..." \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 10. Меценаты (Patron)

Меценаты могут создавать платёжные ссылки для других людей. Платёжная ссылка привязана к кампании и имеет фиксированную сумму.

---

### 10.1 POST /patron/payment-links

Создать платёжную ссылку.

| | |
|---|---|
| **URL** | `POST /patron/payment-links` |
| **Роль** | Patron (только) |
| **Content-Type** | `application/json` |

**Request Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `campaign_id` | UUID | да | ID кампании |
| `amount_kopecks` | int | да | Сумма в копейках |

**Пример запроса:**

```json
{
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "amount_kopecks": 100000
}
```

**Response 201:**

```json
{
  "id": "01912345-0000-7abc-def0-000000000900",
  "campaign_id": "01912345-0000-7abc-def0-000000000001",
  "campaign_title": "Помощь детям",
  "amount_kopecks": 100000,
  "payment_url": "https://yookassa.ru/checkout/...",
  "expires_at": "2026-03-29T12:00:00Z",
  "status": "active",
  "created_at": "2026-03-28T12:00:00Z"
}
```

**Поля ответа (`PaymentLinkResponse`):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | ID ссылки |
| `campaign_id` | UUID | ID кампании |
| `campaign_title` | string \| null | Название кампании |
| `amount_kopecks` | int | Сумма |
| `payment_url` | string | URL для оплаты (отправить получателю) |
| `expires_at` | datetime | Срок действия (24 часа с момента создания) |
| `status` | string | `"active"`, `"paid"`, `"expired"` |
| `created_at` | datetime | Дата создания |

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| (HTTP 403) | 403 | Роль не `patron` |
| `NOT_FOUND` | 404 | Кампания не найдена |
| `CAMPAIGN_NOT_ACTIVE` | 422 | Кампания не активна |

**Пример curl:**

```bash
curl -X POST "https://backend.porublyu.parmenid.tech/api/v1/patron/payment-links" \
  -H "Authorization: Bearer eyJhbGci..." \
  -H "Content-Type: application/json" \
  -d '{"campaign_id": "01912345-...", "amount_kopecks": 100000}'
```

**Бизнес-правила:**
- Ссылка действительна **24 часа** (`PATRON_LINK_TTL_HOURS = 24`).
- Меценат отправляет `payment_url` другому человеку для оплаты.
- После оплаты статус меняется на `paid`.
- Пожертвование засчитывается в рамках кампании.

---

### 10.2 GET /patron/payment-links

Список платёжных ссылок мецената.

| | |
|---|---|
| **URL** | `GET /patron/payment-links` |
| **Роль** | Patron (только) |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Query-параметры:**

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `limit` | int (1--100) | 20 | Количество элементов |
| `cursor` | string \| null | null | Курсор пагинации |
| `status` | string \| null | null | Фильтр по статусу (`active`, `paid`, `expired`) |

**Response 200:**

```json
{
  "data": [
    {
      "id": "01912345-0000-7abc-def0-000000000900",
      "campaign_id": "01912345-0000-7abc-def0-000000000001",
      "campaign_title": "Помощь детям",
      "amount_kopecks": 100000,
      "payment_url": "https://yookassa.ru/checkout/...",
      "expires_at": "2026-03-29T12:00:00Z",
      "status": "paid",
      "created_at": "2026-03-28T12:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| (HTTP 403) | 403 | Роль не `patron` |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/patron/payment-links?status=active" \
  -H "Authorization: Bearer eyJhbGci..."
```

---

### 10.3 GET /patron/payment-links/{link_id}

Получить детали платёжной ссылки.

| | |
|---|---|
| **URL** | `GET /patron/payment-links/{link_id}` |
| **Роль** | Patron (только) |

**Request Headers:**

```
Authorization: Bearer <access_token>
```

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `link_id` | UUID | ID ссылки |

**Response 200:** объект `PaymentLinkResponse` (формат как в POST)

**Коды ошибок:**

| Код | HTTP | Описание |
|---|---|---|
| (HTTP 401) | 401 | Невалидный токен |
| (HTTP 403) | 403 | Роль не `patron` |
| `NOT_FOUND` | 404 | Ссылка не найдена |

**Пример curl:**

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/patron/payment-links/01912345-..." \
  -H "Authorization: Bearer eyJhbGci..."
```

---

## 11. Вебхуки

### POST /webhooks/yookassa

Серверный эндпоинт (server-to-server). Вызывается платёжной системой YooKassa для уведомления о статусе платежей.

| | |
|---|---|
| **URL** | `POST /webhooks/yookassa` |
| **Вызывающая сторона** | YooKassa (не мобильное приложение) |
| **Content-Type** | `application/json` |

**Обрабатываемые события:**

| Событие | Описание |
|---|---|
| `payment.succeeded` | Платёж успешен. Обновляет статус доната/транзакции/ссылки на `success`/`paid`. |
| `payment.canceled` | Платёж отменён. Обновляет статус на `failed`. Для транзакций запускает retry по расписанию. |

**Метаданные платежа (`metadata`):**

| Поле | Значения | Описание |
|---|---|---|
| `type` | `"donation"`, `"transaction"`, `"patron_link"` | Тип платежа |
| `entity_id` | UUID | ID сущности |

**Response 200:**

```json
{"status": "ok"}
```

> Клиентское приложение **не вызывает** этот эндпоинт. Он нужен для понимания жизненного цикла платежей: после оплаты в WebView, YooKassa отправляет вебхук, и сервер обновляет статус. Клиент может получить обновлённый статус через polling GET-запросов к `/donations/{id}` или `/transactions/{id}`.

---

## 12. Push-уведомления

Для получения push-уведомлений клиент должен:

1. Получить Firebase push token на устройстве.
2. Отправить `push_token` и `push_platform` через `PATCH /me`.
3. Настроить обработку входящих push-уведомлений.

### Типы push-уведомлений

| `notification_type` | Триггер | `title` (пример) | `body` (пример) | `data` payload |
|---|---|---|---|---|
| `donation_success` | Успешный разовый донат | `"Пожертвование 500₽"` | `"Спасибо за поддержку!"` | `{"type": "donation_success", "donation_id": "<uuid>"}` |
| `payment_success` | Успешное списание по подписке | `"Списание 21₽"` | `"Стрик: 42 дн."` | `{"type": "payment_success", "transaction_id": "<uuid>"}` |
| `streak_daily` | Ежедневное уведомление о стрике (12:00 в таймзоне пользователя) | `"Ваш стрик: 42 дней!"` | `"Вы помогаете 42 дней подряд. Так держать!"` | `{"type": "streak", "days": 42}` |
| `campaign_completed` | Кампания завершена (собрана сумма или закрыта досрочно) | `"Сбор завершён"` | `"Кампания «Помощь детям» завершена"` | `{"type": "campaign_closed", "campaign_id": "<uuid>", "closed_early": false}` |
| `thanks_content` | Фонд добавил благодарность к кампании | `"Благодарность от фонда"` | `"Помощь детям: Спасибо от подопечных"` | `{"type": "thanks_content", "thanks_content_id": "<uuid>", "campaign_id": "<uuid>"}` |

### Настройки уведомлений (notification_preferences)

| Настройка | По умолчанию | Контролирует типы |
|---|---|---|
| `push_on_payment` | `true` | `donation_success`, `payment_success` |
| `push_on_campaign_change` | `true` | (зарезервировано для изменений кампаний) |
| `push_daily_streak` | `false` | `streak_daily` |
| `push_campaign_completed` | `true` | `campaign_completed` |

> Тип `thanks_content` отправляется всегда (нет отдельного флага).

### Обработка push-уведомлений в клиенте

При нажатии на push-уведомление клиент должен маршрутизировать по полю `type` в `data`:

| `data.type` | Навигация |
|---|---|
| `donation_success` | Экран деталей доната (`/donations/{donation_id}`) |
| `payment_success` | Экран деталей транзакции (`/transactions/{transaction_id}`) |
| `streak` | Экран импакта (`/impact`) |
| `campaign_closed` | Экран деталей кампании (`/campaigns/{campaign_id}`) |
| `thanks_content` | Экран благодарности (`/thanks/{thanks_content_id}`) |

---

## 13. Полный справочник кодов ошибок

### Аутентификация

| Код | HTTP | Описание |
|---|---|---|
| `OTP_RATE_LIMIT` | 422 | Повторная отправка OTP раньше чем через 60 секунд |
| `OTP_EXPIRED` | 422 | OTP-код истёк (TTL 10 минут) или не найден |
| `OTP_MAX_ATTEMPTS` | 422 | Превышено число попыток ввода OTP (5 попыток) |
| `OTP_INVALID` | 422 | Неверный OTP-код |
| `FORBIDDEN` | 403 | Аккаунт деактивирован (при verify-otp) |
| `INVALID_REFRESH_TOKEN` | 401 | Refresh token не найден / отозван / истёк / пользователь деактивирован |
| `REPLAY_ATTACK_DETECTED` | 401 | Повторное использование ротированного refresh token. Все сессии отозваны. |

### Донаты

| Код | HTTP | Описание |
|---|---|---|
| `EMAIL_REQUIRED` | 400 | Гостевой запрос без указания email |
| `AUTH_REQUIRED` | 401 | Пользователь с таким email существует -- нужна авторизация через OTP. Проверить `details.is_new` для определения, это вход или регистрация. |
| `ACCOUNT_DEACTIVATED` | 403 | Аккаунт пользователя деактивирован |
| `MIN_DONATION_AMOUNT` | 422 | Сумма доната меньше 1000 копеек (10 руб) |

### Кампании

| Код | HTTP | Описание |
|---|---|---|
| `CAMPAIGN_NOT_ACTIVE` | 422 | Кампания не активна (завершена, архивирована) |

### Подписки

| Код | HTTP | Описание |
|---|---|---|
| `INVALID_AMOUNT` | 422 | Недопустимая сумма подписки (допустимы: 100, 300, 500, 1000 копеек/день) |
| `VALIDATION_ERROR` | 422 | Не указан обязательный `campaign_id` (для `specific_campaign`) или `foundation_id` (для `foundation_pool`) |
| `SUBSCRIPTION_LIMIT_EXCEEDED` | 422 | Превышен лимит 5 активных подписок |
| `SUBSCRIPTION_NOT_ACTIVE` | 422 | Попытка поставить на паузу неактивную подписку, или возобновить подписку не на паузе |
| `SUBSCRIPTION_ALREADY_ACTIVE` | 422 | Попытка привязать карту к уже активной подписке |

### Меценаты

| Код | HTTP | Описание |
|---|---|---|
| `CAMPAIGN_NOT_ACTIVE` | 422 | Кампания не активна (при создании платёжной ссылки) |

### Общие

| Код | HTTP | Описание |
|---|---|---|
| `NOT_FOUND` | 404 | Запрашиваемый ресурс не найден (кампания, фонд, донат, подписка, транзакция, благодарность, платёжная ссылка, пользователь) |
| `CONFLICT` | 409 | Конфликт (общий) |
| `FORBIDDEN` | 403 | Доступ запрещён |

### HTTP-ошибки FastAPI

| HTTP | Описание |
|---|---|
| 401 | `Not authenticated` -- отсутствует или невалидный Bearer token |
| 401 | `Invalid token type` -- токен не является access token |
| 401 | `Invalid token` -- JWT невалиден (истёк, подпись, формат) |
| 403 | `Patron role required` -- для эндпоинтов, требующих роль `patron` |
| 422 | Ошибка валидации Pydantic (неверный формат полей в request body) |

---

## Приложение A: Бизнес-константы

| Константа | Значение | Описание |
|---|---|---|
| `PLATFORM_FEE_PERCENT` | 15 | Комиссия платформы, % |
| `ALLOWED_SUBSCRIPTION_AMOUNTS` | 100, 300, 500, 1000 | Допустимые суммы подписки (копеек/день) |
| `BILLING_PERIOD_MULTIPLIER` | weekly: 7, monthly: 30 | Множитель для расчёта суммы списания |
| `MAX_ACTIVE_SUBSCRIPTIONS` | 5 | Макс. активных подписок на пользователя |
| `MIN_DONATION_AMOUNT_KOPECKS` | 1000 | Минимальная сумма доната (10 руб) |
| `OTP_TTL_MINUTES` | 10 | Время жизни OTP-кода |
| `OTP_MAX_ATTEMPTS` | 5 | Макс. попыток ввода OTP |
| `OTP_RATE_LIMIT_SECONDS` | 60 | Интервал между отправками OTP |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15 | Время жизни access token |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 30 | Время жизни refresh token |
| `PATRON_LINK_TTL_HOURS` | 24 | Время жизни платёжной ссылки мецената |
| `SOFT_DECLINE_RETRY_DAYS` | 1, 3, 7, 14 | Расписание повторных попыток списания при мягком отказе |

---

## Приложение B: Жизненный цикл платежей

```
Клиент                          Сервер                     YooKassa
   |                               |                          |
   |  POST /donations              |                          |
   |------------------------------>|                          |
   |  201 {payment_url, status:    |                          |
   |       "pending"}              |                          |
   |<------------------------------|                          |
   |                               |                          |
   |  Открыть payment_url          |                          |
   |  в WebView                    |                          |
   |---------------------------------------------->|          |
   |  Пользователь оплачивает      |              |          |
   |<----------------------------------------------|          |
   |                               |                          |
   |                               |  POST /webhooks/yookassa |
   |                               |  payment.succeeded       |
   |                               |<-------------------------|
   |                               |  {"status": "ok"}        |
   |                               |------------------------->|
   |                               |                          |
   |  GET /donations/{id}          |                          |
   |------------------------------>|                          |
   |  200 {status: "success"}      |                          |
   |<------------------------------|                          |
   |                               |                          |
   |  (Push: donation_success)     |                          |
   |<------------------------------|                          |
```

---

## Приложение C: Полный флоу подписки

```
1. POST /subscriptions
   -> 201 {status: "pending_payment_method", id: "..."}

2. POST /subscriptions/{id}/bind-card
   -> 201 {payment_url: "https://yookassa.ru/...", amount_kopecks: 2100}

3. Открыть payment_url в WebView
   -> Пользователь оплачивает первое списание

4. YooKassa -> POST /webhooks/yookassa (payment.succeeded)
   -> Подписка переходит в status: "active"
   -> next_billing_at устанавливается на +7/+30 дней

5. GET /subscriptions
   -> [{status: "active", next_billing_at: "2026-04-04T12:00:00Z", ...}]

6. Через 7/30 дней: сервер автоматически создаёт транзакцию и списывает

7. При неудаче: retry через 1, 3, 7, 14 дней (soft decline schedule)
```
