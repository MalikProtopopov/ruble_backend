# Хендовер для мобильной команды — 2026-04-08

Сводка изменений бэкенда, которые мобилка должна потребить. Документ объединяет два пласта:

1. **Митинг 2 (commit `226e2c9`)** — авто-регистрация устройства, donation cooldown, сохранённые карты, per-user поля у кампаний.
2. **Hotfix орфанов (текущий коммит)** — закрытие бага «после переустановки приложения подписки и карта остаются на потерянном аккаунте».

Подробности по каждой задаче — в `meet2_mobile_tasks.md`. Здесь — только то, что нужно знать чтобы начать работать.

---

## A. Что уже готово на бэкенде (commit `226e2c9`, митинг 2)

### Авторизация и аккаунты
- `POST /api/v1/auth/device-register` — анонимная регистрация по `device_id`. Идемпотентна, refresh-токен живёт 180 дней.
- `POST /api/v1/auth/send-otp` + `POST /api/v1/auth/link-email/verify-otp` — привязка email к гостевому аккаунту, при конфликте — поддержка слияния (`allow_merge=true`).
- `GET /api/v1/me` теперь возвращает `is_anonymous`, `is_email_verified`, `donation_cooldown_hours`, стрик и счётчики донатов.

### Кампании
- `GET /api/v1/campaigns` для авторизованных возвращает `donated_today`, `last_donation`, `next_available_at`, `has_any_donation`. Поддерживает `?sort=helped_today|helped_ever`.
- `GET /api/v1/campaigns/today` — топ-3 для виджета на главной.
- `GET /api/v1/campaigns/{id}` — детальный эндпоинт также отдаёт per-user state + `cooldown_hours`.

### Донаты и подписки
- `POST /api/v1/donations`: cooldown 8 часов на сбор → ответ **429** с `retry_after` и `next_available_at`. Поддерживает `save_payment_method=true` и `payment_method_id` (быстрая оплата сохранённой картой).
- `GET /api/v1/subscriptions/active` — для CTA «оформить подписку» на экране «Спасибо».
- `GET /api/v1/payment-methods` / `DELETE /api/v1/payment-methods/{id}` / `POST /api/v1/payment-methods/{id}/set-default` — управление сохранёнными картами.

### Push
- Регистрация FCM-токена через `device-register` (поле `push_token`). Бэкенд рассылает пуши при успешном донате, при истечении cooldown (`donation_reminder`), и т.д.

> **Где детали и контракты**: [`meet2_mobile_tasks.md`](./meet2_mobile_tasks.md). Каждая фича расписана с примерами и UX-комментариями.

---

## B. Что добавилось сейчас (hotfix орфанов, 2026-04-08)

### Корень бага
Анонимный юзер сохранил карту → не привязал email → переустановил приложение → клиент сгенерировал новый `device_id` → создан новый аккаунт → старый со всеми подписками и картой висит «осиротевшим».

### Решение — три линии обороны

#### B.1. Стабильный `device_id` на клиенте — **главное** 🔥
**В зоне ответственности мобильной команды.** Без этого пункта остальное не имеет смысла.

- iOS: Keychain через `flutter_secure_storage` с `accessibility: KeychainAccessibility.first_unlock`.
- Android: Android Keystore через тот же `flutter_secure_storage`. В манифесте отключить участие этого ключа в auto-backup (`android:allowBackup="false"` или `<exclude>` в backup rules).
- При первой генерации сохранить UUID v4 и **никогда не перегенерировать**. Убедиться, что значение читается после `flutter clean` + переустановки на тестовом устройстве.
- Бэкенд по тому же `device_id` отдаст того же юзера — все подписки и карты на месте.

Это закрывает **~95% случаев**. Тестировать обязательно: установить → оформить подписку → удалить приложение → установить снова → подписка должна быть на месте.

#### B.2. Recovery по карте — для редких случаев (новые телефоны и т.д.)
Когда `device_id` всё-таки сменился (новое устройство, восстановление из чужого бэкапа), бэкенд умеет находить старые аккаунты по **отпечатку карты** (хеш `first6+last4+exp`).

**Новые эндпоинты (см. 11.2 в `meet2_mobile_tasks.md` и `orphans_recovery_corner_cases.md`):**
- 🟢 `GET /api/v1/payment-methods/orphans` — scan-вариант. **Рекомендуется**: не нужно знать `pm_id` свежесохранённой карты, не нужно ловить webhook YooKassa.
- 🟢 `POST /api/v1/payment-methods/recover` — мерджит всех найденных. Идемпотентен.
- `GET /api/v1/payment-methods/{pm_id}/orphans` — точечный (альтернатива).
- `POST /api/v1/payment-methods/{pm_id}/recover` — точечный (альтернатива).

**Когда дёргать:** сразу после первого успешного сохранения карты на свежей установке (после пуша `donation_success` или `payment_success`). Если массив непустой → показать модалку «Найдены данные с прошлой установки. Восстановить?».

**Что закрыто на бэкенде (мобилке костыли НЕ нужны):**
- Дедупликация активных подписок и default-карт после merge
- Идемпотентность `/recover` (можно ретрайнить)
- NULL fingerprint, soft-deleted orphan'ы, race с cleanup-кроном
- Проверка прав на чужой `pm_id` (404)

Полный список — `orphans_recovery_corner_cases.md`.

#### B.3. Авто-уборка мёртвых аккаунтов — на бэкенде, мобилке нужно обработать пуш
Раз в сутки крон `cleanup_inactive_anonymous_users`:
- Анонимные юзеры с `last_seen_at < now − 180 дней` → отменяет активные подписки, гасит карты, отзывает токены, шлёт пуш типа `subscription_expired_inactive`.
- Юзеры с историей донатов остаются soft-deleted (история живёт), без истории — hard-delete.

**Что нужно сделать мобилке:**
- Обработать deep link для пуша `subscription_expired_inactive` → открыть экран «Подписки», показать баннер «Подписка приостановлена из-за длительной неактивности. Восстановить?».
- На login-флоу проверять `is_new` в ответе `device-register`: если `true`, значит старый аккаунт вычистило → имеет смысл предложить сразу привязать почту, чтобы такого больше не было.
- Никаких отдельных запросов для tracking активности **делать не нужно** — бэкенд обновляет `last_seen_at` через middleware на каждом авторизованном запросе (троттлинг 15 минут).

---

## C. Чек-лист задач на мобилке

### Критично (блокирует hotfix)
- [ ] **B.1**: device_id в Keychain (iOS) + Keystore (Android) через `flutter_secure_storage`. Тест: переустановка не теряет `device_id`.
- [ ] **B.2**: после сохранения карты дёргать `GET /payment-methods/orphans` (scan-вариант, без pm_id); показывать модалку восстановления; вызывать `POST /payment-methods/recover`.
- [ ] **B.3**: deep link для push `subscription_expired_inactive` → экран подписок с баннером.

### Из митинга 2 (если ещё не сделано)
- [ ] device-register flow + хранение токенов (см. A → 1 в `meet2_mobile_tasks.md`).
- [ ] Привязка email через OTP + слияние (1.3 в `meet2_mobile_tasks.md`).
- [ ] Per-user поля в карточке кампании, кнопка «Помочь» с состояниями (раздел 2).
- [ ] Виджет «Сегодня помогаем» (раздел 3).
- [ ] Обработка 429 / cooldown bottom sheet (раздел 4).
- [ ] Экран «Спасибо» + CTA подписки через `/subscriptions/active` (раздел 5).
- [ ] Упрощённый экран подписки (раздел 6).
- [ ] Модалка «Моя подписка» (раздел 7).
- [ ] Раздел «Способы оплаты» в профиле (раздел 8).
- [ ] Визуальные правки (раздел 9).
- [ ] FCM регистрация + deep links (раздел 10).

---

## D. Где смотреть полные технические детали

| Документ | Что внутри |
|---|---|
| `meet2_mobile_tasks.md` | Полное ТЗ для мобилки по всем разделам, включая новый раздел 11 про защиту от орфанов. |
| `orphans_recovery_corner_cases.md` | **Все пограничные случаи hotfix'а орфанов** + рекомендации мобилке/админке + чего НЕ делать. |
| `meet2_backend_tasks.md` | Что и зачем сделано на бэкенде в commit `226e2c9`. |
| `meet2_admin_tasks.md` | Изменения для админ-фронта. |
| `meet2_deploy_notes.md` | Migrations + env vars для прод-деплоя. |
| `mocks/2_meet.md` | Исходные требования заказчика. |

---

## E. Что нового в API (быстрая шпаргалка)

```
POST   /api/v1/auth/device-register
POST   /api/v1/auth/link-email/verify-otp           # с allow_merge для слияния
GET    /api/v1/me                                    # is_anonymous, is_email_verified, ...
GET    /api/v1/campaigns                             # ?sort=helped_today|helped_ever, per-user fields
GET    /api/v1/campaigns/today                       # топ-3 виджет
GET    /api/v1/campaigns/{id}                        # per-user state
POST   /api/v1/donations                             # save_payment_method, payment_method_id, 429
GET    /api/v1/subscriptions/active
GET    /api/v1/payment-methods
DELETE /api/v1/payment-methods/{id}
POST   /api/v1/payment-methods/{id}/set-default
GET    /api/v1/payment-methods/orphans               # 🟢 scan-вариант — для мобилки
POST   /api/v1/payment-methods/recover               # 🟢 scan-вариант — для мобилки
GET    /api/v1/payment-methods/{id}/orphans          # точечный (альтернативный flow)
POST   /api/v1/payment-methods/{id}/recover          # точечный (альтернативный flow)
```

Контракты схем — в OpenAPI (`/api/v1/openapi.json`) и в исходных файлах `app/schemas/*.py`.

---

## F. Что НЕ требуется от мобилки

- Делать собственный «keep-alive» / heartbeat для tracking активности — бэкенд считает `last_seen_at` сам.
- Сохранять fingerprint карты на клиенте — он считается на бэкенде в webhook'е YooKassa.
- Удалять локальный `device_id` при logout — он должен переживать всё, кроме факта удаления приложения **с обычного хранилища**, поэтому Keychain/Keystore.

---

**Вопросы / правки** — пишите, докручу.
