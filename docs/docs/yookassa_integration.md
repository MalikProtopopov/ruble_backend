# Интеграция ЮKassa — «По Рублю»

Документ дополняет [api_public.md](api_public.md) (вебхук §10.1, донаты, подписки) и [porubly_functional_requirements_v3.md](porubly_functional_requirements_v3.md). Здесь — контракт между бэкендом и провайдером, без дублирования всех полей REST API приложения.

---

## 1. Официальная документация ЮKassa

Использовать как первичный источник по протоколу:

| Тема | URL |
|------|-----|
| Обзор API | [https://yookassa.ru/developers/api](https://yookassa.ru/developers/api) |
| Создание платежа | [https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start](https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start) |
| Входящие уведомления (вебхуки) | [https://yookassa.ru/developers/using-api/webhooks](https://yookassa.ru/developers/using-api/webhooks) |
| Сохранение способа оплаты | [https://yookassa.ru/developers/payment-acceptance/integration-scenarios/widget/additional-settings/save-payment-method](https://yookassa.ru/developers/payment-acceptance/integration-scenarios/widget/additional-settings/save-payment-method) |
| Автоплатежи (рекуррент) | [https://yookassa.ru/developers/payment-acceptance/scenario-extensions/recurring-payments](https://yookassa.ru/developers/payment-acceptance/scenario-extensions/recurring-payments) |
| Объект Payment | [https://yookassa.ru/developers/api#payment_object](https://yookassa.ru/developers/api#payment_object) |

---

## 2. Переменные окружения (бэкенд)

- `YOOKASSA_SHOP_ID` — идентификатор магазина  
- `YOOKASSA_SECRET_KEY` — секретный ключ  
- `YOOKASSA_WEBHOOK_SECRET` (опционально) — если используется отдельный секрет проверки уведомлений; иначе — проверка по документации ЮKassa (IP allowlist / подпись в зависимости от выбранного метода)  

**Тестовый контур:** отдельные shop_id/secret для sandbox, те же эндпоинты API с тестовыми картами из [документации](https://yookassa.ru/developers/payment-acceptance/testing-and-going-live/testing).

---

## 3. Типы платежей в продукте

| Сценарий | Создание платежа | `save_payment_method` | После успеха |
|----------|------------------|------------------------|--------------|
| Разовый донат (JWT или гость с email) | API приложения → ЮKassa Create Payment | `false` | `Donation.status = success`, вебхук |
| Первая оплата подписки (`bind-card`) | API приложения → Create Payment | `true` | Сохранить `payment_method_id` на подписке, активировать подписку |
| Рекуррентное списание | Create Payment с `payment_method_id` | — | `Transaction`, аллокация кампании |

В объекте платежа ЮKassa в **`metadata`** (строковые ключи/значения) передавать минимум:

- `kind`: `donation` | `subscription_first_charge` | `subscription_recurring` | `patron_link`  
- `user_id` — UUID пользователя (если известен)  
- `donation_id` / `subscription_id` / `transaction_id` — в зависимости от `kind`  
- `campaign_id` — если применимо  

Это упрощает обработчик вебхука и расследование инцидентов.

---

## 4. Вебхук `POST /api/v1/webhooks/yookassa`

- Регистрация URL в личном кабинете ЮKassa; события минимум: `payment.succeeded`, `payment.canceled` (и при необходимости `payment.waiting_for_capture` — если включён двухстадийный сценарий; для «По Рублю» обычно одностадийный capture).  
- **Идемпотентность:** одно событие может доставляться повторно. Обработка по `payment.id` (idempotency): повторный `payment.succeeded` не должен дважды увеличивать `collected_amount` / не должен дублировать запись в `transactions`.  
- **Ответ:** HTTP 200 с телом `{ "status": "ok" }` (как в api_public). Триггер благодарностей (THANKS-01) и пуши выполняются **после** успешной фиксации платежа в БД, а не «вместо» ответа ЮKassa.

Подробная матрица событий → действия БД — в [api_public.md §10.1](api_public.md).

---

## 5. Подтверждение оплаты и 3DS

- Для разовых платежей и первого платежа подписки клиент получает `confirmation.confirmation_url` (или аналог для embedded-сценария) — см. поле `payment_url` в ответах API приложения.  
- После прохождения 3DS итог приходит **только** через вебхук; клиент может опросить статус платежа по API ЮKassa при необходимости UX, но источником истины для бизнес-логики остаётся вебхук + запись в БД.

---

## 6. Рекуррентные списания

- Использовать сохранённый `payment_method_id` с платежа с `save_payment_method: true`.  
- Сумма первого списания подписки: дневная ставка × 7 (weekly) или × 30 (monthly) — см. [api_public.md §5](api_public.md).  
- Ошибки списания: soft/hard decline и retry — по правилам BILL-06 в ФТ v3.

---

## 7. Безопасность

- Секреты только на сервере; в мобильном клиенте — только `payment_url` или токен сценария, выданный сервером.  
- Логировать `payment.id`, `metadata.kind`, внутренние id сущностей; не логировать полные PAN/CVC.  
- Ограничить вход на вебхук по [рекомендациям ЮKassa](https://yookassa.ru/developers/using-api/webhooks#without-http-notification) (IP / проверка подлинности).

---

## 8. Связь с openAPI / тестами

После стабилизации контрактов имеет смысл добавить контрактные тесты на разбор тела вебхука (фикстуры из документации ЮKassa) и e2e в sandbox для одного доната и одного `bind-card`.
