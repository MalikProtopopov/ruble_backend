# «По Рублю» — Документ синхронизации и правок
## Версия 1.0 | На основе cross-check четырёх документов

> Этот документ описывает **все изменения**, которые нужно внести в каждый из четырёх файлов проекта.
> Структура: 4 блока по одному на файл. Каждое изменение имеет тип (`ADD` / `CHANGE` / `FIX` / `CLARIFY`) и уровень приоритета (`🔴 критично` / `🟡 важно` / `🟢 минор`).

> **Актуализация (март 2026):** ниже — история правок. Текущий канон: благодарности — `GET /api/v1/thanks/{id}` и `GET /api/v1/thanks/unseen` ([docs/docs/api_public.md](docs/docs/api_public.md)); очистка `thanks_content_shown` — **12 месяцев**, 1-е число 03:00 UTC ([docs/docs/database_requirements.md](docs/docs/database_requirements.md), ФТ §4.14 TASK-07); ЮKassa — [docs/docs/yookassa_integration.md](docs/docs/yookassa_integration.md).

---

## БЛОК 1 — Функциональные требования
### Файл: `porubly_functional_requirements_v3_2.md`

---

### [CHANGE] 🔴 1.1 Стек: Celery → Taskiq

**Где:** Заголовок документа + раздел 7 «Нефункциональные требования»

**Было:**
```
FastAPI + PostgreSQL + Redis + Celery + YooKassa + Docker
Beat — строго один инстанс
```

**Стало:**
```
FastAPI + PostgreSQL 16 + Redis 7 + Taskiq + YooKassa + Docker
Taskiq scheduler — строго один инстанс планировщика задач
```

**Почему:** Celery и Taskiq — разные библиотеки с разным API. Весь DB-документ уже написан под Taskiq. Если оставить Celery в FR, разработчик подключит не ту зависимость.

---

### [CHANGE] 🔴 1.2 UUID v7 везде вместо v4

**Где:** Заголовок документа + раздел 7 + раздел 3 (все сущности)

**Было:**
```
Все UUID v4
```

**Стало:**
```
Все UUID v7 (библиотека uuid_utils). Монотонные, эффективнее для B-tree индексов PostgreSQL.
Стандартный uuid.uuid4() не использовать — только uuid_utils.uuid7().
```

**Во всех сущностях:** поле `id` описывать как `UUID v7, PK` (не просто `UUID`).

---

### [ADD] 🔴 1.3 Три недостающие сущности

Добавить в раздел 3 «Сущности» после соответствующих родительских сущностей:

---

#### 3.2а `CampaignDonors` (после Campaign, 3.2)

| Поле | Тип | Описание |
|---|---|---|
| campaign_id | UUID v7 | FK → Campaign. PK composite. |
| user_id | UUID v7 | FK → User. PK composite. |
| first_at | datetime UTC | Дата первого доната пользователя в кампанию |

**Зачем:** без этой таблицы `donors_count` считает дубли. 10 донатов одного пользователя = +10 к счётчику. Таблица гарантирует уникальность пары (кампания, пользователь).

**Логика при успешном платеже:**
```sql
INSERT INTO campaign_donors (campaign_id, user_id)
VALUES (:cid, :uid)
ON CONFLICT DO NOTHING;
-- если вставка произошла (rowcount = 1):
UPDATE campaigns SET donors_count = donors_count + 1 WHERE id = :cid;
-- collected_amount обновляется всегда:
UPDATE campaigns SET collected_amount = collected_amount + :amount WHERE id = :cid;
```

---

#### 3.6а `RefreshToken` (после OTPCode, 3.6)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User. Nullable если токен принадлежит Admin |
| admin_id | UUID v7 | FK → Admin. Nullable если токен принадлежит User |
| token_hash | string | SHA-256 хэш токена. Не plain text. Unique. |
| expires_at | datetime UTC | TTL: 30 дней |
| is_used | boolean | true после rotation |
| is_revoked | boolean | true после logout или replay-атаки |
| created_at | datetime UTC | |

**Constraint:** ровно одно из (user_id, admin_id) должно быть NOT NULL.

**Бизнес-правила:**
- `/auth/refresh`: найти по token_hash → проверить `is_used=false AND is_revoked=false AND expires_at > now()` → выдать новую пару → пометить старый `is_used=true`
- `/auth/logout`: пометить `is_revoked=true`
- Если использован токен с `is_used=true` — это replay-атака: отозвать **все** токены пользователя/админа

---

#### 3.4а `ThanksContentShown` (после ThanksContent, 3.4)

| Поле | Тип | Описание |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID v7 | FK → User |
| thanks_content_id | UUID v7 | FK → ThanksContent |
| device_id | string | Информационное. Не участвует в уникальности (аналитика) |
| shown_at | datetime UTC | |

**UNIQUE:** `(user_id, thanks_content_id)`

**Зачем:** отслеживает, какой пользователь уже видел какую благодарность. Без этой таблицы невозможно определить, отправлять ли пуш после платежа.

**Retention:** раз в неделю удалять записи старше 90 дней — после этого благодарность можно показать повторно.

---

### [ADD] 🔴 1.4 Добавить кэш-поля в сущность User (3.5)

Добавить в таблицу полей User:

| Поле | Тип | Описание |
|---|---|---|
| current_streak_days | integer | Кэш текущего стрика. Default: 0. Обновляется атомарно при каждом успешном платеже. |
| last_streak_date | date UTC | Последний день, засчитанный в стрик. |
| total_donated_kopecks | integer | Кэш суммы для GET /impact. Default: 0. |
| total_donations_count | integer | Кэш количества успешных платежей. Default: 0. |
| next_streak_push_at | datetime UTC | Время следующего streak-пуша (12:00 в timezone пользователя). NULL если отключено. |

**Почему эти поля необходимы:**
`GET /impact` вызывается при каждом открытии главного экрана. Без кэша нужен тяжёлый `SELECT DISTINCT DATE(created_at) FROM transactions + donations` по всей истории пользователя при каждом запросе. Кэш-поля обновляются атомарно при успешном платеже и ежедневно сверяются reconciliation-задачей.

**Логика обновления стрика:**
- `last_streak_date = today (UTC)` → ничего не делать (платёж уже засчитан сегодня)
- `last_streak_date = yesterday (UTC)` → `streak += 1`, `last_streak_date = today`
- Иначе → `streak = 1`, `last_streak_date = today`
- При `skipped (no_active_campaigns)` → стрик **не прерывается**: обновить `last_streak_date = today` без инкремента

---

### [ADD] 🟡 1.5 Soft Delete — явно описать миксины в начале раздела 3

Добавить перед разделом 3.1 новый подраздел «3.0 Общие миксины»:

**UUIDMixin** — поле `id: UUID v7`. Применяется ко всем сущностям.

**TimestampMixin** — поля `created_at`, `updated_at` (UTC). Применяется ко всем сущностям.

**SoftDeleteMixin** — поля `is_deleted: boolean (default false)`, `deleted_at: datetime (nullable)`. Применяется к: `User`, `Subscription`, `Donation`. Оба поля обязательны одновременно.

Добавить оба поля явно в сущности User, Subscription, Donation (сейчас в FR их нет или они описаны неполно).

**Важно для Subscription:** `cancelled_at` и `deleted_at` — разные поля:
- `cancelled_at` — бизнес-событие (пользователь отменил подписку через приложение)
- `deleted_at` — техническое мягкое удаление (например, анонимизация по ФЗ-152)

---

### [ADD] 🟡 1.6 Поле `external_reference` в OfflinePayment — добавить в FR и объяснить

**Где:** сущность OfflinePayment (3.8)

Добавить поле в таблицу:

| Поле | Тип | Описание |
|---|---|---|
| external_reference | string | Номер платёжного поручения, банковской квитанции или иного документа. Nullable. |

**Зачем это поле и почему это не баг, а фича:**

Офлайн-платежи вносит администратор вручную через форму. Если он нажмёт «Сохранить» дважды — без защиты `collected_amount` вырастет на двойную сумму, а в БД появятся два идентичных платежа.

`external_reference` — это реальный идентификатор платежа из внешней системы: номер платёжного поручения при банковском переводе (`ПП-12345`), номер кассового чека при наличном и т.д.

**Защита:** в БД создан partial unique index:
```sql
UNIQUE (campaign_id, payment_date, amount_kopecks, external_reference)
WHERE external_reference IS NOT NULL
```

Если admin дважды попытается сохранить один и тот же платёж с заполненным `external_reference` — второй INSERT будет отклонён на уровне БД.

**Вывод:** поле нужно оставить. Рекомендуется делать его обязательным в UI формы (хотя в БД nullable для гибкости). Добавить в FR в описание сущности.

---

### [ADD] 🔴 1.7 Модуль аутентификации — добавить Admin refresh/logout

В раздел 4.1 «Модуль: Аутентификация» добавить строки:

| ID | Требование | Роль |
|---|---|---|
| AUTH-06 | Обновление admin access-токена по refresh (rotation). Логика идентична AUTH-03. | Admin |
| AUTH-07 | Выход администратора — инвалидация refresh-токена. | Admin |

Текущий AUTH-06 переименовать в AUTH-08.

**Почему это критично:** в таблице `refresh_tokens` есть поле `admin_id UUID FK → admins`. Если не добавить эти эндпоинты — admin_id в таблице никогда не заполнится, FK становится мёртвым. Либо нужно убрать поле из БД, либо — что правильно — добавить соответствующие эндпоинты.

---

### [ADD] 🔴 1.8 Новый модуль 4.13: Благодарности (Thanks Content)

Добавить после модуля 4.12 «Уведомления»:

#### 4.13 Модуль: Благодарности от фондов

**Общая концепция:** после успешного платежа пользователь получает push-уведомление с благодарностью от фонда. Пуш содержит `thanks_content_id`. Пользователь нажимает на уведомление → Flutter-клиент открывает экран благодарности → делает запрос к серверу → получает медиа-контент (видео или аудио) → сервер фиксирует факт просмотра.

**Триггеры для отправки:**
1. Успешный разовый донат (`Donation.status → success`) в кампанию
2. Успешное списание по подписке (`Transaction.status → success`), если деньги пошли в конкретную кампанию
3. Успешная оплата по ссылке мецената (`PatronPaymentLink.status → paid`)

**Условия отправки:**
- У кампании есть хотя бы один активный `ThanksContent`
- Пользователь ещё не видел этот контент (нет записи в `ThanksContentShown`)
- Если у кампании несколько `ThanksContent` — выбирается первый непоказанный

| ID | Требование | Роль |
|---|---|---|
| THANKS-01 | После payment.succeeded: проверить наличие непоказанного thanks_content для пользователя. Если есть — отправить push с данными: `{type: "thanks_content", thanks_content_id: "uuid", campaign_id: "uuid", campaign_title: "..."}` | Система |
| THANKS-02 | GET /thanks-contents/{id}: вернуть контент, атомарно зафиксировать показ (`INSERT INTO thanks_content_shown ON CONFLICT DO NOTHING`). Если контент уже показан — всё равно вернуть (пользователь может пересмотреть). | Donor |
| THANKS-03 | Если несколько непоказанных — выбирать по `created_at ASC` (первый загруженный). | Система |
| THANKS-04 | Retention: Taskiq-задача раз в неделю удаляет записи `thanks_content_shown` старше 90 дней → контент можно показать снова. | Система |
| THANKS-05 | Если push-уведомления отключены (`push_on_payment = false`) — благодарность всё равно доступна через историю или список уведомлений, но пуш не отправляется. | Система |

**Почему не WebSocket:**
WebSocket избыточен для этого сценария. Push-уведомление + REST-эндпоинт — стандартный и надёжный паттерн для мобильных приложений. WebSocket оправдан только если нужна двусторонняя связь в реальном времени (например, чат). Здесь достаточно: пуш доставляет ID контента → клиент делает один HTTP-запрос.

---

### [ADD] 🟡 1.9 Граф переходов статусов кампании

Добавить в раздел 4.2 «Модуль: Кампании» или в раздел 3.2 «Campaign»:

**Допустимые переходы статусов:**

```
draft ──────────────→ active      (publish, ADM-02)
active ─────────────→ paused      (admin pause)
active ─────────────→ completed   (complete / close-early / auto по goal / auto по ends_at)
paused ─────────────→ active      (admin resume)
completed ──────────→ archived    (archive)
archived ───────────→ (финальный, нет переходов)
```

**Недопустимые переходы → 422 INVALID_STATUS_TRANSITION:**
- `draft → paused`, `draft → completed`, `draft → archived`
- `archived → любой`
- `completed → active`, `completed → paused`, `completed → draft`

---

### [ADD] 🟡 1.10 Добавить `is_new` в AUTH-02

В требование AUTH-02 добавить:

"Ответ содержит флаг `is_new: true`, если пользователь создан при первой авторизации (не существовал до этого). Используется Flutter-клиентом для запуска онбординга (приветственный экран, выбор интересов и т.д.)."

---

### [ADD] 🟡 1.11 Добавить `allocation_changes` в Фазу 1

**Где:** раздел 8 «Фазы реализации», Фаза 1

Добавить `AllocationChange` в список таблиц Фазы 1 с пояснением:

"Таблица `AllocationChange` **обязательна в Фазе 1**, несмотря на то что полная логика аллокации реализуется в Фазе 2. Причина: требование CLOSE-02 (при закрытии кампании запускать ALLOC-04 и логировать перераспределение) входит в Фазу 1 через CLOSE-01. Без таблицы логирования невозможно выполнить CLOSE-02."

---

### [CHANGE] 🟡 1.12 Исправить skip_reason в сущности Transaction

**Где:** раздел 3.10 Transaction

**Было:** `skipped_reason: string (Nullable)`

**Стало:** `skipped_reason: enum('no_active_campaigns') (Nullable)`

**Почему:** ENUM на уровне БД защищает от невалидных значений. Если в коде случайно запишут произвольную строку — БД отклонит. Разработчик API должен знать, какие значения возможны в ответе.

---

### [ADD] 🟢 1.13 Push notification data payloads

В раздел «Уведомления» (4.12) добавить описание структуры data-поля push-уведомлений:

| notification_type | data payload | Действие клиента |
|---|---|---|
| `payment_success` | `{transaction_id}` или `{donation_id}` | Открыть детальный экран платежа |
| `thanks_content` | `{thanks_content_id, campaign_id, campaign_title}` | Открыть экран благодарности |
| `campaign_changed` | `{subscription_id, new_campaign_id}` | Открыть детали подписки |
| `achievement_earned` | `{achievement_id, achievement_code}` | Открыть экран достижений |
| `payment_failed` | `{subscription_id}` | Открыть экран обновления карты |
| `campaign_completed` | `{campaign_id}` | Открыть карточку завершённой кампании |
| `streak_reminder` | `{current_streak_days}` | Открыть главный экран |

---

## БЛОК 2 — Требования к базе данных
### Файл: `database_requirements.md`

---

### [ADD] 🟡 2.1 Добавить function index для сортировки ленты кампаний

**Где:** секция 3.2 `campaigns`, блок индексов

**Проблема:** сортировка ленты в API описана как `urgency_level DESC, (collected_amount / goal_amount) DESC, sort_order ASC`. Вычисляемое выражение `(collected_amount / goal_amount)` не индексировано. При большом количестве кампаний PostgreSQL будет делать filesort по этому выражению.

**Добавить:**
```sql
-- Для сортировки по проценту заполнения (не охватывает бессрочные кампании)
CREATE INDEX idx_campaigns_fill_rate
    ON campaigns ((collected_amount::numeric / NULLIF(goal_amount, 0)) DESC NULLS LAST)
    WHERE status = 'active' AND goal_amount IS NOT NULL;
```

**Альтернатива (более чистая):** добавить generated column:
```sql
ALTER TABLE campaigns
    ADD COLUMN fill_rate NUMERIC GENERATED ALWAYS AS
    (CASE WHEN goal_amount > 0 THEN collected_amount::numeric / goal_amount ELSE NULL END)
    STORED;

CREATE INDEX idx_campaigns_fill_rate ON campaigns (fill_rate DESC NULLS LAST)
    WHERE status = 'active';
```

Generated column обновляется автоматически при UPDATE и не требует ручного сопровождения.

---

### [ADD] 🟡 2.2 Уточнить admin refresh tokens в секции 3.7

**Где:** секция 3.7 `refresh_tokens`

Добавить в «Бизнес-правила»:

"Логика для admin-токенов идентична user-токенам:
- `POST /admin/auth/refresh`: найти по `token_hash` где `admin_id IS NOT NULL`, проверить, выдать новую пару, пометить старый `is_used=true`
- `POST /admin/auth/logout`: пометить `is_revoked=true`
- Replay-атака (использован `is_used=true` токен): отозвать **все** refresh-токены данного admin-а (`WHERE admin_id = :aid`)

Таким образом, таблица обслуживает оба типа сессий: user и admin — через разные FK-поля при одном CHECK constraint."

---

### [ADD] 🟡 2.3 Добавить бизнес-объяснение к `external_reference` в offline_payments

**Где:** секция 3.10 `offline_payments`

Добавить перед блоком индексов:

"**Защита от дублей:** `external_reference` — номер платёжного поручения / квитанции из внешней системы. Partial unique index гарантирует, что один и тот же документ не будет записан дважды с тем же campaign_id, датой и суммой. Если `external_reference` не заполнен — дедупликация на уровне БД не выполняется. Рекомендуется в UI формы делать это поле обязательным для `payment_method = bank_transfer` (у банковских переводов всегда есть номер поручения).

Поведение при конфликте: вернуть ошибку 409 DUPLICATE_OFFLINE_PAYMENT на уровне приложения, перехватив `UniqueViolation` от PostgreSQL."

Добавить код ошибки в API: `DUPLICATE_OFFLINE_PAYMENT | 409 | Офлайн-платёж с такими реквизитами уже записан`

---

### [ADD] 🟢 2.4 Явно зафиксировать allocation_changes в Фазе 1

**Где:** раздел 7 «Фазы реализации БД», Фаза 1

Таблица `allocation_changes` уже включена в список Фазы 1 с пометкой — это корректно. Добавить пояснение:

"Включена в Фазу 1, так как требование CLOSE-02 (запуск ALLOC-04 при закрытии кампании) реализуется уже на MVP-этапе. Без этой таблицы невозможно залогировать перераспределения и отправить push донорам с объяснением смены кампании."

---

### [ADD] 🟢 2.5 Добавить Taskiq-задачу для reconciliation thanks_content_shown

**Где:** раздел 8 «Фоновые задачи», таблица задач

Добавить строку:

| Задача | Периодичность | SQL |
|---|---|---|
| Очистка thanks_content_shown | Раз в неделю | `DELETE FROM thanks_content_shown WHERE shown_at < now() - interval '90 days'` |

*(Задача уже упомянута в разделе 3.4a, но отсутствует в сводной таблице раздела 8)*

---

## БЛОК 3 — Публичный API
### Файл: `api_public.md`

---

### [ADD] 🔴 3.1 Новый эндпоинт: GET /thanks-contents/{id}

Добавить новый раздел **8. Благодарности от фондов** (перед текущим разделом «Меценаты»):

---

**GET `/thanks-contents/{id}`** — Получить благодарность и зафиксировать просмотр

**Требование:** THANKS-02
**Роль:** Donor (JWT)

**Описание:** вызывается Flutter-клиентом после того как пользователь нажал на push-уведомление с благодарностью. Возвращает медиа-контент и одновременно фиксирует факт просмотра в `thanks_content_shown`. Если пользователь открывает одну и ту же благодарность повторно — контент всё равно возвращается, повторная запись в `thanks_content_shown` игнорируется (ON CONFLICT DO NOTHING).

**Path-параметр:** `id` — UUID v7 благодарности

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
  "description": "Благодаря вам мы смогли помочь 15 семьям этой зимой."
}
```

**Сервер при обработке запроса:**
```sql
INSERT INTO thanks_content_shown (user_id, thanks_content_id)
VALUES (:user_id, :thanks_content_id)
ON CONFLICT DO NOTHING;
```

**Ошибки:**
| Код | HTTP | Описание |
|---|---|---|
| `NOT_FOUND` | 404 | Благодарность не найдена |
| `UNAUTHORIZED` | 401 | Не авторизован |

---

### [ADD] 🔴 3.2 Обновить раздел 9.1 Вебхук ЮKassa — добавить thanks_content логику

**Где:** таблица «Логика» в секции 9.1

Добавить строку (применяется ко всем success-событиям где есть user_id):

| Событие | Действие |
|---|---|
| `payment.succeeded` (любой тип, есть user_id) | ...всё что описано сейчас... + **Проверить наличие непоказанного thanks_content**: если для кампании есть ThanksContent и записи в thanks_content_shown для данного пользователя нет → отправить push `{type: "thanks_content", thanks_content_id, campaign_id, campaign_title}`, залогировать в notification_logs |

**Уточнение для `platform_pool` / `foundation_pool`:** если деньги ушли в кампанию (всегда кроме `skipped`), проверять thanks_content именно той кампании, куда фактически направлены средства (campaign_id транзакции).

---

### [ADD] 🟡 3.3 Push notification data payloads — добавить в раздел 0 «Общие стандарты»

Добавить подраздел **0.6 Push Notification Data Payloads**:

Flutter-клиент получает data-поле в push-уведомлении и на основе `type` открывает нужный экран:

```json
// Успешный платёж
{ "type": "payment_success", "transaction_id": "uuid-v7" }

// Успешный донат
{ "type": "donation_success", "donation_id": "uuid-v7" }

// Благодарность от фонда
{ "type": "thanks_content", "thanks_content_id": "uuid-v7",
  "campaign_id": "uuid-v7", "campaign_title": "Помощь детям" }

// Автоматическая смена кампании
{ "type": "campaign_changed", "subscription_id": "uuid-v7",
  "new_campaign_id": "uuid-v7", "new_campaign_title": "..." }

// Новая ачивка
{ "type": "achievement_earned", "achievement_id": "uuid-v7",
  "achievement_code": "STREAK_30", "achievement_title": "30 дней подряд" }

// Неудача платежа (soft decline)
{ "type": "payment_failed_soft", "subscription_id": "uuid-v7" }

// Неудача платежа (hard decline)
{ "type": "payment_failed_hard", "subscription_id": "uuid-v7" }

// Кампания завершена
{ "type": "campaign_completed", "campaign_id": "uuid-v7",
  "campaign_title": "Помощь детям", "closed_early": false }

// Ежедневный стрик
{ "type": "streak_reminder", "current_streak_days": 42 }
```

---

### [CHANGE] 🟡 3.4 Добавить `paused_at` в ответ GET /subscriptions

**Где:** раздел 5.2 `GET /subscriptions`, объект в data[]

Добавить поле в response:
```json
{
  "paused_at": "2026-03-01T12:00:00Z"
}
```
`paused_at: null` если подписка не на паузе.

---

### [CHANGE] 🟡 3.5 Добавить `source` в ответ POST /donations

**Где:** раздел 4.1 `POST /donations`, Ответ 201

Добавить поле в response:
```json
{
  "source": "app"
}
```

---

### [ADD] 🟡 3.6 Добавить значения skip_reason в документацию

**Где:** раздел 6.2 `GET /transactions/{id}`

Добавить после описания поля `status`:

```
skipped_reason: null | "no_active_campaigns"
```

`no_active_campaigns` — означает, что в момент биллинга не было ни одной активной кампании по стратегии подписки. Стрик пользователя при этом **не прерывается**.

---

### [ADD] 🟢 3.7 Добавить код ошибки DUPLICATE_OFFLINE_PAYMENT в 0.3

*(для полноты, хотя это скорее admin-ошибка)*

---

### [CHANGE] 🟢 3.8 UUID v7 — отметить везде в описании id полей

В описании всех response и request body, где упоминается `"id": "uuid"`, добавить комментарий: `UUID v7`. Например в описании полей ответа:

```
id: string (UUID v7) — уникальный идентификатор
```

---

## БЛОК 4 — Admin API
### Файл: `api_admin.md`

---

### [ADD] 🔴 4.1 Новый эндпоинт: POST /admin/auth/refresh

Добавить в раздел 1 «Аутентификация»:

---

**POST `/admin/auth/refresh`** — Обновить admin access-токен

**Требование:** AUTH-06

**Тело запроса:**
| Ключ | Тип | Обязательность | Описание |
|---|---|---|---|
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

**Логика:** идентична donor-refresh. Старый refresh-токен помечается `is_used=true`. Выдаётся новая пара. Повторное использование уже использованного токена → `REPLAY_ATTACK_DETECTED` → все admin-сессии немедленно отзываются.

**Ошибки:** `401` INVALID_REFRESH_TOKEN, `401` REPLAY_ATTACK_DETECTED

---

### [ADD] 🔴 4.2 Новый эндпоинт: POST /admin/auth/logout

Добавить в раздел 1 «Аутентификация»:

---

**POST `/admin/auth/logout`** — Выход администратора

**Требование:** AUTH-07

**Тело запроса:**
| Ключ | Тип | Обязательность | Описание |
|---|---|---|---|
| `refresh_token` | string | required | Текущий refresh token для отзыва |

```json
{ "refresh_token": "eyJ..." }
```

**Ответ 204:** No Content

**Логика:** пометить токен `is_revoked=true` в `refresh_tokens` по `admin_id`. Access-токен при этом остаётся валидным до истечения TTL (15 мин) — это стандартное поведение stateless JWT.

**Ошибки:** `401` UNAUTHORIZED

---

### [ADD] 🟡 4.3 Добавить объяснение `external_reference` в offline-payment

**Где:** раздел 3.11 POST `/admin/campaigns/{id}/offline-payment`

В описание поля `external_reference` добавить:

"Номер платёжного поручения, банковской квитанции или иного подтверждающего документа. **Рекомендуется заполнять всегда**, особенно для `payment_method = bank_transfer`. При наличии этого поля система автоматически защищает от дублей: попытка сохранить тот же платёж повторно (с теми же campaign_id, payment_date, amount_kopecks, external_reference) вернёт ошибку 409."

Добавить в таблицу ошибок:
| Код | HTTP | Описание |
|---|---|---|
| `DUPLICATE_OFFLINE_PAYMENT` | 409 | Офлайн-платёж с такими реквизитами уже зафиксирован |

---

### [ADD] 🟡 4.4 Добавить граф переходов статусов кампании в раздел 3

Добавить перед списком эндпоинтов кампаний:

**Допустимые переходы статусов кампании:**

| Текущий статус | Переход | Эндпоинт | Примечание |
|---|---|---|---|
| `draft` | → `active` | POST `/publish` | |
| `active` | → `paused` | POST `/pause` | |
| `active` | → `completed` | POST `/complete` | Запускает ALLOC-04 + push донорам |
| `active` | → `completed` | POST `/close-early` | closed_early=true, нужен close_note |
| `paused` | → `active` | PATCH (через статус) | |
| `completed` | → `archived` | POST `/archive` | |

Все прочие переходы → `422 INVALID_STATUS_TRANSITION`

---

### [ADD] 🟡 4.5 Добавить поля анонимизации в GET /admin/users/{id}

**Где:** раздел 7.2 `GET /admin/users/{id}`, поля ответа

Добавить поля:
```json
{
  "is_deleted": false,
  "deleted_at": null
}
```

Это нужно администратору чтобы понимать статус аккаунта — анонимизирован ли он по запросу пользователя (ФЗ-152). У анонимизированных пользователей: `is_deleted=true`, `email` заменён на `deleted_{uuid}@deleted.local`, `name=null`, `phone=null`.

---

### [CHANGE] 🟡 4.6 Обновить коды ошибок раздела 0

Добавить в таблицу:

| Код | HTTP | Описание |
|---|---|---|
| `ADMIN_AUTH_FAILED` | 401 | Неверный email или пароль *(уже есть)* |
| `DUPLICATE_OFFLINE_PAYMENT` | 409 | Офлайн-платёж с такими реквизитами уже зафиксирован *(добавить)* |
| `INVALID_STATUS_TRANSITION` | 422 | Недопустимый переход статуса *(уже есть)* |

---

### [CHANGE] 🟢 4.7 Обновить сводную таблицу эндпоинтов

Добавить в конец:

| # | Метод | Путь | Требование | Описание |
|---|---|---|---|---|
| 37 | POST | `/admin/auth/refresh` | AUTH-06 | Обновить admin access-токен |
| 38 | POST | `/admin/auth/logout` | AUTH-07 | Выход администратора |

**Итого: 38 эндпоинтов admin API.**

---

### [CHANGE] 🟢 4.8 UUID v7 — отметить в описании всех id полей

Аналогично Блоку 3 — во всех объектах ответов добавить пометку `UUID v7` к полям-идентификаторам.

---

## Сводная таблица всех изменений

| Блок | ID | Приоритет | Тип | Краткое описание |
|---|---|---|---|---|
| FR | 1.1 | 🔴 | CHANGE | Celery → Taskiq |
| FR | 1.2 | 🔴 | CHANGE | UUID v4 → v7 везде |
| FR | 1.3 | 🔴 | ADD | 3 новые сущности: CampaignDonors, RefreshToken, ThanksContentShown |
| FR | 1.4 | 🔴 | ADD | Кэш-поля в User (стрик, импакт, пуш) |
| FR | 1.5 | 🟡 | ADD | Общие миксины: UUIDMixin, TimestampMixin, SoftDeleteMixin |
| FR | 1.6 | 🟡 | ADD | external_reference в OfflinePayment + объяснение |
| FR | 1.7 | 🔴 | ADD | AUTH-06/07: admin refresh + logout |
| FR | 1.8 | 🔴 | ADD | Модуль 4.13: Благодарности (thanks_content) |
| FR | 1.9 | 🟡 | ADD | Граф переходов статусов кампании |
| FR | 1.10 | 🟡 | ADD | is_new флаг в AUTH-02 |
| FR | 1.11 | 🟡 | ADD | allocation_changes в Фазу 1 |
| FR | 1.12 | 🟡 | CHANGE | skip_reason: string → enum |
| FR | 1.13 | 🟢 | ADD | Push payload структуры |
| DB | 2.1 | 🟡 | ADD | Function index для fill_rate в ленте |
| DB | 2.2 | 🟡 | ADD | Описание admin refresh/logout в refresh_tokens |
| DB | 2.3 | 🟡 | ADD | Бизнес-объяснение external_reference |
| DB | 2.4 | 🟢 | ADD | allocation_changes в Фазу 1 (пояснение) |
| DB | 2.5 | 🟢 | ADD | Taskiq-задача очистки thanks_content_shown в сводную таблицу |
| PUB | 3.1 | 🔴 | ADD | GET /thanks-contents/{id} |
| PUB | 3.2 | 🔴 | CHANGE | Webhook + thanks_content триггер |
| PUB | 3.3 | 🟡 | ADD | Push data payloads документация |
| PUB | 3.4 | 🟡 | CHANGE | paused_at в GET /subscriptions |
| PUB | 3.5 | 🟡 | CHANGE | source в POST /donations |
| PUB | 3.6 | 🟡 | ADD | skip_reason values в GET /transactions |
| PUB | 3.7 | 🟢 | ADD | DUPLICATE_OFFLINE_PAYMENT в ошибки |
| PUB | 3.8 | 🟢 | CHANGE | UUID v7 пометки везде |
| ADM | 4.1 | 🔴 | ADD | POST /admin/auth/refresh |
| ADM | 4.2 | 🔴 | ADD | POST /admin/auth/logout |
| ADM | 4.3 | 🟡 | CHANGE | external_reference — объяснение + ошибка 409 |
| ADM | 4.4 | 🟡 | ADD | Граф переходов статусов кампании |
| ADM | 4.5 | 🟡 | ADD | is_deleted, deleted_at в /admin/users/{id} |
| ADM | 4.6 | 🟡 | CHANGE | Коды ошибок — DUPLICATE_OFFLINE_PAYMENT |
| ADM | 4.7 | 🟢 | CHANGE | Сводная таблица: 36 → 38 эндпоинтов |
| ADM | 4.8 | 🟢 | CHANGE | UUID v7 пометки везде |

**Итого:** 34 изменения. Критических 🔴 — 10. Важных 🟡 — 16. Минорных 🟢 — 8.
