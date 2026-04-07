# Модуль «Документы»: как реализовано в Mediann и как повторить в другом проекте

Документ для бэкенд-разработчика: схема БД, API, типы данных, жизненный цикл, файлы, фича-флаги, права, интеграции. Источник в репозитории: `backend/app/modules/documents/`, миграция `011_create_documents.py`, тесты `tests/api/v1/test_documents_api.py`, `tests/unit/services/test_document_service.py`.

---

## 1. Назначение модуля

Юридические и корпоративные документы (политика конфиденциальности, оферта и т.п.) с:

- **мультиязычностью** (отдельная строка на язык);
- **статусом публикации** (черновик / опубликован / архив);
- **опциональным файлом** (PDF, DOCX и др.) в объектном хранилище;
- **публичным API** (только опубликованные) и **админским CRUD**;
- **slug** для URL на сайте;
- **оптимистичной блокировкой** при обновлении.

---

## 2. База данных

### 2.1. Таблица `documents`

| Поле | Тип | NULL | Описание |
|------|-----|------|----------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL | FK → `tenants.id`, **ON DELETE CASCADE** |
| `status` | VARCHAR(20) | NOT NULL, default `draft` | `draft` \| `published` \| `archived` (CHECK в БД) |
| `document_version` | VARCHAR(50) | NULL | Версия для отображения («1.0», «v2.3») |
| `document_date` | DATE | NULL | Дата документа (юридическая/отчётная) |
| `published_at` | TIMESTAMPTZ | NULL | Проставляется при первом publish |
| `file_url` | VARCHAR(500) | NULL | URL файла после загрузки (S3/CDN) |
| `sort_order` | INTEGER | NOT NULL, default 0 | Порядок в публичном списке |
| `version` | INTEGER | NOT NULL, default 1 | Optimistic locking |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL | |
| `deleted_at` | TIMESTAMPTZ | NULL | **Soft delete** |

**Индексы:**

- `ix_documents_tenant` (`tenant_id`)
- `ix_documents_published` (`tenant_id`, `status`) **WHERE** `deleted_at IS NULL AND status = 'published'`
- `ix_documents_date` (`document_date`)

### 2.2. Таблица `document_locales`

| Поле | Тип | NULL | Описание |
|------|-----|------|----------|
| `id` | UUID | PK | |
| `document_id` | UUID | NOT NULL | FK → `documents.id`, **ON DELETE CASCADE** |
| `locale` | VARCHAR(5) | NOT NULL | `ru`, `en`, … |
| `title` | VARCHAR(255) | NOT NULL | CHECK length ≥ 1 |
| `slug` | VARCHAR(255) | NOT NULL | CHECK length ≥ 2 |
| `excerpt` | VARCHAR(500) | NULL | Краткое описание |
| `full_description` | TEXT | NULL | HTML-текст страницы документа |
| `meta_title` | VARCHAR(70) | NULL | SEO |
| `meta_description` | VARCHAR(160) | NULL | SEO |
| `meta_keywords` | VARCHAR(255) | NULL | из SEOMixin (в миграции есть) |
| `og_image` | VARCHAR(500) | NULL | из SEOMixin |
| `created_at`, `updated_at` | TIMESTAMPTZ | NOT NULL | |

**Ограничения:**

- **UNIQUE** (`document_id`, `locale`) — один набор полей на язык
- Индекс `ix_document_locales_slug` (`locale`, `slug`) — ускорение публичной выдачи по slug

### 2.3. Уникальность slug

В приложении вызывается **`check_slug_unique`**: slug уникален в рамках **tenant + locale** среди документов без soft-delete (см. `app/modules/localization/helpers.py`). При обновлении передаётся `exclude_parent_id` = id текущего документа.

**Рекомендация для другого проекта:** либо тот же подход (уникальность в коде + индекс), либо **UNIQUE (tenant_id, locale, slug)** через join/view — в Mediann уникальность slug не в одной таблице, а проверяется запросом.

---

## 3. Жизненный цикл и «активность» документа

### 3.1. Статусы (`DocumentStatus`)

| Значение | Смысл |
|----------|--------|
| `draft` | Не виден публично |
| `published` | Виден в публичном API и sitemap |
| `archived` | В БД допустим; в текущем API **нет отдельного эндпоинта archive** — можно выставить через `PATCH` с `status`, либо добавить эндпоинт по аналогии с publish |

### 3.2. Методы на модели

- `publish()` — `status = published`, при отсутствии `published_at` выставить «сейчас» (UTC).
- `unpublish()` — `status = draft` (**published_at не очищается** в текущей реализации).
- `archive()` — `status = archived` (используйте при расширении API).

### 3.3. Удаление

**DELETE** в админке = **soft delete** (`deleted_at`), не физическое удаление строки.

### 3.4. Публичная выборка

Условия: `deleted_at IS NULL`, `status = 'published'`, для списка/детали дополнительно фильтр по **locale** через join с `document_locales`.

Сортировка публичного списка: `sort_order`, затем `document_date DESC NULLS LAST`.

---

## 4. API (префикс приложения: `/api/v1`)

### 4.1. Публичные маршруты (без JWT)

Зависимость: **feature flag `documents`** для тенанта + `tenant_id` из публичного контекста (query / заголовок — как в вашем `PublicTenantId`).

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/public/documents` | Список опубликованных, пагинация, `search` по title, фильтр `document_date_from` / `document_date_to` |
| GET | `/public/documents/{slug}` | Один документ по slug **в запрошенной локали** |

Ответ списка: **без** полного `full_description` (экономия трафика). Детальная карточка — с полным HTML.

### 4.2. Админские маршруты (JWT + tenant)

Зависимости: **feature `documents`** + RBAC:

| Permission | Операции |
|------------|----------|
| `documents:read` | GET список, GET по id |
| `documents:create` | POST |
| `documents:update` | PATCH, publish, unpublish, upload/delete file |
| `documents:delete` | DELETE (soft) |

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/admin/documents` | Список с фильтрами: `status`, `search`, даты, `sort_by`, `sort_direction` |
| POST | `/admin/documents` | Создание + массив `locales` (минимум 1) |
| GET | `/admin/documents/{id}` | Деталь |
| PATCH | `/admin/documents/{id}` | Частичное обновление; **обязательное поле `version`** для optimistic lock |
| DELETE | `/admin/documents/{id}` | Soft delete |
| POST | `/admin/documents/{id}/publish` | Опубликовать |
| POST | `/admin/documents/{id}/unpublish` | В черновик |
| POST | `/admin/documents/{id}/file` | multipart: загрузка файла |
| DELETE | `/admin/documents/{id}/file` | Удалить файл из хранилища и обнулить `file_url` |

`file_url` **не** передаётся в теле create/update — только отдельными эндпоинтами файла.

---

## 5. Типы данных (Pydantic / контракт API)

### 5.1. Создание (`DocumentCreate`)

- `status` (default `draft`)
- `document_version`, `document_date`, `sort_order`
- `locales`: список объектов с полями: `locale`, `title`, `slug`, `excerpt`, `full_description`, `meta_title`, `meta_description` — **минимум одна локаль**

### 5.2. Обновление (`DocumentUpdate`)

- Опционально: `status`, `document_version`, `document_date`, `sort_order`, `locales`
- **Обязательно:** `version` (текущая версия сущности с сервера)

Локали в update: по `locale` ищется существующая строка — обновление полей; если локали не было — **создание** новой.

### 5.3. Ответ админки (`DocumentResponse`)

Все поля документа + `id`, `tenant_id`, `file_url`, `version`, `published_at`, `created_at`, `updated_at`, массив `locales` с id и метками времени.

### 5.4. Публичный ответ (`DocumentPublicResponse`)

Плоский DTO для одной локали: `slug`, `title`, `excerpt`, `full_description` (опционально в списке), `file_url`, `document_version`, `document_date`, `published_at`, meta.

Маппинг: `mappers.py` — если локаль не найдена, fallback на первую доступную; иначе ошибка `LocaleDataMissingError`.

---

## 6. Загрузка файлов

- Сервис: **`DocumentUploadService`** (`upload_service.py`) — наследник image-upload с другим whitelist MIME и лимитом **50 MB**.
- Разрешённые типы: PDF, DOC/DOCX, XLS/XLSX, PPT/PPTX, TXT, CSV.
- Ключ S3: `{tenant_id}/documents/{entity_id}_{suffix}.{ext}` (как у картинок, но папка `documents`).
- При замене файла старый URL передаётся в upload — удаление/замена по политике вашего `S3Service`.

**Для другого проекта:** вынести whitelist и max size в конфиг; при необходимости хранить не URL, а `storage_key` + отдельная таблица вложений.

---

## 7. Фича-модуль и биллинг

- В БД: feature flag с именем **`documents`** (таблица `feature_flags`, `tenant_id` + `feature_name`).
- Зависимости роутов: `require_documents` / `require_documents_public` (см. `middleware/feature_check.py`).
- В биллинге модуль с slug **`documents`** может входить в планы (`billing_modules` / `tenant_modules`).

Без включённого флага админ получает ошибку «feature disabled»; публичный API для скрытия факта существования модуля может отдавать **404** (как реализовано для public feature check).

---

## 8. Интеграции

- **Sitemap:** `sitemap_service.py` — сегмент `documents`, URL вида `/documents/{slug}` для опубликованных записей в нужной локали.
- **Меню админки:** пункт навигации с `feature: "documents"`, `perm: "documents:read"` (см. `auth_router.py`).

---

## 9. Чеклист для реализации в другом проекте

1. **Миграции:** таблицы `documents` и `document_locales` как выше; FK и CHECK на `status`.
2. **Сервисный слой:** CRUD, список опубликованных с join по locale и корректным **count** (подзапрос / distinct), `check_slug_unique` или эквивалент.
3. **Optimistic locking:** инкремент `version` при успешном PATCH (как в `BaseService` / `check_version`).
4. **Публичные эндпоинты:** только `published`, без утечки черновиков.
5. **Файлы:** отдельные POST/DELETE, валидация MIME и размера, привязка к `tenant_id`.
6. **RBAC:** четыре права `documents:*` и назначение ролям.
7. **Feature flag** (если SaaS): единое имя, например `documents`.
8. **Тесты:** публичный список/деталь, админ CRUD, slug draft недоступен публично, конфликт версии при PATCH.
9. **Опционально:** эндпоинт `archive`, очистка `published_at` при unpublish — зафиксировать в продуктовых правилах.

---

## 10. Карта файлов в Mediann

| Файл | Роль |
|------|------|
| `documents/models.py` | ORM, статусы, publish/unpublish/archive |
| `documents/schemas.py` | Pydantic, enum статусов |
| `documents/service.py` | Бизнес-логика, пагинация, фильтры |
| `documents/router.py` | FastAPI routes |
| `documents/mappers.py` | ORM → публичные DTO |
| `media/upload_service.py` | `DocumentUploadService`, `document_upload_service` |
| `localization/helpers.py` | `check_slug_unique` |
| `middleware/feature_check.py` | `require_documents`, `require_documents_public` |

Этого достаточно, чтобы воспроизвести модуль на другом стеке (Nest, Django, Go и т.д.) с сохранением контрактов и поведения.
