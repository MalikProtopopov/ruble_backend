# Административная панель API -- Полное руководство

> Версия: 1.0
> Дата: 2026-03-28
> Аудитория: фронтенд-разработчики админ-панели

---

## Содержание

0. [Общая информация](#0-общая-информация)
1. [Аутентификация](#1-аутентификация)
2. [Управление фондами](#2-управление-фондами)
3. [Управление кампаниями](#3-управление-кампаниями)
4. [Загрузка медиа](#4-загрузка-медиа)
5. [Управление пользователями](#5-управление-пользователями)
6. [Статистика](#6-статистика)
7. [Выплаты фондам](#7-выплаты-фондам)
8. [Достижения](#8-достижения)
9. [Логи](#9-логи)
10. [Управление администраторами](#10-управление-администраторами)
11. [Полный справочник ошибок](#11-полный-справочник-ошибок)
12. [Сводная таблица всех эндпоинтов](#12-сводная-таблица-всех-эндпоинтов)

---

## 0. Общая информация

### Base URL

```
https://backend.porublyu.parmenid.tech/api/v1/admin
```

Все пути в этом документе указаны относительно Base URL. Например, `POST /auth/login` означает `POST https://backend.porublyu.parmenid.tech/api/v1/admin/auth/login`.

### Аутентификация

Все эндпоинты, кроме `/auth/login` и `/auth/refresh`, требуют заголовка:

```
Authorization: Bearer <admin_access_token>
```

Время жизни access-токена -- 15 минут. При истечении необходимо вызвать `/auth/refresh`.

### Формат данных

| Правило | Описание |
|---|---|
| Формат ответов | JSON (`Content-Type: application/json`) |
| Денежные суммы | Всегда в **копейках** (int). 100 копеек = 1 рубль |
| Даты и время | UTC, ISO 8601: `2026-03-28T14:30:00Z` |
| Даты (без времени) | ISO 8601: `2026-03-28` |
| Идентификаторы | UUID v7 (строка) |

### Пагинация (cursor-based)

Все списковые эндпоинты поддерживают курсорную пагинацию. Query-параметры:

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `limit` | int | 20 | Количество элементов на странице (1-100) |
| `cursor` | string \| null | null | Курсор для следующей страницы (из предыдущего ответа) |

Формат ответа пагинированных списков:

```json
{
  "data": [ ... ],
  "pagination": {
    "next_cursor": "eyJpZCI6IC4uLn0=",
    "has_more": true,
    "total": null
  }
}
```

- `next_cursor` -- передать в следующий запрос для получения следующей страницы. `null` если данных больше нет.
- `has_more` -- `true` если есть ещё записи.
- `total` -- всегда `null` (cursor-based пагинация не считает общее количество).

### Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Фонд не найден",
    "details": {}
  }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `code` | string | Машиночитаемый код ошибки |
| `message` | string | Человекочитаемое сообщение (на русском) |
| `details` | object | Дополнительная информация (может быть пустым `{}`) |

---

## 1. Аутентификация

Базовый путь: `/auth`

---

### 1.1. POST /auth/login

Вход администратора по email и паролю.

**Авторизация:** не требуется.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `email` | string (email) | да | Email администратора | Валидный email |
| `password` | string | да | Пароль | -- |

**Пример запроса:**

```json
{
  "email": "admin@porublyu.ru",
  "password": "securePass123!"
}
```

**Успешный ответ (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
  "token_type": "bearer",
  "admin": {
    "id": "019523a1-7b4c-7def-8a12-abcdef123456",
    "email": "admin@porublyu.ru",
    "name": "Иван Петров"
  }
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Неверный email или пароль |
| 403 | `ACCOUNT_DISABLED` | Аккаунт администратора деактивирован |

---

### 1.2. POST /auth/refresh

Обновление пары токенов по refresh-токену.

**Авторизация:** не требуется.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `refresh_token` | string | да | Текущий refresh-токен |

**Пример запроса:**

```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4..."
}
```

**Успешный ответ (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "bmV3IHJlZnJlc2ggdG9rZW4...",
  "token_type": "bearer",
  "admin": {
    "id": "019523a1-7b4c-7def-8a12-abcdef123456",
    "email": "admin@porublyu.ru",
    "name": "Иван Петров"
  }
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 401 | `TOKEN_EXPIRED` | Refresh-токен истёк (30 дней) |
| 401 | `TOKEN_REVOKED` | Токен был отозван (logout) |

---

### 1.3. POST /auth/logout

Выход администратора, отзыв refresh-токена.

**Авторизация:** не требуется (токен передаётся в теле).

**Тело запроса:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `refresh_token` | string | да | Refresh-токен для отзыва |

**Пример запроса:**

```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4..."
}
```

**Успешный ответ:** `204 No Content` (пустое тело).

**Ошибки:** нет (идемпотентная операция).

---

## 2. Управление фондами

Базовый путь: `/foundations`

---

### 2.1. GET /foundations

Список фондов с фильтрацией и пагинацией.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `status` | string | нет | Фильтр по статусу: `pending_verification`, `active`, `suspended` |
| `search` | string | нет | Поиск по названию / ИНН |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "name": "Фонд помощи детям",
      "description": "Благотворительный фонд помощи детям-сиротам",
      "logo_url": "https://cdn.porublyu.ru/logos/fond1.png",
      "website_url": "https://fond-help.ru",
      "status": "active",
      "legal_name": "АНО \"Фонд помощи детям\"",
      "inn": "7712345678",
      "yookassa_shop_id": "shop_abc123",
      "verified_at": "2026-01-15T10:30:00Z",
      "created_at": "2026-01-10T08:00:00Z",
      "updated_at": "2026-03-01T12:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6IC4uLn0=",
    "has_more": true,
    "total": null
  }
}
```

**Поля объекта фонда:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор фонда |
| `name` | string | Публичное название |
| `description` | string \| null | Описание фонда |
| `logo_url` | string \| null | URL логотипа |
| `website_url` | string \| null | Ссылка на сайт фонда |
| `status` | string | Статус: `pending_verification`, `active`, `suspended` |
| `legal_name` | string | Юридическое наименование |
| `inn` | string | ИНН организации |
| `yookassa_shop_id` | string \| null | ID магазина YooKassa |
| `verified_at` | datetime \| null | Дата верификации |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата последнего обновления |

---

### 2.2. POST /foundations

Создание нового фонда. Фонд создаётся в статусе `pending_verification`.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `name` | string | да | Публичное название | -- |
| `legal_name` | string | да | Юридическое наименование | -- |
| `inn` | string | да | ИНН организации | Уникальное значение |
| `description` | string | нет | Описание | -- |
| `logo_url` | string | нет | URL логотипа (загрузить через `/media/upload`) | -- |
| `website_url` | string | нет | Ссылка на сайт | -- |

**Пример запроса:**

```json
{
  "name": "Фонд помощи детям",
  "legal_name": "АНО \"Фонд помощи детям\"",
  "inn": "7712345678",
  "description": "Благотворительный фонд помощи детям-сиротам",
  "logo_url": "https://cdn.porublyu.ru/logos/fond1.png",
  "website_url": "https://fond-help.ru"
}
```

**Успешный ответ (201):** объект фонда (формат см. в 2.1).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 409 | `INN_ALREADY_EXISTS` | Фонд с таким ИНН уже зарегистрирован |
| 422 | -- | Ошибка валидации полей |

---

### 2.3. GET /foundations/{foundation_id}

Получение деталей одного фонда.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `foundation_id` | UUID | Идентификатор фонда |

**Успешный ответ (200):** объект фонда (формат см. в 2.1).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Фонд не найден |

---

### 2.4. PATCH /foundations/{foundation_id}

Обновление данных фонда. Передавайте только те поля, которые нужно изменить.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `foundation_id` | UUID | Идентификатор фонда |

**Тело запроса (все поля опциональные):**

| Поле | Тип | Описание | Ограничения |
|---|---|---|---|
| `name` | string | Публичное название | -- |
| `legal_name` | string | Юридическое наименование | -- |
| `inn` | string | ИНН | Уникальное значение |
| `description` | string | Описание | -- |
| `logo_url` | string | URL логотипа | -- |
| `website_url` | string | Ссылка на сайт | -- |
| `status` | string | Статус фонда | `pending_verification`, `active`, `suspended` |
| `yookassa_shop_id` | string | ID магазина YooKassa | -- |

**Бизнес-правила:**
- При смене статуса на `active` автоматически проставляется `verified_at` (если ещё не было установлено).
- При изменении ИНН проверяется уникальность.

**Пример запроса:**

```json
{
  "status": "active",
  "yookassa_shop_id": "shop_abc123"
}
```

**Успешный ответ (200):** обновлённый объект фонда.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Фонд не найден |
| 409 | `INN_ALREADY_EXISTS` | Новый ИНН уже занят |

---

## 3. Управление кампаниями

Базовый путь: `/campaigns`

### Статусная машина кампаний (FSM)

```
  draft ──> active ──> paused
                │         │
                │         └──> active (возврат)
                │
                └──> completed ──> archived
```

**Таблица допустимых переходов:**

| Текущий статус | Допустимые целевые статусы | Эндпоинт |
|---|---|---|
| `draft` | `active` | `POST /{id}/publish` |
| `active` | `paused` | `POST /{id}/pause` |
| `active` | `completed` | `POST /{id}/complete` или `POST /{id}/close-early` |
| `paused` | `active` | `POST /{id}/publish` |
| `completed` | `archived` | `POST /{id}/archive` |

> При завершении кампании (`complete` / `close-early`) автоматически происходит реаллокация подписок пользователей на другие кампании, а всем донорам отправляется push-уведомление.

---

### 3.1. GET /campaigns

Список кампаний с фильтрацией и пагинацией.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `status` | string | нет | Фильтр: `draft`, `active`, `paused`, `completed`, `archived` |
| `foundation_id` | UUID | нет | Фильтр по фонду |
| `search` | string | нет | Поиск по названию |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "019523b2-aaaa-7def-8a12-abcdef123456",
      "foundation_id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "foundation_name": "Фонд помощи детям",
      "title": "Сбор на лечение Маши",
      "description": "Маше 5 лет, нужна срочная операция",
      "video_url": "https://cdn.porublyu.ru/videos/masha.mp4",
      "thumbnail_url": "https://cdn.porublyu.ru/thumbs/masha.jpg",
      "status": "active",
      "goal_amount": 50000000,
      "collected_amount": 12345600,
      "donors_count": 234,
      "urgency_level": 5,
      "is_permanent": false,
      "ends_at": "2026-06-01T00:00:00Z",
      "sort_order": 10,
      "closed_early": false,
      "close_note": null,
      "created_at": "2026-02-01T10:00:00Z",
      "updated_at": "2026-03-25T15:30:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6IC4uLn0=",
    "has_more": false,
    "total": null
  }
}
```

**Поля объекта кампании:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор кампании |
| `foundation_id` | UUID | ID фонда |
| `foundation_name` | string \| null | Название фонда |
| `title` | string | Заголовок кампании |
| `description` | string \| null | Описание |
| `video_url` | string \| null | URL видео |
| `thumbnail_url` | string \| null | URL превью |
| `status` | string | Статус кампании |
| `goal_amount` | int \| null | Целевая сумма в копейках (`null` для бессрочных) |
| `collected_amount` | int | Собранная сумма в копейках |
| `donors_count` | int | Количество доноров |
| `urgency_level` | int | Уровень срочности (1-5) |
| `is_permanent` | bool | Бессрочная кампания |
| `ends_at` | datetime \| null | Дата окончания сбора |
| `sort_order` | int | Порядок сортировки (меньше = выше) |
| `closed_early` | bool | Закрыта досрочно |
| `close_note` | string \| null | Причина досрочного закрытия |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата последнего обновления |

---

### 3.2. POST /campaigns

Создание новой кампании. Кампания создаётся в статусе `draft`.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `foundation_id` | UUID | да | ID фонда | Фонд должен существовать |
| `title` | string | да | Заголовок кампании | -- |
| `description` | string | нет | Описание | -- |
| `video_url` | string | нет | URL видео | -- |
| `thumbnail_url` | string | нет | URL превью | -- |
| `goal_amount` | int | нет | Целевая сумма в копейках | `null` для бессрочных |
| `urgency_level` | int | нет | Уровень срочности | По умолчанию 3 |
| `is_permanent` | bool | нет | Бессрочная кампания | По умолчанию `false` |
| `ends_at` | datetime | нет | Дата окончания | ISO 8601 |
| `sort_order` | int | нет | Порядок сортировки | По умолчанию 0 |

**Пример запроса:**

```json
{
  "foundation_id": "019523a1-7b4c-7def-8a12-abcdef123456",
  "title": "Сбор на лечение Маши",
  "description": "Маше 5 лет, нужна срочная операция",
  "goal_amount": 50000000,
  "urgency_level": 5,
  "ends_at": "2026-06-01T00:00:00Z"
}
```

**Успешный ответ (201):** объект кампании (формат см. в 3.1).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Фонд не найден |
| 422 | -- | Ошибка валидации полей |

---

### 3.3. GET /campaigns/{campaign_id}

Получение детальной информации о кампании, включая документы и контент благодарностей.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Успешный ответ (200):**

```json
{
  "id": "019523b2-aaaa-7def-8a12-abcdef123456",
  "foundation_id": "019523a1-7b4c-7def-8a12-abcdef123456",
  "foundation_name": "Фонд помощи детям",
  "title": "Сбор на лечение Маши",
  "description": "Маше 5 лет, нужна срочная операция",
  "video_url": "https://cdn.porublyu.ru/videos/masha.mp4",
  "thumbnail_url": "https://cdn.porublyu.ru/thumbs/masha.jpg",
  "status": "active",
  "goal_amount": 50000000,
  "collected_amount": 12345600,
  "donors_count": 234,
  "urgency_level": 5,
  "is_permanent": false,
  "ends_at": "2026-06-01T00:00:00Z",
  "sort_order": 10,
  "closed_early": false,
  "close_note": null,
  "created_at": "2026-02-01T10:00:00Z",
  "updated_at": "2026-03-25T15:30:00Z",
  "documents": [
    {
      "id": "019523c3-bbbb-7def-8a12-abcdef123456",
      "title": "Медицинское заключение",
      "file_url": "https://cdn.porublyu.ru/documents/med_report.pdf",
      "sort_order": 0
    }
  ],
  "thanks_contents": [
    {
      "id": "019523d4-cccc-7def-8a12-abcdef123456",
      "type": "video",
      "media_url": "https://cdn.porublyu.ru/videos/thanks_masha.mp4",
      "title": "Спасибо от Маши!",
      "description": "Маша записала видео-благодарность всем, кто помогал"
    }
  ]
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

---

### 3.4. PATCH /campaigns/{campaign_id}

Обновление данных кампании. Передавайте только изменённые поля.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса (все поля опциональные):**

| Поле | Тип | Описание |
|---|---|---|
| `foundation_id` | UUID | ID фонда |
| `title` | string | Заголовок |
| `description` | string | Описание |
| `video_url` | string | URL видео |
| `thumbnail_url` | string | URL превью |
| `goal_amount` | int | Целевая сумма (копейки) |
| `urgency_level` | int | Уровень срочности |
| `is_permanent` | bool | Бессрочная кампания |
| `ends_at` | datetime | Дата окончания |
| `sort_order` | int | Порядок сортировки |

**Пример запроса:**

```json
{
  "title": "Обновлённый заголовок",
  "urgency_level": 4
}
```

**Успешный ответ (200):** обновлённый объект кампании.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

> **Примечание:** этот эндпоинт обновляет только данные кампании, не статус. Для смены статуса используйте отдельные эндпоинты (publish, pause, complete и т.д.).

---

### 3.5. POST /campaigns/{campaign_id}/publish

Публикация кампании (перевод в статус `active`).

**Допустимые исходные статусы:** `draft`, `paused`.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:** отсутствует.

**Успешный ответ (200):** объект кампании со статусом `active`.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |
| 422 | `INVALID_STATUS_TRANSITION` | Невозможный переход статуса |

---

### 3.6. POST /campaigns/{campaign_id}/pause

Приостановка кампании.

**Допустимые исходные статусы:** `active`.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:** отсутствует.

**Успешный ответ (200):** объект кампании со статусом `paused`.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |
| 422 | `INVALID_STATUS_TRANSITION` | Невозможный переход статуса |

---

### 3.7. POST /campaigns/{campaign_id}/complete

Завершение кампании (сбор завершён).

**Допустимые исходные статусы:** `active`.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:** отсутствует.

**Побочные эффекты:**
- Все подписки, привязанные к этой кампании, автоматически реаллоцируются на другие активные кампании.
- Всем донорам кампании отправляется push-уведомление с текстом "Сбор завершён".

**Успешный ответ (200):** объект кампании со статусом `completed`.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |
| 422 | `INVALID_STATUS_TRANSITION` | Невозможный переход статуса |

---

### 3.8. POST /campaigns/{campaign_id}/close-early

Досрочное закрытие кампании с указанием причины.

**Допустимые исходные статусы:** `active`.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `close_note` | string | да | Причина досрочного закрытия |

**Пример запроса:**

```json
{
  "close_note": "Маша выздоровела, собранных средств достаточно"
}
```

**Побочные эффекты:**
- Устанавливается `closed_early = true` и `close_note`.
- Все подписки автоматически реаллоцируются.
- Всем донорам отправляется push-уведомление с текстом из `close_note`.

**Успешный ответ (200):** объект кампании со статусом `completed`, `closed_early = true`.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |
| 422 | `INVALID_STATUS_TRANSITION` | Невозможный переход статуса |

---

### 3.9. POST /campaigns/{campaign_id}/archive

Архивация завершённой кампании.

**Допустимые исходные статусы:** `completed`.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:** отсутствует.

**Успешный ответ (200):** объект кампании со статусом `archived`.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |
| 422 | `INVALID_STATUS_TRANSITION` | Невозможный переход статуса |

---

### 3.10. POST /campaigns/{campaign_id}/force-realloc

Принудительная реаллокация всех активных подписок кампании на другие кампании.

> Используйте с осторожностью. Операция немедленно переключает подписки пользователей.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:** отсутствует.

**Успешный ответ (200):**

```json
{
  "reallocated_subscriptions": 42
}
```

| Поле | Тип | Описание |
|---|---|---|
| `reallocated_subscriptions` | int | Количество переведённых подписок |

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

---

### 3.11. POST /campaigns/{campaign_id}/offline-payment

Регистрация офлайн-платежа (наличные, банковский перевод и т.д.).

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `amount_kopecks` | int | да | Сумма платежа в копейках | > 0 |
| `payment_method` | string | да | Способ оплаты | `cash`, `bank_transfer`, `other` |
| `description` | string | нет | Описание платежа | -- |
| `external_reference` | string | нет | Внешний номер платёжного документа | -- |
| `payment_date` | date | да | Дата платежа | ISO 8601 (`YYYY-MM-DD`) |

**Пример запроса:**

```json
{
  "amount_kopecks": 10000000,
  "payment_method": "bank_transfer",
  "description": "Перевод от ООО Рога и Копыта",
  "external_reference": "PAY-2026-00042",
  "payment_date": "2026-03-25"
}
```

**Побочные эффекты:**
- Сумма `collected_amount` кампании автоматически увеличивается на `amount_kopecks`.
- Если после увеличения `collected_amount >= goal_amount`, кампания может быть автоматически завершена.

**Успешный ответ (201):**

```json
{
  "id": "019523e5-dddd-7def-8a12-abcdef123456",
  "campaign_id": "019523b2-aaaa-7def-8a12-abcdef123456",
  "amount_kopecks": 10000000,
  "payment_method": "bank_transfer",
  "description": "Перевод от ООО Рога и Копыта",
  "external_reference": "PAY-2026-00042",
  "payment_date": "2026-03-25",
  "recorded_by_admin_id": "019523a1-7b4c-7def-8a12-abcdef123456",
  "created_at": "2026-03-28T14:30:00Z"
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |
| 409 | `DUPLICATE_OFFLINE_PAYMENT` | Дублирующий офлайн-платёж (совпадение `external_reference` + `payment_date` + `amount_kopecks`) |

---

### 3.12. GET /campaigns/{campaign_id}/offline-payments

Список офлайн-платежей кампании.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "019523e5-dddd-7def-8a12-abcdef123456",
      "campaign_id": "019523b2-aaaa-7def-8a12-abcdef123456",
      "amount_kopecks": 10000000,
      "payment_method": "bank_transfer",
      "description": "Перевод от ООО Рога и Копыта",
      "external_reference": "PAY-2026-00042",
      "payment_date": "2026-03-25",
      "recorded_by_admin_id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "created_at": "2026-03-28T14:30:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

---

### 3.13. POST /campaigns/{campaign_id}/documents

Добавление документа к кампании.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `title` | string | да | Название документа | -- |
| `file_url` | string | да | URL файла (загрузить через `/media/upload`) | -- |
| `sort_order` | int | нет | Порядок сортировки | По умолчанию 0 |

**Пример запроса:**

```json
{
  "title": "Медицинское заключение",
  "file_url": "https://cdn.porublyu.ru/documents/abc123.pdf",
  "sort_order": 0
}
```

**Успешный ответ (201):**

```json
{
  "id": "019523c3-bbbb-7def-8a12-abcdef123456",
  "title": "Медицинское заключение",
  "file_url": "https://cdn.porublyu.ru/documents/abc123.pdf",
  "sort_order": 0
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

---

### 3.14. DELETE /campaigns/{campaign_id}/documents/{doc_id}

Удаление документа из кампании.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |
| `doc_id` | UUID | Идентификатор документа |

**Тело запроса:** отсутствует.

**Успешный ответ:** `204 No Content` (пустое тело).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Документ не найден |

---

### 3.15. POST /campaigns/{campaign_id}/thanks

Добавление контента благодарности к кампании.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `type` | string | да | Тип контента | `video`, `audio` |
| `media_url` | string | да | URL медиафайла: **`POST /media/upload`** с `type=video` для видео или **`type=audio`** для аудио, затем поле `url` из ответа | -- |
| `title` | string | нет | Заголовок | -- |
| `description` | string | нет | Описание | -- |

**Пример запроса:**

```json
{
  "type": "video",
  "media_url": "https://cdn.porublyu.ru/videos/thanks_masha.mp4",
  "title": "Спасибо от Маши!",
  "description": "Маша записала видео-благодарность всем, кто помогал"
}
```

**Побочные эффекты:**
- Если кампания в статусе `active`, всем донорам отправляется push-уведомление "Благодарность от фонда".

**Успешный ответ (201):**

```json
{
  "id": "019523d4-cccc-7def-8a12-abcdef123456",
  "type": "video",
  "media_url": "https://cdn.porublyu.ru/videos/thanks_masha.mp4",
  "title": "Спасибо от Маши!",
  "description": "Маша записала видео-благодарность всем, кто помогал"
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

---

### 3.16. PATCH /campaigns/{campaign_id}/thanks/{thanks_id}

Обновление контента благодарности.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |
| `thanks_id` | UUID | Идентификатор контента благодарности |

**Тело запроса (все поля опциональные):**

| Поле | Тип | Описание |
|---|---|---|
| `type` | string | Тип контента: `video`, `audio` |
| `media_url` | string | URL медиафайла |
| `title` | string | Заголовок |
| `description` | string | Описание |

**Пример запроса:**

```json
{
  "title": "Обновлённый заголовок"
}
```

**Успешный ответ (200):** обновлённый объект благодарности (формат как в 3.15).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Контент благодарности не найден |

---

### 3.17. DELETE /campaigns/{campaign_id}/thanks/{thanks_id}

Удаление контента благодарности.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |
| `thanks_id` | UUID | Идентификатор контента благодарности |

**Тело запроса:** отсутствует.

**Успешный ответ:** `204 No Content` (пустое тело).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Контент благодарности не найден |

---

## 4. Загрузка медиа и библиотека

Базовый путь: `/media` (полный URL: `/api/v1/admin/media/...`).

### Рекомендуемый флоу для админки (модалка загрузки)

1. Пользователь выбирает файл и тип (`video` / `document` / `audio`).
2. Фронт отправляет **`multipart/form-data`** с полями **`file`** и **`type`**. Не задавайте заголовок `Content-Type` вручную — браузер добавит `boundary`.
3. Из ответа сохраните **`url`** (обязательно для полей кампании/фонда и для благодарностей) и при необходимости **`id`** / **`key`** для справки и повторного использования.
4. Для **благодарности с аудио**: в upload укажите **`type=audio`**, в **`POST .../thanks`** передайте **`type: "audio"`** и **`media_url`** = `url` из ответа upload (не используйте `type=video` для аудиофайла).
5. При сохранении кампании или фонда:
   - либо подставьте **`url`** в `video_url`, `thumbnail_url`, `logo_url` и т.д.;
   - либо передайте **`video_media_asset_id`**, **`thumbnail_media_asset_id`**, **`logo_media_asset_id`** (uuid из поля `id` ответа upload или из списка `GET /media`) — бэкенд сам проставит соответствующий `*_url`. Если в одном запросе указаны и URL, и `*_media_asset_id`, **приоритет у `*_media_asset_id`**.
6. Список ранее загруженных файлов: **`GET /media`** (опционально **`?type=audio`** и т.д.) — чтобы выбрать уже существующий файл без повторной загрузки.
7. Деталка / ссылка «Скачать»: **`GET /media/{id}`** или **`GET /media/{id}/download`** (редирект 302 на публичный URL).

---

### 4.1. POST /media/upload

Загрузка файла в S3 и запись в библиотеку `media_assets`.

**Content-Type:** `multipart/form-data`

**Параметры формы:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `file` | file (binary) | да | Файл для загрузки | См. ограничения ниже |
| `type` | string | да | Тип медиа | `video`, `document` или `audio` |

**Ограничения по типам:**

| Тип | Макс. размер | Допустимые форматы |
|---|---|---|
| `video` | 500 МБ | `video/mp4` |
| `document` | 10 МБ | `application/pdf` |
| `audio` | 50 МБ | `audio/mpeg`, `audio/mp4`, `audio/ogg`, `audio/webm` |

**Пример запроса (curl):**

```bash
curl -X POST \
  https://backend.porublyu.parmenid.tech/api/v1/admin/media/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/video.mp4" \
  -F "type=video"
```

**Успешный ответ (200):**

```json
{
  "id": "0195a1b2-c3d4-7e5f-8a90-abcdef123456",
  "key": "videos/a1b2c3d4e5f6789012345678abcdef.mp4",
  "url": "https://backend.porublyu.parmenid.tech/s3/porubly/videos/a1b2c3d4e5f6789012345678abcdef.mp4",
  "filename": "video.mp4",
  "size_bytes": 15728640,
  "content_type": "video/mp4"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `id` | uuid | Идентификатор в библиотеке медиа |
| `key` | string | Ключ в S3 |
| `url` | string | Публичный URL — копировать в поля сущностей или использовать через `*_media_asset_id` в PATCH |
| `filename` | string | Оригинальное имя файла |
| `size_bytes` | int | Размер файла в байтах |
| `content_type` | string | MIME-тип файла |

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 422 | `INVALID_MEDIA_TYPE` | Тип должен быть `video`, `document` или `audio` |
| 422 | `FILE_TOO_LARGE` | Файл превышает максимальный размер (видео 500 МБ, документ 10 МБ, аудио 50 МБ) |
| 422 | `INVALID_FILE_FORMAT` | Недопустимый MIME для выбранного типа |

---

### 4.2. GET /media

Список загруженных файлов (курсорная пагинация). Query: `limit`, `cursor`, опционально `type` (`video` \| `document` \| `audio`), `search`.

---

### 4.3. GET /media/{id}

Деталь: `url`, `key`, `download_url`, `uploaded_by_admin_id`, метаданные.

---

### 4.4. GET /media/{id}/download

Ответ **302** с `Location` = публичный URL файла.

---

## 5. Управление пользователями

Базовый путь: `/users`

---

### 5.1. GET /users

Список пользователей с фильтрацией и пагинацией.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `role` | string | нет | Фильтр по роли: `donor`, `patron` |
| `search` | string | нет | Поиск по email / имени / телефону |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "019523f6-eeee-7def-8a12-abcdef123456",
      "email": "user@example.com",
      "phone": "+79161234567",
      "name": "Мария Иванова",
      "avatar_url": "https://cdn.porublyu.ru/avatars/user1.jpg",
      "role": "donor",
      "is_active": true,
      "current_streak_days": 45,
      "total_donated_kopecks": 2500000,
      "total_donations_count": 25,
      "created_at": "2025-12-01T10:00:00Z",
      "updated_at": "2026-03-28T08:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJpZCI6IC4uLn0=",
    "has_more": true,
    "total": null
  }
}
```

**Поля объекта пользователя:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор |
| `email` | string | Email |
| `phone` | string \| null | Телефон |
| `name` | string \| null | Имя |
| `avatar_url` | string \| null | URL аватара |
| `role` | string | Роль: `donor`, `patron` |
| `is_active` | bool | Активен ли аккаунт |
| `current_streak_days` | int | Текущий стрик (дни подряд) |
| `total_donated_kopecks` | int | Общая сумма пожертвований (копейки) |
| `total_donations_count` | int | Общее количество пожертвований |
| `created_at` | datetime | Дата регистрации |
| `updated_at` | datetime | Дата последнего обновления |

---

### 5.2. GET /users/{user_id}

Детальная информация о пользователе, включая подписки и последние пожертвования.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `user_id` | UUID | Идентификатор пользователя |

**Успешный ответ (200):**

```json
{
  "id": "019523f6-eeee-7def-8a12-abcdef123456",
  "email": "user@example.com",
  "phone": "+79161234567",
  "name": "Мария Иванова",
  "avatar_url": null,
  "role": "donor",
  "is_active": true,
  "current_streak_days": 45,
  "total_donated_kopecks": 2500000,
  "total_donations_count": 25,
  "created_at": "2025-12-01T10:00:00Z",
  "updated_at": "2026-03-28T08:00:00Z",
  "subscriptions": [
    {
      "id": "01952401-1111-7def-8a12-abcdef123456",
      "amount_kopecks": 300,
      "billing_period": "weekly",
      "allocation_strategy": "platform_pool",
      "campaign_id": null,
      "foundation_id": null,
      "status": "active",
      "next_billing_at": "2026-04-04T10:00:00Z",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "recent_donations": [
    {
      "id": "01952402-2222-7def-8a12-abcdef123456",
      "campaign_id": "019523b2-aaaa-7def-8a12-abcdef123456",
      "amount_kopecks": 2100,
      "status": "success",
      "source": "app",
      "created_at": "2026-03-28T07:00:00Z"
    }
  ]
}
```

**Объект подписки (subscriptions):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор подписки |
| `amount_kopecks` | int | Сумма за день (копейки). Допустимые: 100, 300, 500, 1000 |
| `billing_period` | string | Период списания: `weekly`, `monthly` |
| `allocation_strategy` | string | Стратегия распределения: `platform_pool`, `foundation_pool`, `specific_campaign` |
| `campaign_id` | UUID \| null | ID кампании (если `specific_campaign`) |
| `foundation_id` | UUID \| null | ID фонда (если `foundation_pool`) |
| `status` | string | Статус: `active`, `paused`, `cancelled`, `pending_payment_method` |
| `next_billing_at` | datetime \| null | Дата следующего списания |
| `created_at` | datetime | Дата создания |

**Объект пожертвования (recent_donations):**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор пожертвования |
| `campaign_id` | UUID | ID кампании |
| `amount_kopecks` | int | Сумма (копейки) |
| `status` | string | Статус: `pending`, `success`, `failed`, `refunded` |
| `source` | string | Источник: `app`, `patron_link`, `offline` |
| `created_at` | datetime | Дата создания |

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Пользователь не найден |

---

### 5.3. POST /users/{user_id}/grant-patron

Назначение пользователю роли "patron" (патрон).

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `user_id` | UUID | Идентификатор пользователя |

**Тело запроса:** отсутствует.

**Успешный ответ (200):**

```json
{
  "id": "019523f6-eeee-7def-8a12-abcdef123456",
  "role": "patron"
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Пользователь не найден |

---

### 5.4. POST /users/{user_id}/revoke-patron

Снятие роли "patron" (возврат к "donor").

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `user_id` | UUID | Идентификатор пользователя |

**Тело запроса:** отсутствует.

**Успешный ответ (200):**

```json
{
  "id": "019523f6-eeee-7def-8a12-abcdef123456",
  "role": "donor"
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Пользователь не найден |

---

### 5.5. POST /users/{user_id}/deactivate

Деактивация аккаунта пользователя.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `user_id` | UUID | Идентификатор пользователя |

**Тело запроса:** отсутствует.

**Побочные эффекты:**
- Все refresh-токены пользователя отзываются (мгновенный разлогин).
- Все активные подписки пользователя переводятся в статус `paused`.

**Успешный ответ (200):**

```json
{
  "id": "019523f6-eeee-7def-8a12-abcdef123456",
  "is_active": false
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Пользователь не найден |

---

### 5.6. POST /users/{user_id}/activate

Активация аккаунта пользователя.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `user_id` | UUID | Идентификатор пользователя |

**Тело запроса:** отсутствует.

> **Примечание:** подписки не возобновляются автоматически. Пользователь должен сам возобновить подписки после активации.

**Успешный ответ (200):**

```json
{
  "id": "019523f6-eeee-7def-8a12-abcdef123456",
  "is_active": true
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Пользователь не найден |

---

## 6. Статистика

Базовый путь: `/stats`

---

### 6.1. GET /stats/overview

Общая статистика платформы.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `period_from` | date | нет | Начало периода (`YYYY-MM-DD`). Если не указан -- за всё время |
| `period_to` | date | нет | Конец периода (`YYYY-MM-DD`). Если не указан -- до текущей даты |

**Успешный ответ (200):**

```json
{
  "gmv_kopecks": 125000000,
  "platform_fee_kopecks": 18750000,
  "active_subscriptions": 1245,
  "total_donors": 3210,
  "new_donors_period": 156,
  "retention_30d": 0.72,
  "retention_90d": 0.48,
  "period_from": "2026-01-01",
  "period_to": "2026-03-28"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `gmv_kopecks` | int | Общий объём пожертвований за период (копейки) |
| `platform_fee_kopecks` | int | Комиссия платформы (15% от GMV, копейки) |
| `active_subscriptions` | int | Количество активных подписок |
| `total_donors` | int | Общее количество доноров |
| `new_donors_period` | int | Новых доноров за период |
| `retention_30d` | float | Retention 30 дней (доля от 0 до 1) |
| `retention_90d` | float | Retention 90 дней (доля от 0 до 1) |
| `period_from` | date \| null | Начало периода |
| `period_to` | date \| null | Конец периода |

---

### 6.2. GET /stats/campaigns/{campaign_id}

Статистика по конкретной кампании.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | Идентификатор кампании |

**Успешный ответ (200):**

```json
{
  "campaign_id": "019523b2-aaaa-7def-8a12-abcdef123456",
  "campaign_title": "Сбор на лечение Маши",
  "collected_amount": 12345600,
  "donors_count": 234,
  "average_check_kopecks": 52760,
  "subscriptions_count": 89,
  "donations_count": 312,
  "offline_payments_amount": 5000000
}
```

| Поле | Тип | Описание |
|---|---|---|
| `campaign_id` | UUID | ID кампании |
| `campaign_title` | string | Название кампании |
| `collected_amount` | int | Собранная сумма (копейки) |
| `donors_count` | int | Количество уникальных доноров |
| `average_check_kopecks` | int | Средний чек (копейки) |
| `subscriptions_count` | int | Количество активных подписок на кампанию |
| `donations_count` | int | Общее количество пожертвований |
| `offline_payments_amount` | int | Сумма офлайн-платежей (копейки) |

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Кампания не найдена |

---

## 7. Выплаты фондам

Базовый путь: `/payouts`

---

### 7.1. GET /payouts

Список выплат фондам.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `foundation_id` | UUID | нет | Фильтр по фонду |
| `period_from` | date | нет | Начало периода (`YYYY-MM-DD`) |
| `period_to` | date | нет | Конец периода (`YYYY-MM-DD`) |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "01952410-3333-7def-8a12-abcdef123456",
      "foundation_id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "foundation_name": "Фонд помощи детям",
      "amount_kopecks": 85000000,
      "period_from": "2026-02-01",
      "period_to": "2026-02-28",
      "transfer_reference": "PP-2026-0015",
      "note": "Выплата за февраль",
      "created_by_admin_id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "created_at": "2026-03-05T10:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Поля объекта выплаты:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор выплаты |
| `foundation_id` | UUID | ID фонда |
| `foundation_name` | string \| null | Название фонда |
| `amount_kopecks` | int | Сумма выплаты (копейки) |
| `period_from` | date | Начало периода выплаты |
| `period_to` | date | Конец периода выплаты |
| `transfer_reference` | string \| null | Номер платёжного поручения |
| `note` | string \| null | Примечание |
| `created_by_admin_id` | UUID | ID администратора, создавшего выплату |
| `created_at` | datetime | Дата создания |

---

### 7.2. POST /payouts

Создание записи о выплате фонду.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `foundation_id` | UUID | да | ID фонда | Фонд должен существовать |
| `amount_kopecks` | int | да | Сумма выплаты (копейки) | > 0 |
| `period_from` | date | да | Начало периода | `YYYY-MM-DD` |
| `period_to` | date | да | Конец периода | `YYYY-MM-DD` |
| `transfer_reference` | string | нет | Номер платёжного поручения | -- |
| `note` | string | нет | Примечание | -- |

**Пример запроса:**

```json
{
  "foundation_id": "019523a1-7b4c-7def-8a12-abcdef123456",
  "amount_kopecks": 85000000,
  "period_from": "2026-02-01",
  "period_to": "2026-02-28",
  "transfer_reference": "PP-2026-0015",
  "note": "Выплата за февраль"
}
```

**Успешный ответ (201):** объект выплаты (формат см. в 7.1, без `foundation_name`).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Фонд не найден |

---

### 7.3. GET /payouts/balance

Баланс по фондам: сколько получено, сколько выплачено, сколько задолженность.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `period_from` | date | нет | Начало периода |
| `period_to` | date | нет | Конец периода |

**Успешный ответ (200):**

```json
{
  "balances": [
    {
      "foundation_id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "foundation_name": "Фонд помощи детям",
      "total_nco_kopecks": 106250000,
      "total_paid_kopecks": 85000000,
      "due_kopecks": 21250000
    },
    {
      "foundation_id": "019523a1-8888-7def-8a12-abcdef999999",
      "foundation_name": "Фонд защиты животных",
      "total_nco_kopecks": 45000000,
      "total_paid_kopecks": 45000000,
      "due_kopecks": 0
    }
  ]
}
```

| Поле | Тип | Описание |
|---|---|---|
| `foundation_id` | UUID | ID фонда |
| `foundation_name` | string | Название фонда |
| `total_nco_kopecks` | int | Общая сумма, причитающаяся фонду (GMV - комиссия платформы 15%) |
| `total_paid_kopecks` | int | Уже выплаченная сумма |
| `due_kopecks` | int | Задолженность перед фондом |

---

## 8. Достижения

Базовый путь: `/achievements`

---

### 8.1. GET /achievements

Список всех достижений (без пагинации).

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "01952420-4444-7def-8a12-abcdef123456",
      "code": "streak_7",
      "title": "Неделя добра",
      "description": "7 дней подряд пожертвований",
      "icon_url": "https://cdn.porublyu.ru/achievements/streak7.png",
      "condition_type": "streak_days",
      "condition_value": 7,
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z"
    },
    {
      "id": "01952420-5555-7def-8a12-abcdef123456",
      "code": "total_10k",
      "title": "Щедрая душа",
      "description": "Пожертвовано более 100 рублей",
      "icon_url": "https://cdn.porublyu.ru/achievements/total10k.png",
      "condition_type": "total_amount_kopecks",
      "condition_value": 10000,
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

**Поля объекта достижения:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор |
| `code` | string | Уникальный код достижения |
| `title` | string | Название |
| `description` | string \| null | Описание |
| `icon_url` | string \| null | URL иконки |
| `condition_type` | string | Тип условия: `streak_days`, `total_amount_kopecks`, `donations_count` |
| `condition_value` | int | Значение условия (дни / копейки / количество) |
| `is_active` | bool | Активно ли достижение |
| `created_at` | datetime | Дата создания |

---

### 8.2. POST /achievements

Создание нового достижения.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `code` | string | да | Уникальный код | Уникальное значение |
| `title` | string | да | Название | -- |
| `description` | string | нет | Описание | -- |
| `icon_url` | string | нет | URL иконки | -- |
| `condition_type` | string | да | Тип условия | `streak_days`, `total_amount_kopecks`, `donations_count` |
| `condition_value` | int | да | Значение порога | > 0 |

**Пример запроса:**

```json
{
  "code": "streak_30",
  "title": "Месяц добра",
  "description": "30 дней подряд пожертвований",
  "icon_url": "https://cdn.porublyu.ru/achievements/streak30.png",
  "condition_type": "streak_days",
  "condition_value": 30
}
```

**Успешный ответ (201):** объект достижения (формат см. в 8.1).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 409 | `ACHIEVEMENT_CODE_EXISTS` | Достижение с таким кодом уже существует |

---

### 8.3. PATCH /achievements/{achievement_id}

Обновление достижения.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `achievement_id` | UUID | Идентификатор достижения |

**Тело запроса (все поля опциональные):**

| Поле | Тип | Описание |
|---|---|---|
| `code` | string | Уникальный код |
| `title` | string | Название |
| `description` | string | Описание |
| `icon_url` | string | URL иконки |
| `condition_type` | string | Тип условия |
| `condition_value` | int | Значение порога |
| `is_active` | bool | Активно ли достижение |

**Пример запроса:**

```json
{
  "is_active": false
}
```

**Успешный ответ (200):** обновлённый объект достижения.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Достижение не найдено |
| 409 | `ACHIEVEMENT_CODE_EXISTS` | Новый код уже занят |

---

## 9. Логи

Базовый путь: `/logs`

---

### 9.1. GET /logs/allocation-logs

Журнал реаллокаций подписок (переключение подписки с одной кампании на другую).

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `subscription_id` | UUID | нет | Фильтр по подписке |
| `reason` | string | нет | Фильтр по причине: `campaign_completed`, `campaign_closed_early`, `no_campaigns_in_foundation`, `no_campaigns_on_platform`, `manual_by_admin` |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "01952430-6666-7def-8a12-abcdef123456",
      "subscription_id": "01952401-1111-7def-8a12-abcdef123456",
      "from_campaign_id": "019523b2-aaaa-7def-8a12-abcdef123456",
      "from_campaign_title": "Сбор на лечение Маши",
      "to_campaign_id": "019523b2-bbbb-7def-8a12-abcdef789012",
      "to_campaign_title": "Сбор на школу",
      "reason": "campaign_completed",
      "notified_at": "2026-03-27T15:00:00Z",
      "created_at": "2026-03-27T14:59:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Поля объекта лога реаллокации:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор записи |
| `subscription_id` | UUID | ID подписки |
| `from_campaign_id` | UUID \| null | ID прежней кампании |
| `from_campaign_title` | string \| null | Название прежней кампании |
| `to_campaign_id` | UUID \| null | ID новой кампании (`null` если не удалось реаллоцировать) |
| `to_campaign_title` | string \| null | Название новой кампании |
| `reason` | string | Причина реаллокации |
| `notified_at` | datetime \| null | Когда пользователь был уведомлён |
| `created_at` | datetime | Дата реаллокации |

**Возможные значения `reason`:**

| Значение | Описание |
|---|---|
| `campaign_completed` | Кампания завершена |
| `campaign_closed_early` | Кампания закрыта досрочно |
| `no_campaigns_in_foundation` | Нет активных кампаний в фонде |
| `no_campaigns_on_platform` | Нет активных кампаний на платформе |
| `manual_by_admin` | Ручная реаллокация администратором |

---

### 9.2. GET /logs/notification-logs

Журнал push-уведомлений.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `user_id` | UUID | нет | Фильтр по пользователю |
| `notification_type` | string | нет | Фильтр по типу: `campaign_completed`, `thanks_content`, `payment_success` и др. |
| `status` | string | нет | Фильтр по статусу: `sent`, `mock`, `failed` |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "01952440-7777-7def-8a12-abcdef123456",
      "user_id": "019523f6-eeee-7def-8a12-abcdef123456",
      "push_token": "ExponentPushToken[abc123...]",
      "notification_type": "campaign_completed",
      "title": "Сбор завершён",
      "body": "Кампания \"Сбор на лечение Маши\" завершена",
      "data": {
        "type": "campaign_closed",
        "campaign_id": "019523b2-aaaa-7def-8a12-abcdef123456",
        "closed_early": false
      },
      "status": "sent",
      "provider_response": null,
      "created_at": "2026-03-27T15:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Поля объекта лога уведомления:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор записи |
| `user_id` | UUID \| null | ID пользователя |
| `push_token` | string \| null | Push-токен устройства |
| `notification_type` | string | Тип уведомления |
| `title` | string | Заголовок уведомления |
| `body` | string | Текст уведомления |
| `data` | object \| null | Payload данных (JSON) |
| `status` | string | Статус доставки: `sent`, `mock`, `failed` |
| `provider_response` | string \| null | Ответ провайдера (при ошибке) |
| `created_at` | datetime | Дата отправки |

---

## 10. Управление администраторами

Базовый путь: `/admins`

---

### 10.1. GET /admins

Список администраторов.

**Query-параметры:**

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `is_active` | bool | нет | Фильтр по статусу активности |
| `limit` | int | нет | Записей на странице (1-100, по умолчанию 20) |
| `cursor` | string | нет | Курсор пагинации |

**Успешный ответ (200):**

```json
{
  "data": [
    {
      "id": "019523a1-7b4c-7def-8a12-abcdef123456",
      "email": "admin@porublyu.ru",
      "name": "Иван Петров",
      "is_active": true,
      "created_at": "2025-11-01T10:00:00Z",
      "updated_at": "2026-03-01T12:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

**Поля объекта администратора:**

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Идентификатор |
| `email` | string | Email |
| `name` | string \| null | Имя |
| `is_active` | bool | Активен ли аккаунт |
| `created_at` | datetime | Дата создания |
| `updated_at` | datetime | Дата последнего обновления |

---

### 10.2. POST /admins

Создание нового администратора.

**Тело запроса:**

| Поле | Тип | Обязательное | Описание | Ограничения |
|---|---|---|---|---|
| `email` | string (email) | да | Email | Уникальный, валидный email |
| `password` | string | да | Пароль | -- |
| `name` | string | нет | Имя | -- |

**Пример запроса:**

```json
{
  "email": "new_admin@porublyu.ru",
  "password": "StrongP@ssw0rd!",
  "name": "Анна Сидорова"
}
```

**Успешный ответ (201):** объект администратора (формат см. в 10.1).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 409 | `ADMIN_EMAIL_EXISTS` | Администратор с таким email уже существует |

---

### 10.3. GET /admins/{admin_id}

Детали администратора.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `admin_id` | UUID | Идентификатор администратора |

**Успешный ответ (200):** объект администратора (формат см. в 10.1).

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Администратор не найден |

---

### 10.4. PATCH /admins/{admin_id}

Обновление данных администратора.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `admin_id` | UUID | Идентификатор администратора |

**Тело запроса (все поля опциональные):**

| Поле | Тип | Описание | Ограничения |
|---|---|---|---|
| `name` | string | Имя | -- |
| `email` | string (email) | Email | Уникальный |
| `password` | string | Новый пароль | -- |

**Пример запроса:**

```json
{
  "name": "Обновлённое имя"
}
```

**Успешный ответ (200):** обновлённый объект администратора.

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Администратор не найден |
| 409 | `ADMIN_EMAIL_EXISTS` | Новый email уже занят |

---

### 10.5. POST /admins/{admin_id}/deactivate

Деактивация администратора.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `admin_id` | UUID | Идентификатор администратора |

**Тело запроса:** отсутствует.

**Бизнес-правила:**
- Нельзя деактивировать собственный аккаунт.
- При деактивации все refresh-токены администратора отзываются.

**Успешный ответ (200):**

```json
{
  "id": "019523a1-9999-7def-8a12-abcdef123456",
  "is_active": false
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 403 | `FORBIDDEN` | Попытка деактивировать собственный аккаунт |
| 404 | `NOT_FOUND` | Администратор не найден |

---

### 10.6. POST /admins/{admin_id}/activate

Активация администратора.

**Path-параметры:**

| Параметр | Тип | Описание |
|---|---|---|
| `admin_id` | UUID | Идентификатор администратора |

**Тело запроса:** отсутствует.

**Успешный ответ (200):**

```json
{
  "id": "019523a1-9999-7def-8a12-abcdef123456",
  "is_active": true
}
```

**Ошибки:**

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 404 | `NOT_FOUND` | Администратор не найден |

---

## 11. Полный справочник ошибок

### HTTP-коды ответов

| HTTP код | Значение |
|---|---|
| 200 | Успешный запрос |
| 201 | Ресурс создан |
| 204 | Успешно, тело ответа отсутствует |
| 400 | Некорректный запрос |
| 401 | Не авторизован / токен невалиден |
| 403 | Доступ запрещён |
| 404 | Ресурс не найден |
| 409 | Конфликт (дубликат) |
| 422 | Ошибка валидации / бизнес-логики |

### Коды ошибок приложения

| Код ошибки | HTTP код | Описание | Где возникает |
|---|---|---|---|
| `NOT_FOUND` | 404 | Запрашиваемый ресурс не найден | Все GET/PATCH/POST по ID |
| `CONFLICT` | 409 | Общий конфликт | -- |
| `FORBIDDEN` | 403 | Доступ запрещён | Деактивация собственного аккаунта |
| `INVALID_CREDENTIALS` | 401 | Неверный email или пароль | POST /auth/login |
| `ACCOUNT_DISABLED` | 403 | Аккаунт деактивирован | POST /auth/login |
| `TOKEN_EXPIRED` | 401 | Токен истёк | POST /auth/refresh |
| `TOKEN_REVOKED` | 401 | Токен отозван | POST /auth/refresh |
| `INN_ALREADY_EXISTS` | 409 | ИНН уже зарегистрирован | POST/PATCH /foundations |
| `INVALID_STATUS_TRANSITION` | 422 | Недопустимый переход статуса кампании | POST /campaigns/{id}/publish, pause, complete, close-early, archive |
| `DUPLICATE_OFFLINE_PAYMENT` | 409 | Дублирующий офлайн-платёж | POST /campaigns/{id}/offline-payment |
| `INVALID_MEDIA_TYPE` | 422 | Тип медиа должен быть video, document или audio | POST /media/upload |
| `FILE_TOO_LARGE` | 422 | Файл превышает лимит (видео 500 МБ, документ 10 МБ, аудио 50 МБ) | POST /media/upload |
| `INVALID_FILE_FORMAT` | 422 | Недопустимый MIME-тип файла | POST /media/upload |
| `ACHIEVEMENT_CODE_EXISTS` | 409 | Код достижения уже существует | POST/PATCH /achievements |
| `ADMIN_EMAIL_EXISTS` | 409 | Email администратора уже занят | POST/PATCH /admins |

---

## 12. Сводная таблица всех эндпоинтов

| # | Метод | Путь | Описание | Авторизация |
|---|---|---|---|---|
| 1 | POST | `/auth/login` | Вход администратора | Нет |
| 2 | POST | `/auth/refresh` | Обновление токенов | Нет |
| 3 | POST | `/auth/logout` | Выход (отзыв токена) | Нет |
| 4 | GET | `/foundations` | Список фондов | Bearer |
| 5 | POST | `/foundations` | Создание фонда | Bearer |
| 6 | GET | `/foundations/{foundation_id}` | Детали фонда | Bearer |
| 7 | PATCH | `/foundations/{foundation_id}` | Обновление фонда | Bearer |
| 8 | GET | `/campaigns` | Список кампаний | Bearer |
| 9 | POST | `/campaigns` | Создание кампании | Bearer |
| 10 | GET | `/campaigns/{campaign_id}` | Детали кампании | Bearer |
| 11 | PATCH | `/campaigns/{campaign_id}` | Обновление кампании | Bearer |
| 12 | POST | `/campaigns/{campaign_id}/publish` | Публикация кампании | Bearer |
| 13 | POST | `/campaigns/{campaign_id}/pause` | Приостановка кампании | Bearer |
| 14 | POST | `/campaigns/{campaign_id}/complete` | Завершение кампании | Bearer |
| 15 | POST | `/campaigns/{campaign_id}/close-early` | Досрочное закрытие кампании | Bearer |
| 16 | POST | `/campaigns/{campaign_id}/archive` | Архивация кампании | Bearer |
| 17 | POST | `/campaigns/{campaign_id}/force-realloc` | Принудительная реаллокация подписок | Bearer |
| 18 | POST | `/campaigns/{campaign_id}/offline-payment` | Регистрация офлайн-платежа | Bearer |
| 19 | GET | `/campaigns/{campaign_id}/offline-payments` | Список офлайн-платежей | Bearer |
| 20 | POST | `/campaigns/{campaign_id}/documents` | Добавление документа | Bearer |
| 21 | DELETE | `/campaigns/{campaign_id}/documents/{doc_id}` | Удаление документа | Bearer |
| 22 | POST | `/campaigns/{campaign_id}/thanks` | Добавление благодарности | Bearer |
| 23 | PATCH | `/campaigns/{campaign_id}/thanks/{thanks_id}` | Обновление благодарности | Bearer |
| 24 | DELETE | `/campaigns/{campaign_id}/thanks/{thanks_id}` | Удаление благодарности | Bearer |
| 25 | POST | `/media/upload` | Загрузка файла | Bearer |
| 26 | GET | `/users` | Список пользователей | Bearer |
| 27 | GET | `/users/{user_id}` | Детали пользователя | Bearer |
| 28 | POST | `/users/{user_id}/grant-patron` | Назначение роли patron | Bearer |
| 29 | POST | `/users/{user_id}/revoke-patron` | Снятие роли patron | Bearer |
| 30 | POST | `/users/{user_id}/deactivate` | Деактивация пользователя | Bearer |
| 31 | POST | `/users/{user_id}/activate` | Активация пользователя | Bearer |
| 32 | GET | `/stats/overview` | Общая статистика | Bearer |
| 33 | GET | `/stats/campaigns/{campaign_id}` | Статистика кампании | Bearer |
| 34 | GET | `/payouts` | Список выплат | Bearer |
| 35 | POST | `/payouts` | Создание выплаты | Bearer |
| 36 | GET | `/payouts/balance` | Баланс по фондам | Bearer |
| 37 | GET | `/achievements` | Список достижений | Bearer |
| 38 | POST | `/achievements` | Создание достижения | Bearer |
| 39 | PATCH | `/achievements/{achievement_id}` | Обновление достижения | Bearer |
| 40 | GET | `/logs/allocation-logs` | Логи реаллокаций | Bearer |
| 41 | GET | `/logs/notification-logs` | Логи уведомлений | Bearer |
| 42 | GET | `/admins` | Список администраторов | Bearer |
| 43 | POST | `/admins` | Создание администратора | Bearer |
| 44 | GET | `/admins/{admin_id}` | Детали администратора | Bearer |
| 45 | PATCH | `/admins/{admin_id}` | Обновление администратора | Bearer |
| 46 | POST | `/admins/{admin_id}/deactivate` | Деактивация администратора | Bearer |
| 47 | POST | `/admins/{admin_id}/activate` | Активация администратора | Bearer |
