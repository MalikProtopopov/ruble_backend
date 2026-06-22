# Исправление медиа-ссылок (404 ошибки)

## Что было сделано на сервере бэкенда

1. **Обновлены файлы бэкенда** (скопированы на сервер):
   - `app/core/config.py` — добавлена функция `build_media_url(s3_key)` для динамического построения URL
   - `app/api/v1/media_proxy.py` — **новый прокси-эндпоинт** `/media/{s3_key}`, который проксирует запросы к MinIO
   - `app/api/v1/admin/media.py` — все URL вычисляются динамически из `s3_key`, добавлен эндпоинт `/reindex-urls`
   - `app/services/media_asset_resolve.py` — URL для кампаний/фондов вычисляется динамически
   - `app/services/media.py` — использует `build_media_url()`
   - `app/main.py` — подключен роутер `media_proxy`

2. **Обновлён `backend/.env`** на сервере:
   ```
   S3_PUBLIC_URL=https://backend.porublyu.parmenid.tech/media
   ```
   (было: `https://backend.porublyu.parmenid.tech/s3/porubly` — этот путь не существовал)

3. **Обновлены URL в базе данных** (через SQL):
   - `media_assets.public_url` — 5 записей исправлено
   - `campaigns.video_url` — 1 запись исправлена
   - Все URL теперь вида: `https://backend.porublyu.parmenid.tech/media/videos/xxx.mp4`

4. **Перезапущены контейнеры** backend, worker, scheduler

5. **Проверено**: все типы файлов (видео, аудио, PDF) доступны через новые URL

---

## Как теперь работает схема

```
Клиент/Админка  -->  https://backend.porublyu.parmenid.tech/media/videos/xxx.mp4
                          |
                    системный nginx (certbot SSL)
                          |
                    localhost:8000 (FastAPI в Docker)
                          |
                    /media/{s3_key} прокси-эндпоинт
                          |
                    MinIO (minio:9000, бакет "porubly")
```

Все медиа-файлы теперь обслуживаются через FastAPI прокси `/media/`. Новые загрузки автоматически получают правильные URL.

---

## Что нужно сделать в админке (admin-front)

### Ничего менять не нужно

Админка уже работает корректно:
- Фронт получает URL медиа из API (поля `url`, `video_url`, `thumbnail_url`, `logo_url`)
- API теперь отдаёт правильные URL вида `https://backend.porublyu.parmenid.tech/media/...`
- Фронт использует обычные `<img>` и стандартные теги, не `next/image` — ограничений по доменам нет
- `.env` фронта не содержит S3-настроек — только `NEXT_PUBLIC_API_URL`

### Проверка в админке

1. Откройте https://adminfront.porublyu.parmenid.tech
2. Зайдите в раздел "Медиа" — убедитесь, что URL в списке начинаются с `.../media/...`
3. Загрузите новый файл — URL должен быть вида `https://backend.porublyu.parmenid.tech/media/videos/xxx.mp4`
4. Откройте кампанию — убедитесь, что видео и thumbnail отображаются

---

## Что нужно сделать в клиентском приложении (мобильное/веб)

### Вариант 1: Если приложение получает URL из API (скорее всего так)

Ничего менять не нужно. API теперь отдаёт корректные URL. Проверьте:
- Откройте список кампаний через API: `GET /api/v1/campaigns`
- Убедитесь, что `video_url`, `thumbnail_url` содержат `https://backend.porublyu.parmenid.tech/media/...`
- Эти URL корректно загружают медиа (проверено)

### Вариант 2: Если в клиентском приложении захардкожен базовый URL для медиа

Найдите и замените:
```
# БЫЛО (не работало):
https://backend.porublyu.parmenid.tech/s3/porubly/

# СТАЛО:
https://backend.porublyu.parmenid.tech/media/
```

### Общие рекомендации для клиента

- Убедитесь, что клиент **не кеширует** старые URL с `/s3/porubly/` — если кеш есть, очистите его
- Видео, аудио, PDF и изображения — всё доступно через один базовый путь `/media/`
- Если клиент использует background download или кеширование медиа — URL структура теперь стабильна и не изменится

---

## На будущее

- При новой загрузке медиа URL формируется автоматически из `S3_PUBLIC_URL` + `s3_key`
- Если домен API изменится — достаточно обновить `S3_PUBLIC_URL` в `backend/.env` и вызвать `POST /api/v1/admin/media/reindex-urls` (с admin-токеном) для обновления старых записей
- API отдаёт URL динамически из `s3_key` для медиа-ассетов, поэтому изменение `S3_PUBLIC_URL` мгновенно влияет на выдаваемые URL
