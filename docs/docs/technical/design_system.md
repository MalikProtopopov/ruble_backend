# Design system (Flutter ↔ legacy Ruble)

Активная реализация: [flutter_app/lib/design_system/](../../flutter_app/lib/design_system/). Референс UIKit: [legacy/Ruble/UI/](../../legacy/Ruble/UI/).

## Шрифт Gilroy и semibold

В **legacy** в `UIFont` указан `gilroy-semibold`, в каталоге шрифтов лежат **regular / medium / bold** (файла `gilroy-semibold` в репозитории нет).

Во Flutter стили с суффиксом **bold** / **semibold** в [app_typography.dart](../../flutter_app/lib/design_system/app_typography.dart) используют **`FontWeight.w700`** и **`gilroy-bold.ttf`**. Это осознанная замена до появления отдельного semibold-файла.

Чтобы совпасть с iOS 1:1, добавьте `gilroy-semibold.ttf` в [flutter_app/assets/fonts/](../../flutter_app/assets/fonts/), зарегистрируйте вес **600** в `pubspec.yaml` и замените соответствующие стили на `FontWeight.w600`.

## Цвета

| Swift (`UIColor` extension) | Dart (`AppColors`) |
|-----------------------------|-------------------|
| `darkTextRUB` | `darkText` / `darkTextRUB` |
| `whiteRUB` | `white` / `whiteRUB` |
| `blueRUB` | `blue` / `blueRUB` |
| `lightBlueRUB` | `lightBlue` / `lightBlueRUB` |
| `darkBlueRUB` | `darkBlue` / `darkBlueRUB` |
| `grayRUB` | `gray` / `grayRUB` |
| `greenRUB` | `green` / `greenRUB` |
| `grayTextRUB` | `grayText` / `grayTextRUB` |
| `lightGrayRUB` | `lightGray` / `lightGrayRUB` |
| `darkGrayRUB` | `darkGray` / `darkGrayRUB` |
| `darkGrayTwoRUB` | `darkGrayTwo` / `darkGrayTwoRUB` |
| Linear gradient `#6165D3` → `#6EAAD3` | `AppGradients.buttonHorizontal` (направление как в iOS: справа налево) |
| `backgroundGradient` на карточке | `AppColors.backgroundGradientColors(cardGradientBottomAlpha)` |
| SberPay `#219F38` | `sberPayGreen` |

## Отступы и размеры (`AppSpacing`)

| Токен | pt | Источник в legacy |
|-------|-----|-------------------|
| `screenHorizontal` | 16 | Частые leading/trailing констрейнты |
| `sm` | 8 | `stackView.spacing`, мелкие отступы |
| `md` | 12 | |
| `lg` | 16 | |
| `xl` | 20 | Select pay → кнопка |
| `xxl` | 24 | |
| `primaryButtonHeight` | 44 | Кнопка «Помочь», донат |
| `donateChipRowHeight` | 36 | Ряд сумм 1/2/5/10 ₽ |
| `selectPayMethodRowHeight` | 48 | Строка способа оплаты |
| `sheetSelectButtonHeight` | 40 | «Выбрать» в sheet оплаты |
| `homeCardBottomGradientHeight` | 350 | Градиент снизу карточки ленты |
| `shareButtonSize` | 32 | Иконка share на карточке |

## Радиусы (`AppRadii`)

| Токен | pt | Назначение |
|-------|-----|------------|
| `sm` | 8 | Кнопки, чипы, поля |
| `descriptionMore` | 11 | Кнопка «Подробнее» на карточке |
| `card` | 12 | Карточки контента, листы |
| `feedClip` | 16 | Скругление ячейки ленты, верх sheet |

## Типографика (`AppTypography`)

Имена соответствуют [legacy/Ruble/UI/UIFont.swift](../../legacy/Ruble/UI/UIFont.swift): `bold32`, `medium18`, `regular14`, и т.д. Дополнительно: `medium18White`, `bold14Blue` (шаринг).

## Компоненты (`design_system/widgets/`)

| Виджет | Назначение | Где используется |
|--------|------------|------------------|
| `AppGradientButton` | CTA 44pt, градиент или заливка (SberPay) | Лента, донат |
| `AppFundProgressBar` | Прогресс «собрано / цель», полоса 2pt | Лента |
| `AppDonateAmountChips` | Чипы сумм, border 1.5 | Донат |
| `AppSheetGrabber` | Индикатор 40×4 | Sheets |
| `AppSheetShell` | Оболочка sheet с отступами и grabber | По необходимости |

## Тема приложения

[flutter_app/lib/core/theme/app_theme.dart](../../flutter_app/lib/core/theme/app_theme.dart): `useMaterial3: false` для более плоского вида, ближе к UIKit.

## Таб бар

Чёрный фон, выбранный пункт белый (`whiteRUB`), невыбранный `darkGrayRUB` — как [TabBarController](../../legacy/Ruble/TabBar/View/TabBarController.swift).
