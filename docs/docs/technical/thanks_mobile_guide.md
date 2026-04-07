# Благодарности от фондов — руководство для мобильного приложения

Полное описание системы благодарностей: API, модели данных, сценарии интеграции, UX-рекомендации.

---

## 1. Что это

Фонды записывают видео или аудио с благодарностью для жертвователей и прикрепляют к кампании. Каждый пользователь, который донатил в эту кампанию, получает возможность **один раз** просмотреть/прослушать благодарность. После просмотра она больше не показывается.

**Ключевые принципы:**
- Благодарность привязана к **кампании**, а не к конкретному платежу
- Пользователь видит благодарности только по кампаниям, в которые **он лично донатил** (разовые или подписки)
- Просмотр фиксируется на уровне **пользователя** (не устройства) — посмотрел на одном телефоне, на другом тоже не покажется
- Нет WebSocket/SSE — используется обычный HTTP-запрос для проверки

---

## 2. API

Авторизация: `Authorization: Bearer <access_token>`. Роль: любой аутентифицированный пользователь (donor/patron).

### 2.1. Получить непросмотренные благодарности

**GET** `/api/v1/thanks/unseen`

Возвращает массив благодарностей, которые пользователь ещё не просматривал.

**Ответ (200):**

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
      "donations_count": 3
    },
    "created_at": "2026-03-31T16:00:00Z"
  }
]
```

**Примечания:**
- Возвращает **массив**, не обёрнутый в `{ data: [...] }` — просто `[...]`
- Если непросмотренных нет — пустой массив `[]`
- Отсортирован по `created_at DESC` (новые первые)
- `user_contribution` содержит суммарный вклад пользователя в кампанию (все донаты + подписки)

### 2.2. Получить деталь благодарности (и пометить как просмотренную)

**GET** `/api/v1/thanks/{thanks_id}`

**Важно:** Сам вызов этого эндпоинта **автоматически помечает** благодарность как просмотренную. Отдельного `POST /mark-as-read` нет и не нужно.

**Ответ (200):**

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
    "first_donation_at": "2026-01-01T10:00:00Z",
    "last_donation_at": "2026-03-15T14:30:00Z"
  }
}
```

**Ошибки:**

| HTTP | Описание |
|:---:|----------|
| 404 | Благодарность не найдена |
| 401 | Не авторизован |

---

## 3. Модели данных

### 3.1. UnseenThanksItem (элемент списка)

| Поле | Тип | Nullable | Описание |
|------|-----|:---:|----------|
| `id` | UUID | нет | ID благодарности |
| `campaign_id` | UUID | нет | ID кампании |
| `campaign_title` | string | нет | Название кампании |
| `foundation_name` | string | нет | Название фонда |
| `type` | string | нет | `"video"` или `"audio"` |
| `media_url` | string | нет | Прямой URL на медиафайл |
| `title` | string | да | Заголовок благодарности |
| `description` | string | да | Текстовое описание |
| `user_contribution` | object | нет | Вклад пользователя (см. ниже) |
| `created_at` | datetime | нет | Дата создания благодарности |

### 3.2. ThanksResponse (деталь)

Все поля из `UnseenThanksItem` (кроме `created_at`) плюс:

| Поле | Тип | Nullable | Описание |
|------|-----|:---:|----------|
| `foundation_id` | UUID | нет | ID фонда |

И расширенный `user_contribution` с дополнительными полями.

### 3.3. UserContribution

| Поле | Тип | Описание |
|------|-----|----------|
| `total_donated_kopecks` | int | Сумма всех донатов в копейках |
| `donations_count` | int | Количество донатов |
| `first_donation_at` | datetime \| null | Дата первого доната (только в детали) |
| `last_donation_at` | datetime \| null | Дата последнего доната (только в детали) |

**Перевод в рубли:** `total_donated_kopecks / 100`. Например, `50000` → `500 ₽`.

### 3.4. Типы данных (TypeScript)

```ts
interface UserContribution {
  total_donated_kopecks: number;
  donations_count: number;
  first_donation_at?: string | null;  // ISO 8601
  last_donation_at?: string | null;
}

interface UnseenThanksItem {
  id: string;
  campaign_id: string;
  campaign_title: string;
  foundation_name: string;
  type: "video" | "audio";
  media_url: string;
  title: string | null;
  description: string | null;
  user_contribution: UserContribution;
  created_at: string;
}

interface ThanksDetail {
  id: string;
  campaign_id: string;
  campaign_title: string;
  foundation_id: string;
  foundation_name: string;
  type: "video" | "audio";
  media_url: string;
  title: string | null;
  description: string | null;
  user_contribution: UserContribution;
}
```

### 3.5. Типы данных (Dart/Flutter)

```dart
class UserContribution {
  final int totalDonatedKopecks;
  final int donationsCount;
  final DateTime? firstDonationAt;
  final DateTime? lastDonationAt;
}

class UnseenThanksItem {
  final String id;
  final String campaignId;
  final String campaignTitle;
  final String foundationName;
  final String type; // "video" | "audio"
  final String mediaUrl;
  final String? title;
  final String? description;
  final UserContribution userContribution;
  final DateTime createdAt;
}

class ThanksDetail {
  final String id;
  final String campaignId;
  final String campaignTitle;
  final String foundationId;
  final String foundationName;
  final String type; // "video" | "audio"
  final String mediaUrl;
  final String? title;
  final String? description;
  final UserContribution userContribution;
}
```

---

## 4. Push-уведомления

Когда админ добавляет благодарность к активной кампании, **всем донорам** этой кампании отправляется push:

```json
{
  "title": "Благодарность от фонда",
  "body": "Помощь детям — Спасибо от подопечных",
  "data": {
    "type": "thanks_content",
    "thanks_content_id": "01912345-0000-7abc-def0-000000000800",
    "campaign_id": "01912345-0000-7abc-def0-000000000001"
  }
}
```

**Обработка на клиенте:**

```
Получен push с data.type === "thanks_content"
  └─ Навигация на экран благодарности
     └─ GET /api/v1/thanks/{data.thanks_content_id}
```

Push отправляется **безусловно** — не зависит от пользовательских настроек уведомлений (в отличие от push о платежах).

---

## 5. Сценарии интеграции

### 5.1. Проверка при открытии приложения

Самый важный сценарий. При каждом запуске приложения (или возврате из фона) проверять наличие непросмотренных благодарностей.

```
Приложение открыто / вернулось из фона
  │
  ├─ Пользователь авторизован?
  │  ├─ Нет → обычный экран
  │  └─ Да → GET /api/v1/thanks/unseen
  │     ├─ Пустой массив → ничего не делать
  │     └─ Есть элементы → показать модалку/карточку
  │        └─ Пользователь нажал «Посмотреть»
  │           └─ GET /api/v1/thanks/{id}
  │              └─ Открыть плеер (видео/аудио)
  │              └─ Благодарность автоматически помечена
  │
  └─ Следующий запуск → эта благодарность уже не вернётся
```

**Пример (React Native):**

```ts
// При входе в приложение или возврате из фона
async function checkThanks() {
  try {
    const response = await api.get("/api/v1/thanks/unseen");
    const unseen: UnseenThanksItem[] = response.data;

    if (unseen.length > 0) {
      // Показать первую благодарность
      showThanksModal(unseen[0]);
    }
  } catch {
    // Не критично — просто не показываем
  }
}

// AppState listener
AppState.addEventListener("change", (state) => {
  if (state === "active" && isAuthenticated) {
    checkThanks();
  }
});
```

**Пример (Flutter):**

```dart
// При входе или resuming
Future<void> checkThanks() async {
  try {
    final response = await dio.get('/api/v1/thanks/unseen');
    final unseen = (response.data as List)
        .map((e) => UnseenThanksItem.fromJson(e))
        .toList();

    if (unseen.isNotEmpty) {
      showThanksDialog(unseen.first);
    }
  } catch (_) {
    // Не критично
  }
}

// WidgetsBindingObserver
@override
void didChangeAppLifecycleState(AppLifecycleState state) {
  if (state == AppLifecycleState.resumed && isAuthenticated) {
    checkThanks();
  }
}
```

### 5.2. После успешного платежа

Пользователь вернулся с экрана оплаты → проверить благодарности для этой кампании.

```
Возврат с платёжной страницы
  │
  ├─ Показать экран «Спасибо за пожертвование»
  ├─ Подождать 1-2 секунды (вебхук обрабатывается)
  │
  └─ GET /api/v1/thanks/unseen
     ├─ Есть благодарности → предложить посмотреть
     └─ Нет → остаться на экране успеха
```

```ts
async function onPaymentSuccess(campaignId: string) {
  // Показать экран "Спасибо!"
  navigateTo("PaymentSuccess");

  // Дать время вебхуку обработаться
  await new Promise((r) => setTimeout(r, 2000));

  const response = await api.get("/api/v1/thanks/unseen");
  const unseen = response.data;

  // Найти благодарность для этой кампании
  const forCampaign = unseen.find(
    (t: UnseenThanksItem) => t.campaign_id === campaignId
  );

  if (forCampaign) {
    showThanksPrompt(forCampaign);
  }
}
```

### 5.3. По push-уведомлению

```ts
// Обработчик нажатия на push
function onNotificationPress(data: Record<string, string>) {
  if (data.type === "thanks_content" && data.thanks_content_id) {
    navigateTo("ThanksPlayer", { thanksId: data.thanks_content_id });
  }
}
```

---

## 6. Экран просмотра благодарности

### 6.1. Загрузка данных

```ts
async function loadThanks(thanksId: string): Promise<ThanksDetail> {
  const response = await api.get(`/api/v1/thanks/${thanksId}`);
  // Благодарность автоматически помечена как просмотренная
  return response.data;
}
```

### 6.2. Что показывать на экране

```
┌─────────────────────────────────────┐
│                                     │
│   Фонд помощи                      │  ← foundation_name
│                                     │
│   ┌─────────────────────────────┐   │
│   │                             │   │
│   │      ▶ Видеоплеер           │   │  ← media_url (type === "video")
│   │                             │   │     или аудиоплеер (type === "audio")
│   └─────────────────────────────┘   │
│                                     │
│   Спасибо от подопечных             │  ← title
│                                     │
│   Дети из детского дома             │  ← description
│   благодарят за помощь              │
│                                     │
│   ─────────────────────────────     │
│                                     │
│   Кампания: Помощь детям            │  ← campaign_title
│   Ваш вклад: 500 ₽                 │  ← total_donated_kopecks / 100
│   Пожертвований: 3                  │  ← donations_count
│   Первый донат: 01.01.2026          │  ← first_donation_at
│                                     │
│          [ Закрыть ]                │
│                                     │
└─────────────────────────────────────┘
```

### 6.3. Воспроизведение медиа

```ts
// Определение типа плеера
if (thanks.type === "video") {
  // Видеоплеер (react-native-video / video_player)
  return <VideoPlayer source={{ uri: thanks.media_url }} />;
} else {
  // Аудиоплеер (react-native-track-player / audioplayers)
  return <AudioPlayer source={{ uri: thanks.media_url }} />;
}
```

**Форматы медиа:**
- Видео: `video/mp4`
- Аудио: `audio/mpeg`, `audio/mp4`, `audio/ogg`, `audio/webm`

---

## 7. Модалка/карточка «У вас новая благодарность»

При обнаружении непросмотренных благодарностей показать ненавязчивое уведомление:

### Вариант A: Модалка (bottom sheet)

```
┌─────────────────────────────────────┐
│                                     │
│   🎬  У вас новая благодарность!    │
│                                     │
│   Фонд помощи благодарит вас       │
│   за поддержку кампании             │
│   «Помощь детям»                    │
│                                     │
│   [ Посмотреть ]    [ Позже ]       │
│                                     │
└─────────────────────────────────────┘
```

- **«Посмотреть»** → `GET /thanks/{id}` → экран плеера
- **«Позже»** → закрыть модалку. Благодарность останется в `unseen` и покажется при следующем запуске

### Вариант B: Карточка в ленте

Показать карточку в верхней части главного экрана / ленты. При свайпе или нажатии «×» — скрыть до следующего запуска. При нажатии — перейти к плееру.

---

## 8. Обработка множественных благодарностей

Если `unseen` вернул несколько элементов:

**Рекомендация:** показывать **по одной** за сессию. Не заваливать пользователя несколькими модалками подряд.

```ts
async function checkThanks() {
  const response = await api.get("/api/v1/thanks/unseen");
  const unseen = response.data;

  if (unseen.length > 0) {
    // Показать только первую (самую новую)
    showThanksModal(unseen[0]);
    // Остальные покажутся при следующих запусках
  }
}
```

Или показать карточку с количеством:

```
«У вас 3 новых благодарности от фондов» → переход к списку → просмотр по одной
```

---

## 9. Полная схема потока

```
                          АДМИНКА
                             │
              Админ добавляет благодарность
              POST /admin/campaigns/{id}/thanks
                             │
                    ┌────────┴────────┐
                    │                 │
              Сохранение         Push-уведомление
              в БД               всем донорам
                    │                 │
                    │        ┌────────┘
                    │        │
                          МОБИЛЬНОЕ ПРИЛОЖЕНИЕ
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        При запуске    По push        После оплаты
              │              │              │
        GET /unseen    Нажатие         GET /unseen
              │              │              │
              └──────┬───────┘       Фильтр по
                     │               campaign_id
                     │                    │
              Есть непросмотренные?        │
              ├─ Нет → ничего             │
              └─ Да ──────────────────────┘
                     │
              Показать модалку
              «Новая благодарность»
                     │
              Пользователь нажал
              «Посмотреть»
                     │
              GET /thanks/{id}
              ┌──────┴──────┐
              │             │
        Вернуть       INSERT в
        данные       thanks_content_shown
              │        (помечено)
              │
        Открыть плеер
        (видео/аудио)
              │
        Пользователь закрыл
              │
        Следующий GET /unseen
        → эта благодарность
          уже не вернётся ✓
```

---

## 10. Edge cases

| Ситуация | Поведение |
|----------|-----------|
| Пользователь не донатил ни в одну кампанию | `GET /unseen` вернёт `[]` |
| Благодарность удалена админом после просмотра | Ничего — запись в `thanks_content_shown` каскадно удалится |
| Благодарность удалена до просмотра | Она пропадёт из `unseen` |
| Повторный `GET /thanks/{id}` | Вернёт данные, но повторный INSERT проигнорируется (`ON CONFLICT DO NOTHING`) |
| Несколько благодарностей у одной кампании | Все появятся в `unseen`, каждая помечается отдельно |
| Нет интернета при проверке | Обработать ошибку, не ломать UX |
| Пользователь не нажал «Посмотреть» (закрыл модалку) | Благодарность остаётся в `unseen`, покажется при следующем запуске |

---

## 11. Чеклист реализации

1. **API-клиент** — два метода: `getUnseenThanks()` и `getThanksDetail(id)`
2. **Проверка при запуске** — `GET /unseen` при открытии приложения и при возврате из фона
3. **Проверка после платежа** — `GET /unseen` через 1-2 секунды после возврата с оплаты
4. **Обработка push** — навигация на экран благодарности по `data.type === "thanks_content"`
5. **Модалка/карточка** — ненавязчивое уведомление «У вас новая благодарность»
6. **Экран плеера** — видео/аудио плеер + информация о кампании и вкладе
7. **Медиаформаты** — поддержка mp4 (видео), mp3/mp4/ogg/webm (аудио)
8. **Множественные** — показывать по одной за сессию
9. **Ошибки** — graceful degradation, не блокировать UX при ошибках
