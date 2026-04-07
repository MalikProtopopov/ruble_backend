# Лента кампаний — руководство для мобильного приложения

API ленты кампаний, фильтрация по статусу, отображение завершённых сборов.

---

## 1. Эндпоинт

**GET** `/api/v1/campaigns`

Авторизация: не требуется.

### Query-параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|:---:|----------|
| `status` | string | `active` | `active` — текущие сборы, `completed` — завершённые |
| `limit` | int | 20 | 1–100 |
| `cursor` | string | — | Курсор для следующей страницы |

### Ответ (200)

```json
{
  "data": [
    {
      "id": "019...",
      "foundation_id": "019...",
      "foundation": {
        "id": "019...",
        "name": "Фонд помощи",
        "logo_url": "https://backend.porublyu.parmenid.tech/media/images/logo.png"
      },
      "title": "Помощь детям",
      "description": "Сбор на лечение...",
      "thumbnail_url": "https://backend.porublyu.parmenid.tech/media/images/thumb.jpg",
      "status": "active",
      "goal_amount": 1000000,
      "collected_amount": 750000,
      "donors_count": 42,
      "urgency_level": 4,
      "is_permanent": false,
      "ends_at": "2026-05-01T00:00:00Z",
      "created_at": "2026-03-01T10:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "eyJjcmVhdGVkX2F0IjogIi4uLiJ9",
    "has_more": true,
    "total": null
  }
}
```

---

## 2. Поля кампании

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | ID кампании |
| `foundation_id` | UUID | ID фонда |
| `foundation` | object | `{ id, name, logo_url }` |
| `title` | string | Название |
| `description` | string \| null | Описание |
| `thumbnail_url` | string \| null | Превью-картинка |
| `status` | string | **`active`** или **`completed`** |
| `goal_amount` | int \| null | Цель в копейках (`null` = бессрочный) |
| `collected_amount` | int | Собрано в копейках |
| `donors_count` | int | Количество жертвователей |
| `urgency_level` | int | Срочность 1–5 |
| `is_permanent` | bool | Бессрочный сбор |
| `ends_at` | datetime \| null | Дата окончания |
| `created_at` | datetime | Дата создания |

### Деталь кампании

**GET** `/api/v1/campaigns/{campaign_id}`

Возвращает все поля из списка + дополнительные:

| Поле | Тип | Описание |
|------|-----|----------|
| `video_url` | string \| null | Видео кампании |
| `closed_early` | bool | Закрыта досрочно |
| `close_note` | string \| null | Причина досрочного закрытия |
| `documents` | array | Документы кампании `[{ id, title, file_url, sort_order }]` |
| `thanks_contents` | array | Благодарности `[{ id, type, media_url, title, description }]` |

Доступны кампании со статусом `active` и `completed`.

---

## 3. Сортировка

| Статус | Порядок сортировки |
|--------|-------------------|
| `active` | По срочности (urgency_level DESC), затем по прогрессу сбора (% от цели DESC), затем sort_order |
| `completed` | По дате завершения (updated_at DESC) — последние завершённые первыми |

---

## 4. Суммы в копейках

Все суммы приходят в **копейках**. Для отображения в рублях:

```ts
function formatAmount(kopecks: number): string {
  return `${(kopecks / 100).toLocaleString("ru-RU")} ₽`;
}

// 1000000 → "10 000 ₽"
// 750000  → "7 500 ₽"
```

### Прогресс сбора

```ts
function getProgress(campaign: Campaign): number | null {
  if (!campaign.goal_amount || campaign.goal_amount === 0) return null;
  return Math.min(campaign.collected_amount / campaign.goal_amount, 1);
}

// Для прогресс-бара: getProgress(campaign) * 100 + "%"
```

---

## 5. Интеграция в приложении

### 5.1. Два таба / сегмента

```
┌──────────────┬──────────────┐
│   Активные   │  Завершённые │
└──────────────┴──────────────┘
```

```ts
const [activeTab, setActiveTab] = useState<"active" | "completed">("active");

// Запрос
const { data } = useQuery({
  queryKey: ["campaigns", activeTab, cursor],
  queryFn: () => api.get("/api/v1/campaigns", {
    params: { status: activeTab, limit: 20, cursor },
  }),
});
```

### 5.2. Карточка кампании

```
┌─────────────────────────────────────┐
│  ┌───────────┐                      │
│  │ thumbnail │  Помощь детям        │
│  │           │  Фонд помощи        │
│  └───────────┘                      │
│                                     │
│  ████████████░░░░  75%              │  ← прогресс-бар
│  7 500 ₽ из 10 000 ₽               │
│  42 жертвователя                    │
│                                     │
│  Срочность: ●●●●○                   │  ← urgency_level
│                                     │
└─────────────────────────────────────┘
```

Для завершённых кампаний:
- Показать бейдж **«Завершён»** (зелёный если цель достигнута, серый если нет)
- Прогресс-бар на 100% или финальный процент
- Убрать кнопку «Пожертвовать»

### 5.3. Определение состояния

```ts
function isGoalReached(campaign: Campaign): boolean {
  if (!campaign.goal_amount) return false;
  return campaign.collected_amount >= campaign.goal_amount;
}

function getCampaignBadge(campaign: Campaign): { text: string; color: string } | null {
  if (campaign.status === "completed") {
    return isGoalReached(campaign)
      ? { text: "Цель достигнута", color: "green" }
      : { text: "Завершён", color: "gray" };
  }
  if (campaign.is_permanent) {
    return { text: "Бессрочный", color: "blue" };
  }
  return null;
}
```

### 5.4. Пагинация (курсорная)

```ts
const [items, setItems] = useState<Campaign[]>([]);
const [cursor, setCursor] = useState<string | null>(null);
const [hasMore, setHasMore] = useState(true);

async function loadMore() {
  const response = await api.get("/api/v1/campaigns", {
    params: { status: activeTab, limit: 20, cursor },
  });

  setItems((prev) => [...prev, ...response.data.data]);
  setCursor(response.data.pagination.next_cursor);
  setHasMore(response.data.pagination.has_more);
}

// При смене таба — сбросить список
useEffect(() => {
  setItems([]);
  setCursor(null);
  setHasMore(true);
  loadMore();
}, [activeTab]);
```

---

## 6. Типы данных

### TypeScript

```ts
interface FoundationBrief {
  id: string;
  name: string;
  logo_url: string | null;
}

interface Campaign {
  id: string;
  foundation_id: string;
  foundation: FoundationBrief | null;
  title: string;
  description: string | null;
  thumbnail_url: string | null;
  status: "active" | "completed";
  goal_amount: number | null;    // копейки
  collected_amount: number;      // копейки
  donors_count: number;
  urgency_level: number;         // 1-5
  is_permanent: boolean;
  ends_at: string | null;        // ISO 8601
  created_at: string;
}

interface CampaignDetail extends Campaign {
  video_url: string | null;
  closed_early: boolean;
  close_note: string | null;
  documents: CampaignDocument[];
  thanks_contents: ThanksContentBrief[];
}

interface CampaignDocument {
  id: string;
  title: string;
  file_url: string;
  sort_order: number;
}

interface ThanksContentBrief {
  id: string;
  type: "video" | "audio";
  media_url: string;
  title: string | null;
  description: string | null;
}
```

### Dart/Flutter

```dart
class FoundationBrief {
  final String id;
  final String name;
  final String? logoUrl;
}

class Campaign {
  final String id;
  final String foundationId;
  final FoundationBrief? foundation;
  final String title;
  final String? description;
  final String? thumbnailUrl;
  final String status;       // "active" | "completed"
  final int? goalAmount;     // копейки
  final int collectedAmount; // копейки
  final int donorsCount;
  final int urgencyLevel;    // 1-5
  final bool isPermanent;
  final DateTime? endsAt;
  final DateTime createdAt;
}
```

---

## 7. Чеклист

1. **Два таба** — `active` и `completed` с query-параметром `status`
2. **Курсорная пагинация** — `cursor` + `has_more`, infinite scroll или «Загрузить ещё»
3. **Суммы в копейках** — делить на 100 для отображения в рублях
4. **Прогресс-бар** — `collected_amount / goal_amount`, учесть `goal_amount = null` (бессрочный)
5. **Бейджи** — «Завершён» / «Цель достигнута» / «Бессрочный»
6. **Карточка** — thumbnail, название, фонд, прогресс, donors_count
7. **Деталь** — видео, документы, благодарности, close_note если закрыт досрочно
8. **Кнопка «Пожертвовать»** — скрыть для `completed`
9. **Сброс при смене таба** — очистить список и курсор
