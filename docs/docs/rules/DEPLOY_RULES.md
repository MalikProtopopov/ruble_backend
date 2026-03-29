# Deploy Rules — AI Coding Guide

> Инфраструктура и деплой репозитория **trihoback**.  
> Источник правды: `docker-compose.yml`, `docker-compose.prod.yml`, `scripts/deploy.sh`, `Makefile`, `nginx/`.

---

## Архитектура (prod)

```
                    ┌─────────────┐
                    │   Nginx     │ :80, :443
                    │  SSL, proxy │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           │               │               │
    / → API host     /media/ → MinIO    (фронты —
    proxy_pass       proxy на bucket     отдельные хосты)
    backend:8000
           │
    ┌──────▼──────┐     ┌──────────┐     ┌────────┐     ┌───────┐
    │   backend   │     │ Postgres │     │ Redis  │     │ MinIO │
    │  Gunicorn+  │     │   :5432  │     │ :6379  │     │ :9000 │
    │  Uvicorn    │     │ (внутр.) │     │(внутр.)│     │(внутр.)│
    └──────┬──────┘     └──────────┘     └────────┘     └───┬───┘
           │
    ┌──────▼──────┐
    │   worker    │  Taskiq (очереди Redis)
    └─────────────┘
```

- **API** снаружи — только через **HTTPS** на `${API_DOMAIN}` (из `.env.prod`).
- **Postgres / Redis / MinIO** в prod **не публикуют порты** наружу; доступ из контейнеров по именам сервисов.
- **Админка и публичный сайт** (SPA) в этом compose **не собираются** — деплоятся отдельно; в `docker-compose.prod.yml` нет volume `admin-dist` (в отличие от старых шаблонов).

---

## Сервисы Docker Compose

| Сервис | Назначение |
|--------|------------|
| **backend** | FastAPI под **Gunicorn** + `UvicornWorker`, порт 8000 только `expose` |
| **worker** | `taskiq worker app.tasks:broker` — фоновые задачи |
| **postgres** | PostgreSQL 16, данные в volume `postgres_data` |
| **redis** | Redis 7, persistence в volume `redis_data` |
| **minio** | S3-совместимое хранилище (prod на этом стеке тоже в compose) |
| **minio-init** | Однократное создание bucket (`restart: no`) |
| **nginx** | TLS, прокси на `backend`, раздача `/media/` из bucket MinIO |
| **certbot** | Получение/продление Let's Encrypt (webroot) |

Образы **backend** и **worker** собираются из **`./backend`** (контекст сборки — каталог `backend/`, не корень репозитория).

---

## Dev vs Prod

| | **Dev** (`docker-compose.yml`) | **Prod** (`docker-compose.prod.yml`) |
|---|-------------------------------|----------------------------------------|
| Env | `backend/.env` (`env_file: ./backend/.env`) | **`.env.prod`** в **корне** репозитория |
| Backend | `uvicorn … --reload`, volume `./backend/app` | Gunicorn, без mount кода |
| Worker | есть | есть |
| MinIO | порты 9000/9001 наружу | только внутри сети compose |
| Nginx | нет | да |
| Keys | `./backend/keys` → `/app/keys` | то же |

---

## Переменные окружения

```bash
# Dev: см. документацию к env для локальной разработки (часто копируют из env.dev в backend/.env)

# Prod: шаблон в репозитории
cp env.prod.example .env.prod
# заполнить секреты; НЕ коммитить .env.prod
```

Ключевые группы в prod (неполный список — см. `env.prod.example`):

- **Домены:** `API_DOMAIN`, `PUBLIC_API_URL`, `FRONTEND_URL`, `ADMIN_FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `CERT_EMAIL`
- **Приложение:** `DEBUG`, `SECRET_KEY`, `ENCRYPTION_KEY`
- **JWT (RS256):** пути к PEM, `JWT_AUDIENCE`, `JWT_ISSUER`
- **БД:** `DATABASE_URL`, `POSTGRES_*`
- **Redis:** `REDIS_URL`
- **S3/MinIO:** `S3_ENDPOINT_URL`, ключи, `S3_BUCKET`, `S3_PUBLIC_URL`
- **Платежи:** `PAYMENT_PROVIDER`, Moneta и/или YooKassa по выбору
- **Почта, Telegram** — по необходимости

`scripts/deploy.sh` делает `set -a; source .env.prod` — переменные вроде **`API_DOMAIN`** нужны на хосте для health-check в конце скрипта.

Шаблон для продакшена с пояснениями: `docs/env-production-trichologia.ru.template.md`.

---

## Nginx (prod)

- Главный конфиг: `nginx/nginx.conf` (подключает `conf.d/*.conf`).
- Шаблоны: `nginx/templates/*.template` — подставляются через **envsubst** стандартным entrypoint-образа nginx (переменные из `environment` сервиса `nginx` в compose, напр. `API_DOMAIN`, `S3_BUCKET`).
- Файл **`nginx/templates/api.conf.template`**: HTTPS для API, прокси на `backend:8000`, **`location /media/`** → `http://minio:9000/${S3_BUCKET}/`.
- Редирект HTTP→HTTPS: см. `redirect.conf.template` при использовании.

Сертификаты: `./certbot/conf` и `./certbot/www` смонтированы в nginx и certbot.

---

## SSL

Первичное получение (на сервере, из корня репозитория, с заполненным `.env.prod`):

```bash
./scripts/init-ssl.sh
```

Скрипт запрашивает сертификат для **`API_DOMAIN`** через webroot и перезапускает nginx.

Продление (Makefile):

```bash
make ssl-renew
```

---

## Деплой на сервер

Типовой путь к коду на сервере в проекте: **`/opt/triback`**. Из корня репозитория:

```bash
./scripts/deploy.sh
```

Что делает скрипт (см. `scripts/deploy.sh`):

1. `source .env.prod`
2. `git pull origin main`
3. `docker compose -f docker-compose.prod.yml build backend`
4. `docker compose … run --rm backend alembic upgrade head`
5. `docker compose … up -d --no-deps --build backend worker`
6. `docker compose … restart nginx`
7. `docker image prune -f`
8. Проверка: `curl -sf "https://${API_DOMAIN}/api/v1/health"`

Важно: образ **worker** пересобирается в шаге `up … --build` для сервисов backend и worker.

---

## Makefile (корень репозитория)

| Цель | Действие |
|------|----------|
| `make dev` / `dev-down` / `dev-logs` | dev compose |
| `make prod` / `prod-down` / `prod-logs` | prod compose |
| `make migrate` | alembic upgrade (dev exec) |
| `make migrate-prod` | alembic upgrade одноразовым контейнером backend |
| `make migration msg="..."` | autogenerate (dev) |
| `make deploy` | `./scripts/deploy.sh` |
| `make backup` | `./scripts/backup.sh` |
| `make ssl-init` / `ssl-renew` | SSL |

---

## Бэкап БД

`scripts/backup.sh`: `pg_dump` из контейнера **postgres**, gzip в `./backups` (или `BACKUP_DIR`), ротация старше 30 дней.

На сервере перед запуском убедиться, что в окружении заданы `POSTGRES_USER` / `POSTGRES_DB` или используются дефолты скрипта, совпадающие с `.env.prod`.

---

## Healthcheck

- **backend** (prod): `curl -f http://localhost:8000/api/v1/health` (см. `docker-compose.prod.yml`).

---

## Чек-лист для AI

- [ ] Правки в `docker-compose*.yml` согласованы с путями (`./backend`, `.env.prod` в корне)
- [ ] Новые переменные окружения добавлены в `env.prod.example` и задокументированы
- [ ] Секреты не попадают в git
- [ ] После изменений API — health по-прежнему `/api/v1/health`
- [ ] Миграции применяются через `alembic upgrade head` в контейнере backend
- [ ] При смене домена API — обновить `API_DOMAIN`, nginx-шаблоны, SSL, CORS и URL в Moneta/фронте
