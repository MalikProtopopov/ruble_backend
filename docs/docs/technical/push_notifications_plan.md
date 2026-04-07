# Push-уведомления — контекст проекта и план интеграции с Firebase

---

## 1. Что уже реализовано на бэкенде

### 1.1. Инфраструктура

| Компонент | Статус | Файл |
|-----------|--------|------|
| Функция `send_push()` | Работает в режиме **mock** (пишет в лог, не отправляет реально) | `services/notification.py` |
| Таблица `notification_logs` | Создана, все уведомления логируются | `models/notification_log.py` |
| Поле `push_token` у пользователя | Есть, сохраняется через `PATCH /me` | `models/user.py` |
| Поле `push_platform` (fcm/apns) | Есть | `models/user.py` |
| Настройки уведомлений пользователя | Есть (JSON в `notification_preferences`) | `models/user.py` |
| Конфиг `NOTIFICATION_PROVIDER` | Есть в settings, по умолчанию не `"firebase"` | `core/config.py` |
| Cron-задача streak push | Работает каждые 15 мин, режим mock | `tasks/streak_push.py` |
| Админский просмотр логов | `GET /admin/logs/notifications` | `api/v1/admin/logs.py` |

### 1.2. Настройки уведомлений пользователя (`notification_preferences`)

```json
{
  "push_on_payment": true,
  "push_on_campaign_change": true,
  "push_daily_streak": false,
  "push_campaign_completed": true
}
```

Пользователь управляет ими через `PATCH /api/v1/me/notification-preferences`.

### 1.3. Текущая функция отправки

```python
# services/notification.py
async def send_push(session, user_id, push_token, notification_type, title, body, data):
    if settings.NOTIFICATION_PROVIDER == "firebase" and push_token:
        # TODO: implement Firebase push  ← ВОТ ЭТО НАДО РЕАЛИЗОВАТЬ
        status = NotificationStatus.sent
    else:
        status = NotificationStatus.mock  # сейчас всегда сюда попадает

    # Лог всегда пишется в notification_logs
```

---

## 2. Триггеры уведомлений

### Уже подключены в коде (отправляются в mock-режиме)

| # | Триггер | notification_type | Кому | Настройка пользователя | Где в коде |
|---|---------|-------------------|------|------------------------|------------|
| 1 | **Успешный разовый донат** | `donation_success` | Донору | `push_on_payment` | `services/webhook.py:66` |
| 2 | **Успешное списание подписки** | `payment_success` | Подписчику | `push_on_payment` | `services/webhook.py:127` |
| 3 | **Кампания завершена** (цель достигнута) | `campaign_completed` | Всем донорам кампании | — (безусловно) | `admin/campaigns.py:238` |
| 4 | **Кампания закрыта досрочно** | `campaign_completed` | Всем донорам кампании | — (безусловно) | `admin/campaigns.py:293` |
| 5 | **Новая благодарность** (видео/аудио) | `thanks_content` | Всем донорам кампании | — (безусловно) | `admin/campaigns.py:486` |
| 6 | **Ежедневный стрик** | `streak_daily` | Пользователям с включённым стриком | `push_daily_streak` | `tasks/streak_push.py:18` |

### Нужно добавить

| # | Триггер | Предлагаемый notification_type | Кому | Настройка пользователя | Приоритет |
|---|---------|-------------------------------|------|------------------------|-----------|
| 7 | **Новая кампания** в фонде, куда ранее донатил | `new_campaign` | Донорам фонда | `push_on_campaign_change` | Высокий |
| 8 | **Неудачный платёж** (карта отклонена) | `payment_failed` | Подписчику | `push_on_payment` | Высокий |
| 9 | **Подписка поставлена на паузу** (из-за ошибки оплаты) | `subscription_paused` | Подписчику | `push_on_payment` | Высокий |
| 10 | **Новое достижение** разблокировано | `achievement_unlocked` | Пользователю | — (безусловно) | Средний |
| 11 | **Напоминание о стрике** (стрик горит, осталось X часов) | `streak_warning` | Пользователю | `push_daily_streak` | Средний |
| 12 | **Кампания близка к цели** (90%+) | `campaign_almost_done` | Донорам кампании | `push_on_campaign_change` | Низкий |
| 13 | **Еженедельный отчёт** (вы помогли на X ₽) | `weekly_summary` | Активным донорам | отдельный флаг | Низкий |

---

## 3. Формат push-уведомлений (data payload)

Каждое уведомление содержит `data` — JSON для навигации в приложении:

```json
// donation_success
{
  "type": "donation_success",
  "donation_id": "019..."
}

// payment_success (подписка)
{
  "type": "payment_success",
  "transaction_id": "019..."
}

// campaign_completed / campaign_closed
{
  "type": "campaign_closed",
  "campaign_id": "019...",
  "closed_early": false
}

// thanks_content
{
  "type": "thanks_content",
  "thanks_content_id": "019...",
  "campaign_id": "019..."
}

// streak_daily
{
  "type": "streak",
  "days": 15
}

// new_campaign (предлагаемый)
{
  "type": "new_campaign",
  "campaign_id": "019...",
  "foundation_id": "019..."
}

// payment_failed (предлагаемый)
{
  "type": "payment_failed",
  "transaction_id": "019...",
  "subscription_id": "019..."
}

// achievement_unlocked (предлагаемый)
{
  "type": "achievement_unlocked",
  "achievement_id": "019...",
  "title": "Помощник"
}
```

---

## 4. План интеграции с Firebase Cloud Messaging (FCM)

### Шаг 1: Firebase-проект и сервисный аккаунт

1. Создать проект в [Firebase Console](https://console.firebase.google.com)
2. Включить Cloud Messaging
3. Скачать **service account JSON** (Settings → Service Accounts → Generate New Private Key)
4. Положить файл на сервер (например `/opt/porubly/backend/keys/firebase-sa.json`)
5. Добавить в `.env`:
   ```
   NOTIFICATION_PROVIDER=firebase
   FIREBASE_CREDENTIALS_PATH=/app/keys/firebase-sa.json
   ```

### Шаг 2: Библиотека на бэкенде

Добавить в `pyproject.toml`:
```toml
"firebase-admin>=6.0,<7.0"
```

### Шаг 3: Реализовать отправку в `send_push()`

```python
# services/notification.py
import firebase_admin
from firebase_admin import credentials, messaging

_firebase_app = None

def _get_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app

async def send_push(session, user_id, push_token, notification_type, title, body, data=None):
    status = NotificationStatus.mock
    provider_response = None

    if settings.NOTIFICATION_PROVIDER == "firebase" and push_token:
        try:
            _get_firebase_app()
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=push_token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        click_action="FLUTTER_NOTIFICATION_CLICK",
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(badge=1, sound="default"),
                    ),
                ),
            )
            result = await asyncio.to_thread(messaging.send, message)
            status = NotificationStatus.sent
            provider_response = {"message_id": result}
        except messaging.UnregisteredError:
            # Токен невалиден — очистить у пользователя
            status = NotificationStatus.failed
            provider_response = {"error": "unregistered"}
            if user_id:
                await _clear_push_token(session, user_id)
        except Exception as e:
            status = NotificationStatus.failed
            provider_response = {"error": str(e)}
    else:
        logger.info("push_mock", user_id=str(user_id), type=notification_type)

    # Лог всегда пишется
    log = NotificationLog(
        id=uuid7(), user_id=user_id, push_token=push_token,
        notification_type=notification_type, title=title, body=body,
        data=data or {}, status=status, provider_response=provider_response,
    )
    session.add(log)
    await session.flush()
```

### Шаг 4: Обновить streak_push.py

Заменить raw SQL `INSERT INTO notification_logs` на вызов `send_push()` — чтобы стрик-пуши тоже отправлялись через Firebase.

### Шаг 5: Очистка невалидных токенов

При ошибке `UnregisteredError` или `InvalidArgumentError` от FCM — обнулять `push_token` у пользователя, чтобы не слать повторно.

### Шаг 6: Мобильное приложение

1. Подключить `firebase_messaging` (Flutter) или `@react-native-firebase/messaging`
2. При первом запуске получить FCM-токен
3. Отправить токен на бэкенд: `PATCH /api/v1/me` с `{ "push_token": "...", "push_platform": "fcm" }`
4. Обновлять токен при `onTokenRefresh`
5. Обрабатывать входящие уведомления — парсить `data.type` для навигации

---

## 5. Навигация в приложении по типу уведомления

| `data.type` | Куда навигировать |
|-------------|-------------------|
| `donation_success` | Экран успешного платежа или история донатов |
| `payment_success` | Экран подписки или история транзакций |
| `campaign_closed` | Деталь кампании `GET /campaigns/{campaign_id}` |
| `thanks_content` | Экран благодарности `GET /thanks/{thanks_content_id}` |
| `streak` | Главный экран / профиль (показать стрик) |
| `new_campaign` | Деталь кампании |
| `payment_failed` | Экран подписки (предложить обновить карту) |
| `achievement_unlocked` | Экран достижений |

---

## 6. Регистрация и обновление push-токена

### При входе в приложение

```ts
// 1. Запросить разрешение
const permission = await messaging().requestPermission();

// 2. Получить токен
const token = await messaging().getToken();

// 3. Отправить на бэкенд
await api.patch("/api/v1/me", {
  push_token: token,
  push_platform: Platform.OS === "ios" ? "apns" : "fcm",
});

// 4. Подписаться на обновление токена
messaging().onTokenRefresh(async (newToken) => {
  await api.patch("/api/v1/me", { push_token: newToken });
});
```

### При выходе из аккаунта

```ts
await api.patch("/api/v1/me", { push_token: null });
```

---

## 7. Настройки уведомлений (экран в приложении)

Текущие флаги:

| Флаг | Описание | По умолчанию |
|------|----------|:---:|
| `push_on_payment` | Уведомления об успешных платежах | Вкл |
| `push_on_campaign_change` | Изменения в кампаниях | Вкл |
| `push_daily_streak` | Ежедневный стрик | Выкл |
| `push_campaign_completed` | Завершение кампаний | Вкл |

API: `PATCH /api/v1/me/notification-preferences`

```json
{ "push_on_payment": false }
```

---

## 8. Чеклист

### Бэкенд
- [ ] Добавить `firebase-admin` в зависимости
- [ ] Создать Firebase-проект, скачать service account JSON
- [ ] Положить ключ на сервер, добавить `FIREBASE_CREDENTIALS_PATH` в `.env`
- [ ] Установить `NOTIFICATION_PROVIDER=firebase` в `.env`
- [ ] Реализовать отправку через FCM в `send_push()` (шаг 3)
- [ ] Обработка невалидных токенов (`UnregisteredError` → очистка)
- [ ] Обновить `streak_push.py` — использовать `send_push()` вместо raw SQL
- [ ] (Опционально) Добавить триггеры #7-#13 из таблицы

### Мобильное приложение
- [ ] Подключить Firebase SDK
- [ ] Запросить разрешение на уведомления
- [ ] Получить FCM-токен и отправить на бэкенд (`PATCH /me`)
- [ ] Обработчик `onTokenRefresh`
- [ ] Обработчик входящих уведомлений (foreground + background + terminated)
- [ ] Навигация по `data.type` (таблица в разделе 5)
- [ ] Экран настроек уведомлений (`PATCH /me/notification-preferences`)
- [ ] Очистка токена при logout






