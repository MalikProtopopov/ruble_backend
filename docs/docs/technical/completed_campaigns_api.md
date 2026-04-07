# Получение завершённых кампаний — API

## Эндпоинт

**GET** `/api/v1/campaigns?status=completed`

Авторизация: не требуется.

## Query-параметры

| Параметр | Тип | Обязательный | По умолчанию | Описание |
|----------|-----|:---:|:---:|----------|
| `status` | string | нет | `active` | **`completed`** — завершённые сборы |
| `limit` | int | нет | 20 | Количество элементов (1–100) |
| `cursor` | string | нет | — | Курсор для следующей страницы |

## Пример запроса

```bash
curl "https://backend.porublyu.parmenid.tech/api/v1/campaigns?status=completed&limit=10"
```

## Ответ (200)

```json
{
  "data": [
    {
      "id": "019d3609-6008-7131-b7d5-f5e5ee297715",
      "foundation_id": "019d3608-a1b2-7000-8000-000000000001",
      "foundation": {
        "id": "019d3608-a1b2-7000-8000-000000000001",
        "name": "Фонд помощи",
        "logo_url": "https://backend.porublyu.parmenid.tech/media/images/logo.png"
      },
      "title": "Помощь детям",
      "description": "Сбор средств на лечение",
      "thumbnail_url": "https://backend.porublyu.parmenid.tech/media/images/thumb.jpg",
      "status": "completed",
      "goal_amount": 1000000,
      "collected_amount": 9770500,
      "donors_count": 5,
      "urgency_level": 4,
      "is_permanent": false,
      "ends_at": null,
      "created_at": "2026-03-29T10:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": null,
    "has_more": false,
    "total": null
  }
}
```

## Поля ответа

Все суммы — в **копейках** (делить на 100 для отображения в рублях).

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | ID кампании |
| `foundation_id` | UUID | ID фонда |
| `foundation` | object | `{ id, name, logo_url }` |
| `title` | string | Название кампании |
| `description` | string \| null | Описание |
| `thumbnail_url` | string \| null | Превью-картинка |
| `status` | string | Всегда `"completed"` в этой выборке |
| `goal_amount` | int \| null | Цель сбора в копейках |
| `collected_amount` | int | Собрано в копейках |
| `donors_count` | int | Количество уникальных жертвователей |
| `urgency_level` | int | Срочность 1–5 |
| `is_permanent` | bool | Бессрочный сбор (у завершённых обычно `false`) |
| `ends_at` | datetime \| null | Дата окончания |
| `created_at` | datetime | Дата создания |

## Сортировка

Завершённые кампании отсортированы по **дате завершения** (`updated_at DESC`) — последние завершённые первыми.

## Пагинация

Курсорная. Если `has_more: true`, передать `cursor` из `pagination.next_cursor` в следующий запрос:

```
GET /api/v1/campaigns?status=completed&limit=10&cursor=eyJjcmVhdGVkX2F0IjogIi4uLiJ9
```

## Деталь завершённой кампании

**GET** `/api/v1/campaigns/{id}`

Работает и для `completed`, и для `active`. Возвращает дополнительные поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `video_url` | string \| null | Видео кампании |
| `closed_early` | bool | `true` если закрыта досрочно админом |
| `close_note` | string \| null | Причина досрочного закрытия |
| `documents` | array | Документы `[{ id, title, file_url, sort_order }]` |
| `thanks_contents` | array | Благодарности `[{ id, type, media_url, title, description }]` |
