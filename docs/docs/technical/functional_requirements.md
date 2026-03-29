# Функциональные требования: API "По Рублю"

> **Тип системы:** REST API для мобильного приложения (Flutter iOS/Android), с перспективой подключения веб-клиента.
> **Стек:** FastAPI + PostgreSQL + Redis + Celery + YooKassa + Docker
> **Все суммы:** в копейках (integer). Все даты: UTC.

---

## 1. Роли и доступ

| Роль | Описание | Аутентификация |
|------|----------|----------------|
| **Гость** | Неавторизованный пользователь. Может просматривать ленту кампаний и детали, но не может платить. | — |
| **Жертвователь (Donor)** | Зарегистрированный пользователь. Просмотр, донат, подписки, история, шеринг. | JWT (телефон + SMS OTP) |
| **Администратор (Admin)** | Управление кампаниями, фондами, модерация контента, просмотр статистики. | JWT (email + пароль) |
| **Менеджер фонда (Foundation Manager)** | Просмотр статистики по своим кампаниям, загрузка контента. Будущая роль (v2). | JWT |

---

## 2. Сущности (Entities)

### 2.1 Foundation (Фонд)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| name | string | Публичное название |
| legal_name | string | Юридическое название |
| description | text | Описание фонда |
| logo_url | string | URL логотипа |
| status | enum | `active`, `suspended` |
| yookassa_shop_id | string | ID магазина в ЮKassa (nullable, на старте общий) |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

### 2.2 Campaign (Кампания / Объявление)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| foundation_id | UUID | FK → Foundation |
| title | string | Заголовок |
| description | text | Описание |
| video_url | string | URL видео (CDN) |
| thumbnail_url | string | Превью |
| status | enum | `draft`, `active`, `paused`, `completed`, `archived` |
| goal_amount | integer | Целевая сумма (копейки), nullable для бессрочных |
| collected_amount | integer | Собранная сумма (копейки) |
| urgency_level | integer | 1–5, приоритет в ленте |
| is_permanent | boolean | Бессрочный сбор |
| ends_at | datetime | Дата окончания (nullable) |
| sort_order | integer | Ручная сортировка |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

### 2.3 Campaign Document (Документы кампании)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| campaign_id | UUID | FK → Campaign |
| title | string | Название документа |
| file_url | string | URL файла (PDF) |
| sort_order | integer | Порядок |

### 2.4 Thanks Content (Благодарность)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| campaign_id | UUID | FK → Campaign |
| type | enum | `video`, `audio` |
| media_url | string | URL файла |
| title | string | Заголовок |
| description | text | Текст |

### 2.5 User (Жертвователь)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| phone | string | Телефон (unique) |
| name | string | Имя (nullable) |
| avatar_url | string | nullable |
| is_active | boolean | Активен |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

### 2.6 Subscription (Подписка на донат)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| user_id | UUID | FK → User |
| amount_kopecks | integer | Сумма за день (100, 300, 500, 1000) |
| billing_period | enum | `weekly`, `monthly` |
| allocation_strategy | enum | `platform_pool`, `foundation_pool`, `specific_campaign` |
| campaign_id | UUID | FK nullable (для specific_campaign) |
| foundation_id | UUID | FK nullable (для foundation_pool) |
| payment_method_id | string | Токен ЮKassa |
| status | enum | `active`, `paused`, `cancelled`, `pending_payment_method` |
| next_billing_at | datetime | Следующее списание |
| paused_reason | enum | `user_request`, `no_campaigns`, `payment_failed` |
| created_at | datetime | UTC |
| cancelled_at | datetime | nullable, soft delete |

**Ограничения:** макс. 5 активных подписок на пользователя.

### 2.7 Transaction (Платёж)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| subscription_id | UUID | FK → Subscription |
| campaign_id | UUID | FK → Campaign |
| foundation_id | UUID | FK → Foundation |
| amount_kopecks | integer | Полная сумма |
| platform_fee_kopecks | integer | Комиссия платформы (15%) |
| provider_payment_id | string | ID платежа ЮKassa |
| idempotence_key | string | unique |
| status | enum | `pending`, `success`, `failed`, `skipped`, `refunded` |
| skipped_reason | string | nullable |
| attempt_number | integer | Номер попытки |
| next_retry_at | datetime | nullable |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |

### 2.8 Allocation Change (Аудит перераспределения)
| Поле | Тип | Описание |
|------|-----|----------|
| id | UUID | PK |
| subscription_id | UUID | FK |
| from_campaign_id | UUID | nullable |
| to_campaign_id | UUID | nullable |
| reason | enum | `campaign_completed`, `no_campaigns_in_foundation`, `manual` |
| notified_at | datetime | nullable |
| created_at | datetime | UTC |

---

## 3. Функциональные требования по модулям

### 3.1 Модуль: Аутентификация

| ID | Требование | Роль |
|----|-----------|------|
| AUTH-01 | Регистрация/вход по номеру телефона + SMS OTP | Гость |
| AUTH-02 | Выпуск JWT access + refresh токенов | Система |
| AUTH-03 | Обновление access-токена по refresh | Donor |
| AUTH-04 | Выход (инвалидация refresh-токена) | Donor |
| AUTH-05 | Вход администратора по email + пароль | Admin |

### 3.2 Модуль: Кампании (публичная часть)

| ID | Требование | Роль |
|----|-----------|------|
| CAMP-01 | Получение ленты активных кампаний (пагинация, сортировка по urgency_level DESC → % выполнения DESC) | Гость, Donor |
| CAMP-02 | Получение детали кампании (описание, прогресс, документы, фонд, thanks_content) | Гость, Donor |
| CAMP-03 | Получение списка документов кампании | Гость, Donor |
| CAMP-04 | Получение информации о фонде | Гость, Donor |
| CAMP-05 | Генерация уникальной deeplink для шеринга кампании | Donor |

### 3.3 Модуль: Подписки и платежи (Donor)

| ID | Требование | Роль |
|----|-----------|------|
| SUB-01 | Создание подписки: выбор суммы (1/3/5/10 руб/день), стратегии распределения, способа оплаты | Donor |
| SUB-02 | Первый платёж через SDK ЮKassa с `save_payment_method: true` + 3DS | Donor |
| SUB-03 | Получение списка своих подписок | Donor |
| SUB-04 | Изменение суммы / стратегии / привязанной кампании | Donor |
| SUB-05 | Пауза подписки | Donor |
| SUB-06 | Возобновление подписки | Donor |
| SUB-07 | Отмена подписки (в один клик, обязательно по закону) | Donor |
| SUB-08 | Получение истории транзакций (фильтр по дате, статусу, кампании) | Donor |
| SUB-09 | Получение детали транзакции | Donor |

### 3.4 Модуль: Биллинг (фоновые задачи)

| ID | Требование | Роль |
|----|-----------|------|
| BILL-01 | Шедулер: каждые 15 мин находить подписки с `next_billing_at <= now()` и инициировать рекуррентное списание | Система |
| BILL-02 | Создание транзакции с idempotence_key перед вызовом ЮKassa | Система |
| BILL-03 | Рекуррентный платёж server-to-server через `payment_method_id` | Система |
| BILL-04 | Обработка webhook `payment.succeeded` → обновить транзакцию, увеличить `collected_amount` кампании | Система |
| BILL-05 | Обработка webhook `payment.canceled` → пометить транзакцию как failed, запланировать retry | Система |
| BILL-06 | Retry-логика: soft decline → повтор через 24ч, 3д, 7д, 14д. Hard decline → уведомление, статус `pending_payment_method` | Система |
| BILL-07 | Комиссия платформы: 15% от каждого платежа, фиксируется в `platform_fee_kopecks` | Система |
| BILL-08 | Конкурентность: `SELECT FOR UPDATE SKIP LOCKED` при выборке подписок для биллинга | Система |

### 3.5 Модуль: Распределение средств (Allocation)

| ID | Требование | Роль |
|----|-----------|------|
| ALLOC-01 | Стратегия `platform_pool`: распределить платёж на кампанию с наивысшим приоритетом (urgency DESC, % выполнения DESC) | Система |
| ALLOC-02 | Стратегия `foundation_pool`: выбрать активную кампанию выбранного фонда | Система |
| ALLOC-03 | Стратегия `specific_campaign`: привязка к конкретной кампании | Система |
| ALLOC-04 | При закрытии кампании: auto-switch на следующую кампанию фонда → fallback на `platform_pool`. Лог в `allocation_changes` | Система |
| ALLOC-05 | Если нет ни одной активной кампании: пауза подписки с `paused_reason = no_campaigns`, НЕ списывать, НЕ ломать стрик | Система |
| ALLOC-06 | Push-уведомление пользователю при каждом auto-switch | Система |

### 3.6 Модуль: Импакт и геймификация (Donor)

| ID | Требование | Роль |
|----|-----------|------|
| IMPACT-01 | Эндпоинт `/impact`: общая сумма донатов, текущий стрик (дни подряд), количество успешных донатов | Donor |
| IMPACT-02 | Стрик не прерывается при паузе по причине `no_campaigns` | Система |
| IMPACT-03 | Ачивки: достижения по сумме/количеству (конфигурируемые через админку) | Donor |

### 3.7 Модуль: Уведомления

| ID | Требование | Роль |
|----|-----------|------|
| NOTIF-01 | Push при успешном списании (сумма, название кампании) | Система |
| NOTIF-02 | Push при неудачном списании (предложение обновить карту) | Система |
| NOTIF-03 | Push при автопереключении кампании | Система |
| NOTIF-04 | Push при паузе подписки из-за отсутствия кампаний | Система |
| NOTIF-05 | Push при возобновлении подписки (появилась кампания) | Система |
| NOTIF-06 | Push при закрытии кампании ("Мы собрали нужную сумму!") | Система |
| NOTIF-07 | Напоминание за 7 дней до истечения срока карты | Система |
| NOTIF-08 | Ежедневный push про стрик (для активных пользователей) | Система |

### 3.8 Модуль: Админ-панель (API)

| ID | Требование | Роль |
|----|-----------|------|
| ADM-01 | CRUD фондов (создание, редактирование, приостановка) | Admin |
| ADM-02 | CRUD кампаний (создание, публикация, скрытие, архивирование) | Admin |
| ADM-03 | Загрузка видео и документов к кампании | Admin |
| ADM-04 | Управление контентом благодарности (thanks_content) | Admin |
| ADM-05 | Просмотр списка пользователей и их подписок | Admin |
| ADM-06 | Статистика по кампании: собрано, кол-во доноров, конверсия | Admin |
| ADM-07 | Общая статистика платформы: GMV, комиссия, активные подписки, retention | Admin |
| ADM-08 | Управление urgency_level и sort_order кампаний | Admin |
| ADM-09 | Просмотр логов allocation_changes | Admin |

---

## 4. API Endpoints (сводная таблица)

### Публичные (без авторизации)

```
GET    /api/v1/campaigns                  # Лента кампаний
GET    /api/v1/campaigns/{id}             # Деталь кампании
GET    /api/v1/campaigns/{id}/documents   # Документы кампании
GET    /api/v1/foundations/{id}            # Информация о фонде
POST   /api/v1/auth/send-otp             # Отправка SMS-кода
POST   /api/v1/auth/verify-otp           # Проверка кода, выдача JWT
POST   /api/v1/auth/refresh              # Обновление токена
```

### Donor (авторизация JWT)

```
GET    /api/v1/me                         # Профиль пользователя
PATCH  /api/v1/me                         # Обновление профиля

POST   /api/v1/subscriptions              # Создать подписку
GET    /api/v1/subscriptions              # Мои подписки
PATCH  /api/v1/subscriptions/{id}         # Изменить подписку
POST   /api/v1/subscriptions/{id}/pause   # Пауза
POST   /api/v1/subscriptions/{id}/resume  # Возобновить
DELETE /api/v1/subscriptions/{id}         # Отменить

GET    /api/v1/transactions               # История платежей
GET    /api/v1/transactions/{id}          # Деталь платежа

GET    /api/v1/impact                     # Импакт-счётчик
GET    /api/v1/impact/achievements        # Ачивки

POST   /api/v1/share/{campaign_id}        # Генерация deeplink
```

### Webhooks

```
POST   /api/v1/webhooks/yookassa          # Callback от ЮKassa
```

### Admin (авторизация JWT + role=admin)

```
POST   /api/v1/admin/auth/login           # Вход админа

GET    /api/v1/admin/foundations           # Список фондов
POST   /api/v1/admin/foundations           # Создать фонд
PATCH  /api/v1/admin/foundations/{id}      # Редактировать фонд

GET    /api/v1/admin/campaigns            # Список кампаний (все статусы)
POST   /api/v1/admin/campaigns            # Создать кампанию
PATCH  /api/v1/admin/campaigns/{id}       # Редактировать кампанию
POST   /api/v1/admin/campaigns/{id}/publish    # Опубликовать
POST   /api/v1/admin/campaigns/{id}/pause      # Приостановить
POST   /api/v1/admin/campaigns/{id}/complete   # Завершить
POST   /api/v1/admin/campaigns/{id}/archive    # Архивировать

POST   /api/v1/admin/campaigns/{id}/documents  # Добавить документ
DELETE /api/v1/admin/campaigns/{id}/documents/{doc_id}

POST   /api/v1/admin/campaigns/{id}/thanks     # Добавить благодарность
PATCH  /api/v1/admin/campaigns/{id}/thanks/{t_id}
DELETE /api/v1/admin/campaigns/{id}/thanks/{t_id}

POST   /api/v1/admin/media/upload         # Загрузка файлов (S3)

GET    /api/v1/admin/users                # Список пользователей
GET    /api/v1/admin/users/{id}           # Деталь пользователя + подписки

GET    /api/v1/admin/stats/overview       # Общая статистика платформы
GET    /api/v1/admin/stats/campaigns/{id} # Статистика кампании

GET    /api/v1/admin/allocation-logs      # Логи перераспределений
```

---

## 5. Бизнес-правила (сводка)

| # | Правило |
|---|---------|
| 1 | **Никакого внутреннего баланса.** Платформа не хранит деньги пользователей. Прямой перевод через ЮKassa. |
| 2 | **Суммы подписки:** 1, 3, 5, 10 руб/день. Отображение всегда "X руб/день", списание — раз в неделю или месяц. |
| 3 | **Комиссия платформы:** 15% от каждого платежа. |
| 4 | **Приоритет способов оплаты:** СБП (0.4%) → SberPay → Банковская карта (2.4%). |
| 5 | **Макс. 5 активных подписок** на пользователя. |
| 6 | **Soft delete:** подписки никогда не удаляются физически, только `cancelled_at`. |
| 7 | **Idempotence key** обязателен для каждого платежа в ЮKassa. |
| 8 | **Retry при soft decline:** 24ч → 3д → 7д → 14д. После 4 попыток — статус `pending_payment_method`. |
| 9 | **Hard decline:** не повторять, уведомить пользователя. |
| 10 | **Стрик не прерывается** при паузе из-за отсутствия кампаний. |
| 11 | **Всегда держать хотя бы одну permanent-кампанию** для fallback. |
| 12 | **Уведомления обязательны** по ФЗ-161 при каждом списании. |

---

## 6. Нефункциональные требования

| Требование | Описание |
|-----------|----------|
| **Масштабируемость** | Горизонтальное масштабирование API-сервиса за load balancer. Celery workers масштабируются отдельно. |
| **Безопасность** | HTTPS only. JWT с коротким TTL (15 мин access, 30 дней refresh). Верификация webhook-подписей ЮKassa. Rate limiting. |
| **Данные** | PostgreSQL, все суммы в копейках (integer). Даты в UTC. |
| **Персональные данные** | Хранение на серверах в РФ (ФЗ-152). Анонимизация через 3 года. |
| **Мониторинг** | Логирование всех платёжных операций. Alerting при росте failed payments >10%. |
| **Деплой** | Docker Compose: api, worker, beat, postgres, redis. CI/CD через GitHub Actions. |
| **API versioning** | Префикс `/api/v1/`. Новые breaking changes — новая версия. |

---

## 7. Фазы реализации

### Фаза 1 — MVP
- Аутентификация (телефон + OTP)
- Кампании (лента + деталь + документы)
- Разовый платёж через ЮKassa (токенизация)
- Webhook-обработка
- Экран благодарности
- Базовая админка (CRUD кампаний и фондов)
- Deeplink для шеринга

### Фаза 2 — Подписки
- Рекуррентные платежи
- Стратегии распределения
- Биллинг-шедулер
- Retry-логика
- Dunning-уведомления
- Импакт-счётчик + стрик

### Фаза 3 — Расширение
- Push-уведомления (FCM/APNs)
- Раздел "Волна" (социальные механики)
- Расширенная статистика для админки
- Раздел "Цели"
- Кабинет менеджера фонда (B2B)
