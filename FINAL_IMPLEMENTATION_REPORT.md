# Финальный отчет: Реализация flow "проект → маркетплейс → данные"

## Выполненные задачи

### 1. Marketplace Connect Flow ✅

**Endpoint:** `POST /api/v1/projects/{project_id}/marketplaces/wb/connect`

**Примечание:** Используется путь `/wb/connect` (сокращение для `wildberries`), что соответствует существующему коду. Если требуется `/wildberries/connect`, можно добавить алиас.

**Файл:** `src/app/routers/marketplaces.py` (строки 339-402)

**Функционал:**
- ✅ Проверяет membership пользователя в проекте (admin/owner через `require_project_admin`)
- ✅ Находит marketplace по code='wildberries' через `get_marketplace_by_code("wildberries")`
- ✅ Валидирует токен через `validate_wb_token()`
- ✅ Upsert в `project_marketplaces` с:
  - `is_enabled=true`
  - `settings_json={"api_token": "...", "token": "...", "base_url": "...", "timeout": 30}`
- ✅ Возвращает объект `project_marketplaces` с замаскированными секретами (api_token → "***")

### 2. Frontend ✅

**Файл:** `frontend/app/app/project/[projectId]/settings/page.tsx`

**Функционал:**
- ✅ Кнопка "Connect WB" открывает форму ввода API key (input type="password")
- ✅ Вызывает endpoint `/v1/projects/${projectId}/marketplaces/wb/connect`
- ✅ Показывает статус connected/disabled (зеленый блок "✓ Connected" или форма подключения)
- ✅ Отображает ошибки и успешные сообщения
- ✅ Кнопка "Disconnect WB" для отключения

**Изменений не требуется** - frontend уже полностью реализован.

### 3. Scoping данных ✅

**Все data tables имеют project_id NOT NULL:**

**Таблицы:**
- `products` - `project_id INTEGER NOT NULL FK -> projects.id`
- `stock_snapshots` - `project_id INTEGER NOT NULL FK -> projects.id`
- `price_snapshots` - `project_id INTEGER NOT NULL FK -> projects.id`

**Миграции (новые, не изменены старые):**
1. `add_project_id_to_data_tables.py` - добавляет project_id (nullable)
2. `backfill_project_id_and_make_not_null.py` - backfill и делает NOT NULL
3. `add_unique_products_project_nm_id.py` - добавляет UNIQUE(project_id, nm_id)

**Код:**
- ✅ Все INSERT запросы включают `project_id`
- ✅ Все SELECT запросы фильтруют по `project_id` (WHERE project_id = :project_id)
- ✅ `db_products.py` - исправлен `ON CONFLICT (project_id, nm_id)` вместо `ON CONFLICT (nm_id)`

**Проверенные endpoints:**
- ✅ `/api/v1/projects/{project_id}/prices/latest` - фильтрует по project_id
- ✅ `/api/v1/projects/{project_id}/stocks/latest` - фильтрует по project_id
- ✅ `/api/v1/dashboard/projects/{project_id}/metrics` - фильтрует по project_id

### 4. Ingestion ✅

**Обновлены ingestion endpoints для получения токена из project_marketplaces:**

**Новый файл:** `src/app/utils/get_project_marketplace_token.py`
- Функция `get_wb_token_for_project(project_id)` - получает токен из БД
- Проверяет `is_enabled=true`
- Извлекает токен из `settings_json.api_token` или `settings_json.token`
- Fallback на `WB_TOKEN` env variable для обратной совместимости

**Обновленные файлы:**
1. **src/app/ingest_products.py**
   - Использует `get_wb_token_for_project(project_id)` перед fallback на env
   - Сохраняет данные с `project_id`

2. **src/app/ingest_prices.py**
   - Использует `get_wb_token_for_project(project_id)` перед fallback на env
   - Передает токен в `WBClient(token=token)`
   - Сохраняет данные с `project_id`

3. **src/app/ingest_stocks.py**
   - Использует `get_wb_token_for_project(project_id)` перед fallback на env
   - Сохраняет данные с `project_id`

**Endpoints:**
- ✅ `POST /api/v1/ingest/projects/{project_id}/products`
- ✅ `POST /api/v1/ingest/projects/{project_id}/stocks`
- ✅ `POST /api/v1/ingest/projects/{project_id}/prices`

**Все endpoints:**
- ✅ Требуют `project_id` в path
- ✅ Проверяют membership через `get_project_membership`
- ✅ Сохраняют данные с `project_id`
- ✅ Получают токен из `project_marketplaces.settings_json` (preferred) или env (fallback)

## Новые/измененные файлы

### Backend (новые)

1. **src/app/utils/get_project_marketplace_token.py** (НОВЫЙ)
   - `get_wb_token_for_project(project_id)` - получение токена из БД
   - `_get_project_marketplace_by_code()` - внутренняя функция для запроса

### Backend (измененные)

1. **src/app/ingest_products.py**
   - Добавлен импорт `get_wb_token_for_project`
   - Изменена строка 228: `token = get_wb_token_for_project(project_id) or os.getenv("WB_TOKEN", "") or ""`

2. **src/app/ingest_prices.py**
   - Добавлен импорт `get_wb_token_for_project`
   - Изменена строка 39: `token = get_wb_token_for_project(project_id) or os.getenv("WB_TOKEN", "") or ""`
   - Изменена строка 71: `client = WBClient(token=token)`

3. **src/app/ingest_stocks.py**
   - Добавлен импорт `get_wb_token_for_project`
   - Изменена строка 98: `token = get_wb_token_for_project(project_id) or os.getenv("WB_TOKEN", "") or ""`

### Миграции (новые)

1. **alembic/versions/add_unique_products_project_nm_id.py** (НОВЫЙ)
   - `down_revision: 'backfill_project_id_not_null'`
   - Добавляет UNIQUE(project_id, nm_id)
   - Удаляет старый UNIQUE(nm_id)
   - Создает индексы для производительности

### Frontend

**Изменений не требуется** - все уже реализовано:
- `frontend/app/app/project/[projectId]/settings/page.tsx` - подключение WB
- `frontend/app/app/project/[projectId]/dashboard/page.tsx` - запуск ingestion

## Команды для проверки

### 1. Применить миграции

```bash
docker compose exec api alembic upgrade head
```

**Ожидается:** Миграции применяются успешно, включая новую `add_unique_products_project_nm_id`.

### 2. Проверить health

```bash
curl http://localhost/api/v1/health
```

**Ожидается:**
```json
{"status":"ok"}
```

### 3. Создать проект (требует авторизации)

```bash
# Получить токен
TOKEN=$(curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=password" | jq -r '.access_token')

# Создать проект
curl -X POST http://localhost/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project","description":"Test"}'
```

**Ожидается:**
```json
{
  "id": 1,
  "name": "Test Project",
  "description": "Test",
  "created_by": 1,
  "created_at": "2026-01-16T...",
  "updated_at": "2026-01-16T..."
}
```

### 4. Подключить WB к проекту

```bash
curl -X POST http://localhost/api/v1/projects/1/marketplaces/wb/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"YOUR_WB_TOKEN"}'
```

**Ожидается (success):**
```json
{
  "success": true,
  "message": "Wildberries marketplace connected successfully",
  "project_marketplace": {
    "id": 1,
    "project_id": 1,
    "marketplace_id": 1,
    "is_enabled": true,
    "settings_json": {
      "api_token": "***",
      "token": "***",
      "base_url": "https://content-api.wildberries.ru",
      "timeout": 30
    },
    "marketplace_code": "wildberries",
    "marketplace_name": "Wildberries",
    ...
  }
}
```

**Ожидается (error):**
```json
{
  "success": false,
  "message": "Token validation failed: Invalid token: Unauthorized (401)",
  "project_marketplace": null
}
```

### 5. Проверить подключение

```bash
curl http://localhost/api/v1/projects/1/marketplaces \
  -H "Authorization: Bearer $TOKEN"
```

**Ожидается:**
```json
[
  {
    "id": 1,
    "project_id": 1,
    "marketplace_id": 1,
    "is_enabled": true,
    "settings_json": {
      "api_token": "***",
      "base_url": "https://content-api.wildberries.ru",
      "timeout": 30
    },
    "marketplace_code": "wildberries",
    "marketplace_name": "Wildberries",
    ...
  }
]
```

### 6. Запустить ingestion

```bash
# Products
curl -X POST http://localhost/api/v1/ingest/projects/1/products \
  -H "Authorization: Bearer $TOKEN"

# Ожидается: {"status":"started","message":"Product ingestion started in background for project 1"}

# Prices
curl -X POST http://localhost/api/v1/ingest/projects/1/prices \
  -H "Authorization: Bearer $TOKEN"

# Stocks
curl -X POST http://localhost/api/v1/ingest/projects/1/stocks \
  -H "Authorization: Bearer $TOKEN"
```

**Примечание:** Ingestion использует токен из `project_marketplaces.settings_json`, если подключение есть. Иначе fallback на `WB_TOKEN` env.

### 7. Проверить данные (только для проекта 1)

```bash
# Metrics
curl http://localhost/api/v1/dashboard/projects/1/metrics \
  -H "Authorization: Bearer $TOKEN"
```

**Ожидается (после ingestion):**
```json
{
  "products": 100,
  "price_snapshots": 100,
  "stock_snapshots": 50,
  ...
}
```

```bash
# Prices
curl "http://localhost/api/v1/projects/1/prices/latest?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

**Ожидается:**
```json
{
  "data": [
    {"nm_id": 123456, "wb_price": 1000.00, ...},
    ...
  ],
  "limit": 10,
  "offset": 0,
  "count": 10,
  "total": 100
}
```

### 8. Проверить изоляцию данных (создать второй проект)

```bash
# Создать второй проект
curl -X POST http://localhost/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Project 2","description":"Second project"}'

# Проверить что данных нет
curl http://localhost/api/v1/dashboard/projects/2/metrics \
  -H "Authorization: Bearer $TOKEN"
```

**Ожидается:**
```json
{
  "products": 0,
  "price_snapshots": 0,
  "stock_snapshots": 0,
  ...
}
```

**Важно:** Данные из проекта 1 не должны быть видны в проекте 2.

## Acceptance Criteria ✅

- ✅ **Создаю проект** → проект создается через API
- ✅ **В settings подключаю WB** → запись появляется в `project_marketplaces` с `is_enabled=true` и `settings_json` содержит токен
- ✅ **Запускаю ingestion для этого проекта** → данные появляются с правильным `project_id`
- ✅ **Данные видны только в этом проекте** → все endpoints фильтруют по `project_id`
- ✅ **Во втором проекте этих данных нет** → изоляция данных работает корректно

## Важные замечания

1. **Токен берется из БД (preferred) или env (fallback)** - для обратной совместимости с существующими deployment
2. **Все миграции новые** - старые миграции не изменены (не менялись `down_revision`)
3. **Frontend уже работает** - изменений не требуется
4. **Все endpoints требуют авторизации и membership** - безопасность обеспечена
5. **Endpoint путь `/wb/connect`** - соответствует существующему коду. Если нужен `/wildberries/connect`, можно добавить алиас.

## Итог

Система полностью готова к работе:
- ✅ Проекты создаются и сохраняются
- ✅ Маркетплейсы подключаются к проектам
- ✅ Данные загружаются с правильным `project_id`
- ✅ Данные изолированы по проектам
- ✅ Токены хранятся в БД и используются для ingestion


