# Orphans recovery — пограничные случаи и рекомендации

> Дополнение к `meet2_mobile_tasks.md` (раздел 11) и `mobile_handover_2026-04-08.md`. Документ описывает все пограничные случаи, которые мы прошли при разработке защиты от потерянных анонимных аккаунтов, и фиксирует, какая часть закрыта на бэкенде, а какая остаётся на мобилке/админке. Цель — чтобы у мобильной команды не было костылей.

Дата: 2026-04-08

---

## Тесты — что покрыто

В `backend/tests/api/public/test_inactive_anonymous.py` 26 тестов:

| Категория | Тестов | Что проверяется |
|---|---|---|
| Card fingerprint | 3 | Стабильность хэша одной карты, разные карты дают разный хэш, нет last4 → нет fingerprint |
| Per-PM `/orphans` | 4 | Находит anon-orphan, игнорирует не-анонимных юзеров, пустой массив без fingerprint, 404 на чужой PM |
| Per-PM `/recover` | 5 | Мерджит orphan'а, ошибка без fingerprint, работает от non-anonymous current user, мерджит несколько orphan'ов сразу, идемпотентность повторного вызова |
| Scan-вариант (новые `/orphans` и `/recover` без pm_id) | 3 | Без pm_id находит orphan'ов по всем картам юзера, без pm_id мерджит и идемпотентен, пустой ответ если у юзера нет карт |
| Skip soft-deleted | 1 | Soft-deleted orphan'ы не выходят в `/orphans` |
| Cleanup task | 4 | Soft-delete с историей, hard-delete без истории, отзыв refresh-токенов, ловит NULL `last_seen_at` через `created_at` |
| account_merge bugfix | 2 | Дедуп `is_default` карт после merge, отмена дублирующихся активных подписок |
| Middleware `last_seen_at` | 4 | Обновляется на authenticated request, throttle блокирует повторную запись в окне 15 мин, скип без auth header, скип для admin токена |

**Полная регрессия:** 281 passed.

Запуск: `cd backend && python -m pytest tests/api/public/test_inactive_anonymous.py -v`

---

## Пограничные случаи — что учли и как

### 1. Двойное списание после merge
**Сценарий:** В source-аккаунте была активная подписка 30 ₽/мес, в target-аккаунте — тоже. После merge target имеет ДВЕ активные подписки → крон билинга списал бы дважды.

**Решение:** `app/services/account_merge.py` после переноса подписок дедуплицирует активные — оставляет самую старую (по `created_at`), остальные → `cancelled`. Логирует `merge_dedup_subscriptions` с количеством отменённых.

**Тест:** `test_merge_cancels_duplicate_active_subscriptions`.

---

### 2. Несколько `is_default` карт после merge
**Сценарий:** У source была дефолтная карта, у target — тоже. После merge у target две карты с `is_default=true` → UI ломается.

**Решение:** `account_merge` после переноса PM собирает все non-deleted PMs target'а, отсортированные по `created_at desc`, и оставляет default только на самой свежей. Если ни одна карта не была default — повышает самую свежую.

**Тест:** `test_merge_dedupes_is_default_payment_methods`.

---

### 3. Recovery вернёт чужие данные
**Сценарий:** Юзер дёргает `/payment-methods/{id}/orphans` с PM-ID, который ему не принадлежит → пытается посмотреть orphan'ов через чужую карту.

**Решение:** Эндпоинт делает `get_for_user` (фильтр по `user_id`) → 404 если PM не принадлежит. Scan-вариант `/payment-methods/orphans` оперирует только своими картами.

**Тест:** `test_orphans_endpoint_rejects_other_users_pm`.

---

### 4. Recovery от обычного (не-анонимного) аккаунта
**Сценарий:** Реальный юзер с email привязал старую карту → orphan-аккаунт с этой картой должен также находиться и подтягиваться.

**Решение:** `find_orphaned_accounts` фильтрует только source.is_anonymous=true. Current может быть кем угодно. `merge_anonymous_into` тоже — требует только source.is_anonymous, target свободен.

**Тест:** `test_recover_works_when_current_user_is_real_account`.

---

### 5. Несколько orphan-аккаунтов с одной картой
**Сценарий:** Юзер 3 раза переустанавливал приложение со старого устройства, на каждой установке оформлял что-то. Одна и та же физическая карта.

**Решение:** Запрос находит всех (distinct), цикл по каждому → `merge_anonymous_into`. Все три источника soft-deleted, контент переезжает.

**Тест:** `test_recover_merges_multiple_orphans_in_one_call`.

---

### 6. Идемпотентность `/recover`
**Сценарий:** Сеть мигнула, мобилка ретрайнула — `/recover` вызывается дважды. Первый раз orphan'ы смерджены, второй раз источников уже нет.

**Решение:** На второй итерации запрос фильтра `User.is_deleted == False` ничего не находит → `merged_user_ids: []`, нулевые transferred. 200 OK.

**Тест:** `test_recover_idempotent_second_call_is_noop`.

---

### 7. Race с cleanup-кроном
**Сценарий:** Юзер открывает приложение в момент когда крон в фоне soft-delete'ит его old orphan. Юзер дёргает `/orphans` после крона → orphan уже удалён.

**Решение:** Запрос фильтрует `User.is_deleted == False`. Soft-deleted orphan невидим → пустой массив. UI должен это обработать (показать «нет потерянных данных» или ничего).

**Тест:** `test_recover_skips_already_deleted_orphans`.

---

### 8. PM без fingerprint
**Сценарий:** Карта сохранена до миграции `008_user_last_seen_and_pm_fingerprint`, или YooKassa не вернула card.first6/expiry.

**Решение:** `build_card_fingerprint` возвращает None. Per-PM эндпоинт возвращает пустой массив. Scan-вариант пропускает такие карты в `_user_fingerprints` (`isnot(None)`).

**Тест:** `test_orphans_endpoint_no_fingerprint_returns_empty`, `test_fingerprint_none_without_last4`.

---

### 9. NULL `last_seen_at` у анонимного юзера
**Сценарий:** Юзер был создан до миграции, или middleware никогда не сработал (например, юзер вызвал только webhook-эндпоинты).

**Решение:** Cleanup-крон использует `COALESCE(last_seen_at, created_at) < cutoff`. Так такие юзеры всё равно попадают под уборку через 180 дней с момента создания.

**Тест:** `test_cleanup_query_includes_null_last_seen`.

---

### 10. Backlog cleanup'а после долгого даунтайма
**Сценарий:** Сервис лежал месяц, накопилось 50 000 inactive юзеров — крон попытается всех разом обработать в одной транзакции → блокировка БД.

**Решение:** `CLEANUP_BATCH_SIZE = 500` + `ORDER BY coalesce(last_seen, created_at) ASC LIMIT 500`. Каждый запуск чистит самых старых, остальные подождут до завтра.

---

### 11. Push при cleanup может упасть (Firebase down)
**Сценарий:** Cleanup чистит юзера, шлёт push, Firebase отвечает 5xx.

**Решение:** `_process_user` оборачивает `send_push` в `try/except` и логирует warning. Cleanup продолжается.

---

### 12. Юзер удаляет аккаунт через `DELETE /me` — что с его orphan-данными
**Сценарий:** Юзер сам удаляет аккаунт. У него были связки с другими anon-аккаунтами с такой же картой.

**Решение:** `DELETE /me` (`anonymize_user`) — это отдельный flow, не смешан с recovery. Удаление текущего юзера никак не трогает orphan'ов с такой же картой — они продолжают жить до cleanup'а.

**Возможная доработка:** при удалении аккаунта запустить тот же fingerprint-scan и предложить скачать/удалить связанные orphan'ы. Не делал — спорная фича.

---

### 13. Middleware ошибка не должна ломать запрос
**Сценарий:** Redis down, async_session_factory падает с timeout.

**Решение:** `dispatch` оборачивает `_touch` в `try/except`, response отдаётся всегда. Логируется warning.

---

### 14. Middleware на admin токенах
**Сценарий:** Админ из admin-фронта дёргает API → middleware пытается обновить `users.last_seen_at`, но `sub` указывает на `admins.id`.

**Решение:** `_touch` проверяет `payload.get("role") == "admin"` и пропускает.

**Тест:** `test_middleware_touch_skips_for_admin_token`.

---

### 15. Throttle race
**Сценарий:** Два запроса одного юзера прилетают в одну миллисекунду на разные воркеры. Оба видят, что throttle-ключа нет, оба пишут в БД.

**Решение:** Redis `SET NX EX` атомарен. Только один воркер получит `was_set=True`, второй — None и скипнет. UPDATE никак не нарушает консистентность даже если бы оба прошли — это idempotent UPDATE.

---

## Что НЕ покрыли (сознательно)

### Расширенный аудит-лог merge
Сейчас merge просто пишет `account_merged` в structlog. Если нужен пользовательский audit-trail («кто, когда, что слил»), это отдельная фича — таблица `account_merge_log`. Пока не делал, потому что:
- Не требовалось продуктово.
- Логи structlog уже содержат source/target user_id.
- Если потребуется — добавить таблицу с полями `(source_id, target_id, reason: enum["email_link","fingerprint_recovery"], created_at)` и писать из `merge_anonymous_into` и `_recover_by_fingerprints`.

### Recovery по телефону / email
Если у юзера нет той же карты на новом устройстве (например, поменял банк) — recovery невозможен. Альтернативные «якоря»:
- **Email** — уже работает через `link-email-verify-otp` с merge (для случая когда есть email на старом аккаунте).
- **Телефон** — не реализован. Если продукт хочет, можно повторить тот же паттерн, что для email: `phone_verification_codes`, `link-phone-verify-otp`, тот же `merge_anonymous_into`. Это отдельная эпопея, в текущий hotfix не входит.

### Восстановление selectivity
Сейчас `/recover` мерджит ВСЕ найденные orphan'ы за один вызов. Юзер не может выбрать «эти два да, этот нет». На практике 99% случаев — один orphan, поэтому усложнять API не стал. Если потребуется — добавить body `{"user_ids": ["uuid", ...]}` к POST `/recover`.

### Защита от brute-force enumeration
Теоретически злоумышленник может массово создавать новые анонимные аккаунты, прицеплять разные карты и через `/orphans` мониторить, у каких карт есть active подписки на чужих аккаунтах. На практике:
- YooKassa токенизирует карту и не возвращает first6/last4 без реального успешного платежа.
- Чтобы получить fingerprint, надо реально провести платёж и сохранить карту → это стоит денег.
- Возвращаемые данные `OrphanedAccountPreview` не содержат email или name, только агрегаты — нельзя хайджекнуть identity.
- Если очень параноить — добавить rate limit `5/час` на `/orphans` через тот же Redis-механизм, что для OTP. Не делал — не критично, добавим если будут злоупотребления.

---

## Рекомендации мобильной команде

> Вкратце: бэкенд закрыл всё что мог, чтобы у мобилки не было костылей. Ниже — где можно спокойно полагаться на бэкенд, и где остаётся клиентская работа.

### ✅ Можно полагаться на бэкенд (костыли НЕ нужны)

1. **Дедупликация подписок и карт после merge** — мобилке не нужно проверять «а нет ли двух активных подписок?». Бэкенд уже отменил лишние и пометил один default.
2. **Идемпотентность `/recover`** — спокойно ретрайте при сетевых ошибках.
3. **Tracking `last_seen_at`** — никаких heartbeat'ов делать не надо. Достаточно нормального usage приложения (любые auth-запросы).
4. **Orphan recovery без знания pm_id** — есть scan-варианты `GET/POST /payment-methods/orphans` (без `{pm_id}`), не нужно ловить ID свежесохранённой карты, не нужно ждать webhook.
5. **Поведение при NULL fingerprint** — бэкенд просто пропускает такие карты, мобилка может звать `/orphans` без проверки.
6. **Pause/resume/cancel подписки** — отдельные эндпоинты есть, мобилка не должна костылить через обновление подписки.
7. **`is_new` в ответе device-register** — указывает на то, был ли создан новый юзер или восстановлен старый. Используйте для UX «приветствуем» vs «с возвращением» И для триггера «предложить привязать email» (если `is_new=true` после ранее существовавшего токена — значит старый аккаунт почистили).

### 🟡 Что нужно делать на мобилке

1. **Стабильный device_id в Keychain/Keystore** (см. п.1.1 в `meet2_mobile_tasks.md`) — это критично. Без этого защита от орфанов работает только через recovery, что хуже UX.
2. **Дёргать `/orphans` после save_payment_method** — один раз, после успешного донат-flow или bind-card.
3. **Обработать deep link для `subscription_expired_inactive` push** — открывать экран подписок с баннером восстановления.
4. **При входе по email через `link-email/verify-otp`** с конфликтом — показывать модалку слияния (поле `EMAIL_ALREADY_LINKED` в error).

### 🔴 Чего НЕ нужно делать (антипаттерны)

1. **Не хранить `device_id` в `SharedPreferences`** — стирается при удалении.
2. **Не пытаться вычислять fingerprint на клиенте** — bи ack считает сам в webhook'е, мобилка PCI-чистая (не видит first6+expiry).
3. **Не пытаться маппить donation→pm_id вручную** — используй scan-варианты `/orphans` без знания ID.
4. **Не делать собственную дедупликацию подписок после merge** — бэкенд уже сделал.
5. **Не ретрайнить `/recover` с разными body** — он принимает только current user из токена, body не нужен.

---

## Рекомендации админ-фронту

> Админка не участвует в orphan-flow напрямую, но может помочь саппорту разруливать спорные кейсы.

### Что можно показать в админке (если будет нужно)

1. **Список последних merge'ев** — потребует таблицу `account_merge_log` (см. «Что НЕ покрыли»). Сейчас можно посмотреть в structlog по тегу `account_merged` / `orphaned_accounts_recovered`.
2. **Поиск orphan'ов вручную** — админ может зайти в админку, найти юзера по email/телефону, увидеть у него `last_seen_at` и решить вручную, восстанавливать ли его данные. Сейчас такой UI отсутствует — если нужно, добавим эндпоинт `GET /admin/users?inactive_anonymous=true&days_since=30`.
3. **Ручной merge двух аккаунтов** — пока только через прямой SQL или вызов сервиса `merge_anonymous_into`. Если саппорт регулярно делает такое — можно экспонировать `POST /admin/users/{src}/merge-into/{tgt}`. Не делал — нет запроса.
4. **Метрики**:
   - Сколько orphan'ов вычищается в день (`cleanup_inactive_anonymous_done` в логах)
   - Сколько recovery-merge'ев в день (`orphaned_accounts_recovered`)
   - Сколько push'ей `subscription_expired_inactive` уходит (NotificationLog)

### Что бэкенд НЕ предоставляет админке (по запросу — добавим)

- UI для просмотра device_id юзера (только в БД).
- UI для отмены merge'а (merge необратим, источник soft-deleted, можно только восстанавливать вручную через SQL).
- Алерты в Slack при массовом cleanup'е (все логи в structlog → можно сделать через ваш ELK / Loki).

---

## Что добавлено на бэкенд в этом hotfix'е (краткий список изменений)

### Миграция
- `008_user_last_seen_and_pm_fingerprint.py`:
  - `users.last_seen_at` (+ partial index для крона)
  - `payment_methods.card_fingerprint` (+ partial index для recovery)

### Код
- `app/core/middleware.py:LastSeenMiddleware` — троттлинг 15 мин через Redis NX EX, опциональная запись в БД, fail-open.
- `app/core/config.py` — `LAST_SEEN_THROTTLE_MINUTES`, `ANONYMOUS_INACTIVE_DAYS`.
- `app/services/payment_method.py`:
  - `build_card_fingerprint(first6, last4, exp_month, exp_year) → sha256`
  - `find_orphaned_accounts(pm_id, current_user_id)` — per-PM
  - `find_all_orphaned_accounts_for_user(current_user_id)` — scan-вариант
  - `recover_orphaned_accounts(pm_id, current_user_id)` — per-PM
  - `recover_all_orphaned_accounts_for_user(current_user_id)` — scan-вариант
- `app/services/webhook.py` — пробрасывает first6/exp в save_from_yookassa.
- `app/services/account_merge.py` — дедуп is_default + дедуп активных подписок после merge.
- `app/services/auth.py:device_register` — выставляет `last_seen_at`.
- `app/api/v1/public/payment_methods.py` — 4 новых эндпоинта (2 scan + 2 per-PM).
- `app/schemas/payment_method.py` — `OrphanedAccountPreview`, `RecoveryResult`.
- `app/tasks/inactive_anonymous_cleanup.py` — крон с COALESCE(last_seen, created_at), batching по 500, push, soft/hard delete.
- `app/tasks/scheduler.py` — регистрация нового крона.
- `app/main.py` — регистрация LastSeenMiddleware.

### Тесты
- `backend/tests/api/public/test_inactive_anonymous.py` — 26 новых тестов.

### Конфиг (env vars)
- `LAST_SEEN_THROTTLE_MINUTES=15` (default)
- `ANONYMOUS_INACTIVE_DAYS=180` (default = 6 месяцев)

Никаких новых обязательных env vars — defaults работают.

---

## API quick reference (только новое)

```
GET    /api/v1/payment-methods/orphans                # 🟢 scan, без pm_id — рекомендуется
POST   /api/v1/payment-methods/recover                # 🟢 scan, без pm_id — рекомендуется
GET    /api/v1/payment-methods/{pm_id}/orphans        # точечный, для альтернативных flow
POST   /api/v1/payment-methods/{pm_id}/recover        # точечный
```

Все требуют `Authorization: Bearer <access_token>`. Все возвращают `OrphanedAccountPreview[]` и `RecoveryResult` соответственно.

---

**Вопросы / правки** — пинай Малика или открой issue.
