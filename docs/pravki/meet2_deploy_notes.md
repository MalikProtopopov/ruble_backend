# Meet2 — деплой на прод (5.42.108.203)

Все изменения протестированы локально (255/255 pytest-тестов). Инструкция учитывает, что часть untracked-файлов с прошлой ветки (документы) тоже должна попасть в прод вместе с meet2.

## 1. Что попадёт в коммит

### Новые файлы (meet2-only)
- `backend/alembic/versions/006_anonymous_users.py`
- `backend/alembic/versions/007_payment_methods.py`
- `backend/app/models/payment_method.py`
- `backend/app/schemas/payment_method.py`
- `backend/app/services/account_merge.py`
- `backend/app/services/payment_method.py`
- `backend/app/api/v1/public/payment_methods.py`
- `backend/app/tasks/donation_reminder.py`
- `backend/tests/api/public/test_meet2_api.py`
- `docs/docs/technical/meet2_backend_tasks.md`
- `docs/docs/technical/meet2_mobile_tasks.md`
- `docs/docs/technical/meet2_admin_tasks.md`
- `docs/docs/technical/meet2_deploy_notes.md` (этот файл)

### Изменённые файлы (meet2-only)
- `backend/app/core/config.py` — `JWT_REFRESH_TOKEN_EXPIRE_DAYS_ANONYMOUS=180`, `DONATION_COOLDOWN_HOURS=8`.
- `backend/app/core/security.py` — `jti` в refresh-токене, поддержка кастомного TTL.
- `backend/app/models/user.py` — `email` nullable, `device_id`, `is_anonymous`, `is_email_verified`.
- `backend/app/models/__init__.py` — экспорт `PaymentMethod`.
- `backend/app/schemas/auth.py` — `DeviceRegisterRequest`, `LinkEmailVerifyRequest`, `LinkEmailTokenResponse`, расширение `UserBrief`.
- `backend/app/schemas/donation.py` — поля `payment_method_id`, `save_payment_method`.
- `backend/app/schemas/campaign.py` — `LastDonationBrief`, per-user поля в `CampaignListItem`, `cooldown_hours` в детали.
- `backend/app/schemas/subscription.py` — `ActiveSubscriptionResponse`.
- `backend/app/schemas/user.py` — `is_anonymous`, `is_email_verified`, `donation_cooldown_hours`, `push_on_donation_reminder`.
- `backend/app/services/auth.py` — `device_register`, `link_email_verify_otp`, длинный TTL для гостей, merge-preview в ошибке.
- `backend/app/services/campaign.py` — LATERAL join для per-user полей, режимы сортировки, `get_user_campaign_state`, `list_today_campaigns`.
- `backend/app/services/donation.py` — `_check_donation_cooldown`, поддержка `payment_method_id`/`save_payment_method`, убран guest email-flow.
- `backend/app/services/subscription.py` — `get_active_for_user`.
- `backend/app/services/webhook.py` — сохранение `PaymentMethod` при успешном донате с `save_payment_method=1`.
- `backend/app/services/yookassa.py` — test-mode bypass когда нет credentials (нужен для CI).
- `backend/app/api/v1/auth.py` — эндпоинты `/device-register`, `/link-email/verify-otp`.
- `backend/app/api/v1/public/campaigns.py` — опциональная авторизация, `sort`, `/today`, расширенный detail.
- `backend/app/api/v1/public/donations.py` — пропуск `payment_method_id`/`save_payment_method`.
- `backend/app/api/v1/public/profile.py` — кастомный сериализатор с meet2 полями.
- `backend/app/api/v1/public/subscriptions.py` — `/active`.
- `backend/app/main.py` — регистрация `payment-methods` роутера.
- `backend/app/tasks/scheduler.py` — регистрация `donation_reminder`.
- `backend/tests/api/public/test_donations_api.py` — обновлены под новый контракт (auth required).
- `backend/tests/integration/test_donation_flow.py` — то же самое.

### Файлы, НЕ относящиеся к meet2 (но уже изменены, разобраться отдельно)
В рабочей копии есть правки в `transactions.py`, `notification.py`, `streak_push.py`, `pyproject.toml`, `docker-compose.prod.yml`, `admin/__init__.py`, `transaction.py` — это **до-meet2 untracked-работа** (прежняя сессия). Они тоже попадут в коммит. Перед коммитом стоит просмотреть `git diff` по этим файлам и убедиться, что хочется их пушить.

### Креды Firebase
В корне лежит `porublyu-be27f-firebase-adminsdk-fbsvc-e64d2acb2b.json`. **Не коммитить.** Должен быть в `.gitignore` или передан на сервер отдельно (scp).

## 2. Подготовка к коммиту

```bash
cd /Users/mak/fondback

# Просмотр всего, что в индексе
git status

# Убедиться, что firebase JSON в .gitignore
grep -F "porublyu-be27f-firebase-adminsdk" .gitignore || \
  echo "porublyu-be27f-firebase-adminsdk-fbsvc-e64d2acb2b.json" >> .gitignore

# Стейджить только то, что нужно (выборочно, не -A)
git add backend/alembic/versions/006_anonymous_users.py
git add backend/alembic/versions/007_payment_methods.py
git add backend/app/models/payment_method.py
git add backend/app/schemas/payment_method.py
git add backend/app/services/account_merge.py
git add backend/app/services/payment_method.py
git add backend/app/api/v1/public/payment_methods.py
git add backend/app/tasks/donation_reminder.py
git add backend/tests/api/public/test_meet2_api.py
git add backend/app/core/config.py backend/app/core/security.py
git add backend/app/models/user.py backend/app/models/__init__.py
git add backend/app/schemas/{auth,donation,campaign,subscription,user}.py
git add backend/app/services/{auth,campaign,donation,subscription,webhook,yookassa}.py
git add backend/app/api/v1/auth.py
git add backend/app/api/v1/public/{campaigns,donations,profile,subscriptions}.py
git add backend/app/main.py backend/app/tasks/scheduler.py
git add backend/tests/api/public/test_donations_api.py
git add backend/tests/integration/test_donation_flow.py
git add docs/docs/technical/meet2_*.md .gitignore
```

## 3. Коммит и push

```bash
git commit -m "meet2: anonymous auth, donation cooldown, saved cards, per-user campaign fields"
git push origin main
```

## 4. Применение на сервере

```bash
ssh root@5.42.108.203
cd /opt/porubly
git pull origin main
set -a && source backend/.env && set +a

# Сборка
docker compose -f docker-compose.prod.yml build backend

# Миграции 006 + 007 + 008 (008 — hotfix orphans: users.last_seen_at, payment_methods.card_fingerprint)
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# Перезапуск backend и worker (worker нужен из-за нового donation_reminder cron)
docker compose -f docker-compose.prod.yml up -d --no-deps backend worker

# Проверка
curl -sf https://backend.porublyu.parmenid.tech/api/v1/health
docker logs porubly-backend-1 --tail 50
```

### Smoke checks после деплоя

```bash
# 1. device-register работает
curl -sX POST https://backend.porublyu.parmenid.tech/api/v1/auth/device-register \
  -H "Content-Type: application/json" \
  -d '{"device_id": "smoke-test-12345678"}' | jq

# 2. Расширенный профиль (нужен полученный access_token из шага 1)
ACCESS_TOKEN=...
curl -s https://backend.porublyu.parmenid.tech/api/v1/me \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '{is_anonymous, donation_cooldown_hours, notification_preferences}'

# 3. Кампании с per-user полями
curl -s "https://backend.porublyu.parmenid.tech/api/v1/campaigns?sort=helped_today" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.data[0] | {id, donated_today, next_available_at}'

# 4. Hotfix orphans — scan-вариант (должен вернуть пустой массив для свежесозданного юзера)
curl -s https://backend.porublyu.parmenid.tech/api/v1/payment-methods/orphans \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq

# 5. /campaigns/today
curl -s https://backend.porublyu.parmenid.tech/api/v1/campaigns/today | jq 'length'

# 5. Активная подписка
curl -s https://backend.porublyu.parmenid.tech/api/v1/subscriptions/active \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq

# 6. Payment methods (пока пустой)
curl -s https://backend.porublyu.parmenid.tech/api/v1/payment-methods \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq
```

## 5. Что может пойти не так

### Миграция 006 на проде с существующими данными
- Делает `email NULLABLE`, бэкфиллит `is_email_verified=true` для всех существующих юзеров с email. Если в проде есть юзеры с `email IS NULL` (не должно быть, но мало ли) — у них останется `is_email_verified=false`. Это безопасно.
- Старый partial index `idx_users_email` пересоздаётся с дополнительным условием `email IS NOT NULL`. На время DROP+CREATE индекса возможна короткая блокировка таблицы users — проверьте, что нагрузка низкая в момент применения.

### Миграция 007 — индекс на donations
Создаёт `idx_donations_user_campaign_created` без `CONCURRENTLY`. На больших таблицах это блокирует write'ы. Если donations уже большая (десятки тысяч строк) — лучше применить отдельно через psql:
```sql
CREATE INDEX CONCURRENTLY idx_donations_user_campaign_created
  ON donations (user_id, campaign_id, created_at DESC)
  WHERE status IN ('success', 'pending');
```
И только потом удалить эту часть из миграции 007 / запустить `alembic stamp 007`.

### Worker (taskiq scheduler)
Новый таск `donation_reminder` запускается из `app.tasks.scheduler` через `@broker.task(schedule=[{"cron": "5 * * * *"}])`. Убедитесь, что в `docker-compose.prod.yml` есть сервис `worker` или `scheduler`, который запускает `taskiq scheduler app.tasks.scheduler:scheduler`. Если нет — задача не будет триггериться.

### Refresh-токен `jti`
В `core/security.py` теперь добавлен `jti` claim. **Старые refresh-токены продолжают работать** (jwt-декодер их не отвергает, отсутствие jti не критично). Никакого forced logout не нужно.

### YooKassa test-mode bypass
В `services/yookassa.py` добавлен fallback: если `YOOKASSA_SHOP_ID` пустой — возвращается mock-payload. На проде эти переменные заполнены, поэтому реальные платежи продолжат идти. **Проверь после деплоя**, что `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` в `/opt/porubly/backend/.env` не пустые:
```bash
grep -E '^YOOKASSA_(SHOP_ID|SECRET_KEY)=' /opt/porubly/backend/.env
```

## 6. Откат

Если что-то пошло не так:

```bash
ssh root@5.42.108.203
cd /opt/porubly
docker compose -f docker-compose.prod.yml exec backend alembic downgrade 005_documents
git reset --hard <prev_commit_sha>
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml up -d --no-deps backend worker
```

`downgrade 005_documents` уберёт meet2-миграции (007 и 006). После этого старый код без `device_id`/`is_anonymous` будет работать с восстановленной схемой.

## 7. Что НЕ затронуто

- Nginx-конфиг.
- Postgres / Redis сервисы.
- Существующие endpoint'ы (donations create теперь требует auth — это **breaking change** для клиентов, которые шлют email без токена; мобилка должна обновиться одновременно или раньше деплоя).
- Webhook YooKassa — расширен, но обратно совместим.

## 8. Известные TODO после деплоя

- Удалить firebase JSON из корня репо (если попал в коммит — почистить через `git filter-repo`).
- Решить вопрос с долгоживущими refresh-токенами гостей (180 дней) и хранением jti в БД для возможности revoke по jti.
- Добавить admin endpoint для просмотра payment_methods (см. `meet2_admin_tasks.md`).
