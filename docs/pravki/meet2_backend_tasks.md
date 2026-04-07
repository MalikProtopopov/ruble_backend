# Доработки бэкенда по итогам встречи 2 (2_meet.md)

Источник требований: `docs/mocks/2_meet.md`. Документ описывает только бэкенд-часть. Для мобилки и админки см. `meet2_mobile_tasks.md` и `meet2_admin_tasks.md`.

Все ссылки file:line указывают на текущее состояние кода в ветке `main` на момент 2026-04-07.

---

## 1. Анонимная авторизация (device-register)

**Цель:** убрать обязательность email при первом донате. Юзер открывает приложение → бэкенд автоматически создаёт ему профиль и выдаёт долгоживущий токен. Email привязывается позже опционально.

### 1.1. Миграция модели User
Файл: `backend/app/models/user.py:20-58`, новая Alembic-миграция `006_anonymous_users.py`.

- `email` → `nullable=True`. Уникальный индекс заменить на partial unique: `WHERE email IS NOT NULL`.
- Добавить колонки:
  - `device_id: str | None` — client-generated UUID, для идемпотентности device-register.
  - `is_email_verified: bool default False`.
  - `is_anonymous: bool default False` (вычисляемое поле или явный флаг — выбрать явный, проще для запросов).
- Индекс по `device_id` (unique partial: `WHERE device_id IS NOT NULL`).

### 1.2. Эндпоинт `POST /auth/device-register`
Файл: `backend/app/api/v1/auth.py` (рядом с OTP-эндпоинтами).

**Request:** `{ device_id: UUID, push_token?: str, push_platform?: "ios"|"android", timezone?: str }`.

**Behaviour:**
- Если юзер с таким `device_id` уже существует → вернуть новую пару access/refresh для него (re-issue).
- Иначе создать `User(is_anonymous=True, email=NULL, device_id=...)`.
- Выдать access (короткий) + refresh с увеличенным TTL (см. 1.3).

**Response:** `{ access_token, refresh_token, user: { id, is_anonymous, ... } }`.

### 1.3. TTL refresh-токена для гостей
Файл: `backend/app/core/config.py`, `backend/app/services/auth.py:169-228`.

- Добавить `REFRESH_TOKEN_TTL_DAYS_ANONYMOUS` (по умолчанию 180).
- В `create_refresh_token` различать TTL по `user.is_anonymous`.

### 1.4. Привязка email к гостевому аккаунту
Эндпоинты OTP уже есть (`auth.py:25-50`). Логика `verify-otp` должна различать три случая:
1. Не авторизованный запрос + email не существует → стандартная регистрация (как сейчас).
2. Не авторизованный запрос + email существует → стандартный логин (как сейчас).
3. **Авторизованный запрос гостя + email существует** → merge (см. раздел 2).
4. **Авторизованный запрос гостя + email НЕ существует** → проставить email на текущем `User`, `is_anonymous=False`, `is_email_verified=True`.

Для случаев 3-4 нужен новый эндпоинт `POST /auth/link-email/verify-otp` ИЛИ расширить текущий `verify-otp` опциональным заголовком `Authorization`. Рекомендую отдельный эндпоинт для ясности контрактов.

---

## 2. Слияние аккаунтов

**Когда:** гостевой юзер указывает email, у которого уже есть существующий (полноценный) аккаунт.

### 2.1. Политика merge
Целевой аккаунт — **существующий** (с email). Source — гостевой. После merge гостевой soft-deleted.

Что переносить (всё в одной транзакции):
- `donations.user_id` → target.id (`backend/app/services/donation.py`, `models/donation.py:12-49`).
- `transactions.user_id` → target (`models/transaction.py:13-55`).
- `subscriptions.user_id` → target (`models/subscription.py:14-62`). При конфликте (у обоих есть active subscription) — оставить таргетную, source отменить через `services/subscription.py`.
- `payment_methods.user_id` → target (см. раздел 6).
- `notification_logs.user_id` → target.
- `refresh_tokens` source → revoke все.
- Streak: `target.current_streak_days = max(...)`, `target.last_streak_date = max(...)`.
- `target.total_donated_kopecks += source.total_donated_kopecks`.
- `push_token`: если у target пустой — взять из source.

### 2.2. Сервис `services/account_merge.py` (новый)
- Метод `merge_anonymous_into(source: User, target: User) -> User`.
- Идемпотентность: если `source.is_anonymous == False` → no-op.
- Обернуть в `async with db.begin()`.

### 2.3. Soft-delete гостя
Добавить `deleted_at` в `User` (если нет). Все запросы публичных API уже фильтруют по `is_active` — добавить фильтр и по `deleted_at IS NULL`.

---

## 3. Доработка списка сборов

**Цель:** на главной мобильного приложения юзер должен сразу видеть, в каких сборах он сегодня уже помог, когда в следующий раз сможет внести взнос, и какой был его последний донат.

### 3.1. Расширение `CampaignListItem`
Файл: `backend/app/schemas/campaign.py:32-47`.

Добавить поля (присутствуют только если запрос **авторизованный**, для гостей и анонимов — `null`):
| Поле | Тип | Описание |
|---|---|---|
| `donated_today` | `bool` | True, если юзер сделал успешный донат в эту кампанию в текущий календарный день в его таймзоне. |
| `last_donation` | `DonationShortDTO \| null` | `{ id, amount_kopecks, created_at, status }` последнего успешного доната юзера в эту кампанию. |
| `next_available_at` | `datetime \| null` | `last_donation.created_at + DONATION_COOLDOWN`. `null` если доната ещё не было. |
| `has_any_donation` | `bool` | True, если у юзера в этом сборе вообще когда-либо был успешный донат. |

Поле `thumbnail_url` уже есть — это и есть `preview_image_url` из ТЗ. Переименовывать не нужно.

### 3.2. Сортировка
Файл: `backend/app/services/campaign.py`, `api/v1/public/campaigns.py:22-56`.

Параметр `sort` в `GET /campaigns`:
- `default` — текущая сортировка по `urgency_level`/`created_at`.
- `helped_today` — `ORDER BY donated_today DESC, has_any_donation DESC, urgency_level DESC`.
- `helped_ever` — `ORDER BY has_any_donation DESC, urgency_level DESC`.

### 3.3. Производительность
Для авторизованных запросов делать LATERAL join к `donations`:
```sql
LEFT JOIN LATERAL (
  SELECT id, amount_kopecks, created_at
  FROM donations
  WHERE user_id = :uid AND campaign_id = c.id AND status = 'success'
  ORDER BY created_at DESC LIMIT 1
) AS last_d ON true
```
Индекс: `CREATE INDEX donations_user_campaign_created_idx ON donations (user_id, campaign_id, created_at DESC) WHERE status = 'success';` — добавить в миграцию.

Таймзону для `donated_today` брать из `User.timezone`. Сравнение через `(last_d.created_at AT TIME ZONE :tz)::date = (now() AT TIME ZONE :tz)::date`.

### 3.4. Эндпоинт «3 сбора на сегодня»
Новый: `GET /campaigns/today`. Возвращает 3 кампании из активных. Логика выбора курируемая на старте: первые 3 по сортировке `urgency_level DESC, created_at DESC`. На будущее — параметр `featured` в модели `Campaign`.

Поля те же, что в `CampaignListItem` (включая `donated_today`).

---

## 4. Cooldown повторных донатов

**Цель:** не дать юзеру внести 10 донатов в одну кампанию подряд. Минимум 6–8 часов между донатами в одну и ту же кампанию (точное значение в конфиге).

### 4.1. Конфиг
Файл: `backend/app/core/config.py`. Добавить:
```python
DONATION_COOLDOWN_HOURS: int = 8
```

### 4.2. Проверка в сервисе
Файл: `backend/app/services/donation.py` (создание доната).

Перед созданием платежа в YooKassa:
- Найти последний `success` донат юзера в этой кампании.
- Если `now - last.created_at < timedelta(hours=DONATION_COOLDOWN_HOURS)` → `HTTPException(429)` с заголовком `Retry-After: <seconds>` и телом `{ error: "donation_cooldown", retry_after: <seconds>, next_available_at: <iso> }`.
- Гостям (`user_id IS NULL`) cooldown по device_id (если передан) или по IP — fallback. **Решение:** для гостей с device_id применять cooldown, для анонимов без device_id — пропускать (это рискованно, но другого надёжного ключа нет).

### 4.3. Push-напоминание
Файл: `backend/app/tasks/donation_reminder.py` (новый), по образцу `tasks/streak_push.py`.

- Celery beat task раз в час.
- Находит юзеров, у которых `now - last_donation > DONATION_COOLDOWN` И `now - last_donation < DONATION_COOLDOWN + 1h` И `notification_preferences.push_on_donation_reminder == true`.
- Шлёт push «Можно снова поддержать сбор N» через существующий `services/notification.py`.
- Логирует в `notification_logs`.

Добавить в `User.notification_preferences` ключ `push_on_donation_reminder` (default `true`). Миграция данных не нужна — JSONB.

---

## 5. Saved payment methods

**Цель:** юзер вводит карту один раз, дальше платит в 2 клика.

### 5.1. Новая модель `PaymentMethod`
Файл: `backend/app/models/payment_method.py` (новый), миграция `007_payment_methods.py`.

Поля:
- `id: UUID7`
- `user_id: UUID` (FK на users, ON DELETE CASCADE)
- `provider: str` (пока `"yookassa"`, на будущее `"sbp"`)
- `provider_pm_id: str` (id метода в YooKassa)
- `card_last4: str | None`
- `card_type: str | None` (`visa`/`mastercard`/`mir`)
- `is_default: bool`
- `created_at`, `updated_at`

Уникальный индекс `(user_id, provider, provider_pm_id)`.

### 5.2. Сохранение при первом донате
Файл: `backend/app/services/donation.py` + `services/yookassa.py:42-92`.

- В payload создания доната принимать `save_payment_method: bool` (от мобилки).
- При успешном webhook'е YooKassa, если `save_payment_method=True` и `payment_method_id` пришёл — создать `PaymentMethod`.
- Метаданные карты (last4, type) брать из payload вебхука YooKassa (`payment_method.card`).

### 5.3. CRUD эндпоинты
Новый файл: `backend/app/api/v1/public/payment_methods.py`.

- `GET /payment-methods` → список карт юзера.
- `DELETE /payment-methods/{id}` → удалить (вызов YooKassa API на удаление + soft-delete локально).
- `POST /payment-methods/{id}/set-default` → переключить default.

### 5.4. Использование в донатах и подписках
- В `POST /donations` принимать `payment_method_id` (опциональный). Если передан — оплата без редиректа.
- В `subscriptions` уже есть `payment_method_id` — связать с новой моделью (FK на `payment_methods.id` вместо строки).

**Замечание:** СБП — отдельная история, в этот раунд не реализуем. Только закладываем `provider` поле для расширения.

---

## 6. Проверка активной подписки (для CTA на экране «спасибо»)

**Цель:** мобилка показывает кнопку «оформить подписку» на экране «спасибо» только если у юзера её нет.

### 6.1. Эндпоинт
Файл: `backend/app/api/v1/public/subscriptions.py` (или существующий профильный).

`GET /subscriptions/active` → `{ has_active: bool, subscription: SubscriptionDTO | null }`.

Логика: SELECT по `subscriptions WHERE user_id = :uid AND status = 'active' LIMIT 1`.

Это мини-задача, ~30 строк.

---

## 7. Документы

Уже в работе на текущей ветке (untracked):
- `backend/app/models/document.py`
- `backend/app/repositories/document_repo.py`
- `backend/app/api/v1/public/documents.py`
- `backend/app/api/v1/admin/documents.py`
- Миграция `005_documents.py`

**Что проверить перед мерджем:**
- Возвращает ли публичный эндпоинт превью-картинки документов (для отображения галереи в мобилке).
- Поддерживается ли загрузка изображений документов через админку.

Доработок в рамках meet2 не требуется, см. отдельную ветку работ по документам.

---

## 8. Push-инфраструктура

**Готово:** Firebase Admin SDK, `services/notification.py`, `notification_logs`, `User.push_token/push_platform`, celery `tasks/streak_push.py`. Используется в задаче 4.3 (reminder).

Доработка:
- Добавить ключ `push_on_donation_reminder` в `notification_preferences` (см. 4.3).
- Эндпоинт обновления `push_token` уже есть в `profile.py:29-36`.

---

## Порядок реализации (рекомендация)

1. **Фундамент:** миграция User (1.1) + device-register (1.2) + TTL (1.3). Без этого ничего не сдвинется.
2. **Merge accounts** (раздел 2) — сразу за фундаментом, иначе юзеры сломают данные.
3. **Cooldown донатов** (раздел 4) — изолированная задача, можно параллельно.
4. **Расширение списка сборов** (раздел 3) — зависит от 4 (для `next_available_at`).
5. **Saved payment methods** (раздел 5) — независимо.
6. **GET /subscriptions/active** (раздел 6) — мини-задача, можно в любой момент.
7. **Reminder push** (4.3) — после 4 и наличия beat-конфигурации.

## Открытые вопросы (нужно уточнить у заказчика)

- Точное значение cooldown: 6 или 8 часов? → закладываем конфигом, дефолт 8.
- Что делать при merge, если у обоих аккаунтов активные подписки с разными суммами? → предлагаю оставлять таргетную, source отменять.
- «3 сбора на сегодня» — фиксированный курируемый список или ротация по urgency? → на старте делаем по urgency, потом добавляем `featured` флаг.
- Cooldown для гостей без device_id — применять или нет? → предлагаю не применять (нет надёжного ключа), договориться с заказчиком.
