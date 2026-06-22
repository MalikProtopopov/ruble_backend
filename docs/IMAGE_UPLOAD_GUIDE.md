# Поддержка загрузки изображений (type=image)

## Что изменилось на бэкенде

Добавлен новый тип медиа `image` в endpoint `POST /api/v1/admin/media/upload`.

Раньше поддерживались только `video`, `document`, `audio`. Теперь можно загружать изображения (лого фондов, превью кампаний и т.д.) через тот же endpoint.

**Допустимые форматы:** `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `image/svg+xml`
**Максимальный размер:** 20 МБ
**S3-префикс:** `images/`

**Миграция БД:** `004_media_asset_type_image` — добавляет значение `image` в PostgreSQL enum `media_asset_type`. Накатывается автоматически при деплое (`alembic upgrade head`).

---

## Что нужно обновить в админке (admin-front)

### 1. Форма загрузки медиа — добавить тип `image`

В модалке/форме загрузки файлов (где пользователь выбирает тип: видео/документ/аудио) добавить вариант **"Изображение"** (`image`).

При отправке формы передавать `type=image`:

```js
const formData = new FormData();
formData.append('file', selectedFile);
formData.append('type', 'image'); // <-- новый тип
```

### 2. Загрузка лого фонда

При создании/редактировании фонда, если админ загружает логотип — использовать `type=image` вместо попытки отправить как `document` или `video`.

Флоу:
1. Админ выбирает файл изображения
2. `POST /media/upload` с `type=image` → получаем `{ id, url, ... }`
3. `PATCH /foundations/{id}` с `logo_url=<url из ответа>` или `logo_media_asset_id=<id из ответа>`

### 3. Превью (thumbnail) кампании

При загрузке превью-картинки для кампании — аналогично:
1. `POST /media/upload` с `type=image`
2. `PATCH /campaigns/{id}` с `thumbnail_url=<url>` или `thumbnail_media_asset_id=<id>`

### 4. Фильтр в медиабиблиотеке

Если в списке медиа (`GET /media`) есть фильтр по типу — добавить вариант `image`:

```
GET /api/v1/admin/media?type=image
```

### 5. Отображение в списке медиа

Для элементов с `type=image` показывать превью-картинку (тег `<img>`) вместо иконки файла.

---

## Что нужно обновить в клиентском приложении (мобильное/веб)

### Скорее всего ничего

Клиент получает готовые URL из API (`logo_url`, `thumbnail_url`, `video_url`). Изображения загружаются через стандартные теги `<img>` / `Image`. Бэкенд отдаёт корректные URL вида:

```
https://backend.porublyu.parmenid.tech/media/images/abc123.png
```

### Проверить

- Что `logo_url` фондов и `thumbnail_url` кампаний корректно рендерятся
- Что нет жёсткой фильтрации по content-type или расширениям на стороне клиента
- Если клиент сам загружает медиа (не только админка) — добавить `type=image` в форму загрузки

---

## Пример запроса

```bash
curl -X POST \
  https://backend.porublyu.parmenid.tech/api/v1/admin/media/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@/path/to/logo.png" \
  -F "type=image"
```

Ответ:
```json
{
  "id": "0195a1b2-c3d4-7e5f-8a90-abcdef123456",
  "key": "images/a1b2c3d4e5f6789012345678abcdef.png",
  "url": "https://backend.porublyu.parmenid.tech/media/images/a1b2c3d4e5f6789012345678abcdef.png",
  "filename": "logo.png",
  "size_bytes": 245760,
  "content_type": "image/png"
}
```
