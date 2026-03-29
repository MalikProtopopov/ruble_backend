# Фаза API и платежей (после моков)

Краткий чеклист для следующего этапа после [flutter_app](../../flutter_app):

1. **Репозитории:** заменить `MockCampaignRepository` / `MockThanksRepository` на реализации с `dio` или `http`; вынести `baseUrl` и заголовки авторизации в конфиг (аналог пустого `baseUrl` в [legacy/Ruble/Core/NetworkLayer/NetworkRequest.swift](../../legacy/Ruble/Core/NetworkLayer/NetworkRequest.swift)).
2. **Модели:** сохранить поля `Campaign` и `DocumentItem` совместимыми с JSON бэкенда; при расхождении добавить `fromJson` / `json_serializable`.
3. **Медиа:** при появлении CDN заменить `videoAssetPath` на URL и использовать `video_player` с сетевым источником (кэш при необходимости через `cached_video_player` или аналог).
4. **Платежи:** подключить SDK банка/агрегатора для СБП, SberPay и карт; не хранить PAN/CVC в `SharedPreferences` или в состоянии приложения — только токены от провайдера.
5. **Ошибки сети:** централизованная обработка и отображение пользователю (в iOS `NetworkManagerImp` при failure не вызывал completion — на Flutter избегать такой потери ошибки).
