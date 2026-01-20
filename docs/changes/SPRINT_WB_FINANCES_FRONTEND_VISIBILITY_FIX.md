# Исправление: WB Finances UI не отображался

## Проблема

После реализации функционала "WB Finances" пользователь не видел никаких изменений в UI, хотя frontend контейнер был пересобран.

## Корневая причина

**Ошибка в условии отображения секции WB Finances**

В файле `frontend/app/app/project/[projectId]/marketplaces/page.tsx` в строке 526 использовалось условие:
```typescript
{wbStatus?.connected && (
```

Но в интерфейсе `WBMarketplaceStatus` (определен в строках 26-32) **нет поля `connected`**. Доступные поля:
- `is_enabled: boolean`
- `is_configured: boolean`  ← правильное поле
- `credentials: { api_token: boolean }`
- `settings: { brand_id: number | null }`
- `updated_at: string`

В результате `wbStatus?.connected` всегда был `undefined`, поэтому секция "Wildberries — Finances" никогда не отображалась, даже когда WB был подключен.

## Что исправлено

### 1. Исправлено условие отображения секции

**Файл:** `frontend/app/app/project/[projectId]/marketplaces/page.tsx`

**Изменение:**
```diff
- {wbStatus?.connected && (
+ {wbStatus?.is_configured && (
```

Теперь секция отображается когда `is_configured === true`, что соответствует статусу "Connected ✅" в таблице маркетплейсов (используется то же условие в строке 376).

### 2. Проверена структура роутинга

Структура Next.js app router корректна:
- **Файл страницы marketplaces:** `frontend/app/app/project/[projectId]/marketplaces/page.tsx`
- **Файл страницы отчетов:** `frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx`
- **URL маршруты:** 
  - `/app/project/{projectId}/marketplaces` → страница маркетплейсов
  - `/app/project/{projectId}/wildberries/finances/reports` → страница списка отчётов

### 3. Проверены импорты и зависимости

- Импорты API client корректны
- Импорт globals.css корректный (соответствует другим страницам)
- Функция `handleWbFinancesIngest` правильно использует `apiPost`
- Обработка ошибок присутствует

## Изменённые файлы

1. `frontend/app/app/project/[projectId]/marketplaces/page.tsx` — исправлено условие отображения секции WB Finances

**Остальные файлы уже были корректными:**
- `frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx` — страница списка отчётов (без изменений)
- Все backend файлы (без изменений)

## Где теперь увидеть изменения в UI

### 1. Секция "Wildberries — Finances" на странице маркетплейсов

**Путь кликов:**
1. Открыть проект: `/app/projects` → выбрать проект
2. Перейти в маркетплейсы: меню проекта или прямой URL `/app/project/{projectId}/marketplaces`
3. Убедиться, что Wildberries подключен (статус "Connected ✅")
4. **Секция "Wildberries — Finances" отображается ниже таблицы маркетплейсов**

**Что содержит секция:**
- Поля выбора дат: Date From / Date To (по умолчанию: первый день текущего месяца — сегодня)
- Кнопка "Загрузить финансовые отчеты WB" → POST `/api/v1/projects/{projectId}/marketplaces/wildberries/finances/ingest`
- Кнопка "Открыть список отчётов" → переход на страницу списка

### 2. Страница списка отчётов

**URL:** `/app/project/{projectId}/wildberries/finances/reports`

**Как открыть:**
- Кнопка "Открыть список отчётов" в секции "Wildberries — Finances" на странице marketplaces
- Прямой переход по URL

**Что показывает:**
- Таблица с колонками: Report ID, Period From, Period To, Currency, Total Amount, Rows Count, Last Seen At
- Кнопка "Обновить список" (GET `/api/v1/projects/{projectId}/marketplaces/wildberries/finances/reports`)
- Кнопка "Назад к настройкам" → возврат на страницу marketplaces
- Пустое состояние: "Отчётов пока нет — загрузите их в настройках проекта" (если список пуст)

## Самопроверка (для разработчика)

### 1. Проверка отображения секции

1. Открыть страницу `/app/project/{projectId}/marketplaces` где `{projectId}` — ID проекта с подключенным Wildberries
2. Прокрутить вниз после таблицы "Available Marketplaces"
3. **Ожидаемый результат:** видна секция "Wildberries — Finances" с полями дат и двумя кнопками

**Если секция не видна:**
- Проверить, что Wildberries подключен (`is_configured === true`)
- Проверить в DevTools Console, что `wbStatus` загружается корректно
- Проверить, что endpoint `/api/v1/projects/{projectId}/marketplaces/wb` возвращает `is_configured: true`

### 2. Проверка страницы списка отчётов

1. На странице marketplaces нажать "Открыть список отчётов"
2. **Ожидаемый результат:** открывается страница `/app/project/{projectId}/wildberries/finances/reports`
3. Проверить в Network tab браузера, что выполняется GET запрос к `/api/v1/projects/{projectId}/marketplaces/wildberries/finances/reports`
4. **Ожидаемый результат:** ответ 200 OK с массивом отчётов (или пустой массив)

**Если страница не открывается:**
- Проверить, что файл существует: `frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx`
- Проверить структуру папок Next.js app router
- Проверить консоль браузера на ошибки JavaScript

## Технические детали

**Frontend стек:**
- Next.js 14.2.0 (App Router)
- React 18.3.1
- TypeScript
- Структура роутинга: `app/app/project/[projectId]/...`

**Условие отображения:**
- Секция показывается только если `wbStatus?.is_configured === true`
- Это соответствует логике в таблице маркетплейсов, где статус "Connected ✅" определяется так же: `wbStatus?.is_configured`

**API запросы:**
- Загрузка статуса WB: `GET /api/v1/projects/{projectId}/marketplaces/wb`
- Запуск ingestion: `POST /api/v1/projects/{projectId}/marketplaces/wildberries/finances/ingest`
- Список отчётов: `GET /api/v1/projects/{projectId}/marketplaces/wildberries/finances/reports`
