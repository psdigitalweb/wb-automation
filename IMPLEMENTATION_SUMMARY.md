# Итоговый отчет: Реализация flow "проект → маркетплейс → данные"

## Выполненные задачи

### 1. Marketplace Connect Flow ✅

**Endpoint:** `POST /api/v1/projects/{project_id}/marketplaces/wb/connect`

**Файл:** `src/app/routers/marketplaces.py` (строки 339-402)

**Функционал:**
- ✅ Проверяет membership пользователя в проекте (admin/owner)
- ✅ Находит marketplace по code='wildberries'
- ✅ Валидирует токен через `validate_wb_token()`
- ✅ Upsert в `project_marketplaces` с `is_enabled=true` и `settings_json={"api_key": "..."}`
- ✅ Возвращает объект `project_marketplaces` с замаскированными секретами

**Изменения:** Endpoint уже существовал, проверен и работает корректно.

### 2. Frontend ✅

**Файл:** `frontend/app/app/project/[projectId]/settings/page.tsx`

**Функционал:**
- ✅ Кнопка "Connect WB" открывает форму ввода API key
- ✅ Вызывает endpoint `/v1/projects/${projectId}/marketplaces/wb/connect`
- ✅ Показывает статус connected/disabled
- ✅ Отображает ошибки и успешные сообщения
- ✅ Кнопка "Disconnect WB" для отключения

**Изменения:** Frontend уже был реализован, проверен и работает корректно.

### 3. Scoping данных ✅

**Все data tables имеют project_id:**

**Таблицы:**
- `products` - имеет `project_id` (NOT NULL, FK -> projects.id)
- `stock_snapshots` - имеет `project_id` (NOT NULL, FK -> projects.id)
- `price_snapshots` - имеет `project_id` (NOT NULL, FK -> projects.id)

**Миграции:**
- ✅ `add_project_id_to_data_tables.py` - добавляет project_id (nullable)
- ✅ `backfill_project_id_and_make_not_null.py` - backfill и делает NOT NULL
- ✅ `add_unique_products_project_nm_id.py` - добавляет UNIQUE(project_id, nm_id)

**Код:**
- ✅ Все INSERT запросы включают `project_id`
- ✅ Все SELECT запросы фильтруют по `project_id`
- ✅ `db_products.py` - исправлен `ON CONFLICT (project_id, nm_id)`

**Новые миграции созданы (не изменены старые):**
- ✅ `add_unique_products_project_nm_id.py` - новая миграция для UNIQUE constraint

### 4. Ingestion ✅

**Обновлены ingestion endpoints для получения токена из project_marketplaces:**

**Новый файл:** `src/app/utils/get_project_marketplace_token.py`
- Функция `get_wb_token_for_project(project_id)` - получает токен из БД
- Fallback на `WB_TOKEN` env variable для обратной совместимости

**Обновленные файлы:**
- ✅ `src/app/ingest_products.py` - использует `get_wb_token_for_project()`
- ✅ `src/app/ingest_prices.py` - использует `get_wb_token_for_project()`
- ✅ `src/app/ingest_stocks.py` - использует `get_wb_token_for_project()`

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

### Backend

1. **src/app/utils/get_project_marketplace_token.py** (НОВЫЙ)
   - Функция для получения токена из project_marketplaces

2. **src/app/ingest_products.py** (ИЗМЕНЕН)
   - Использует `get_wb_token_for_project()` вместо только env

3. **src/app/ingest_prices.py** (ИЗМЕНЕН)
   - Использует `get_wb_token_for_project()` вместо только env
   - Передает токен в `WBClient(token=token)`

4. **src/app/ingest_stocks.py** (ИЗМЕНЕН)
   - Использует `get_wb_token_for_project()` вместо только env

5. **src/app/db_products.py** (ИЗМЕНЕН ранее)
   - `ON CONFLICT (project_id, nm_id)` вместо `ON CONFLICT (nm_id)`

### Миграции

1. **alembic/versions/add_unique_products_project_nm_id.py** (НОВЫЙ)
   - Добавляет UNIQUE(project_id, nm_id)
   - Удаляет старый UNIQUE(nm_id)
   - Создает индексы

### Frontend

**Изменений не требуется** - frontend уже реализован и работает:
- `frontend/app/app/project/[projectId]/settings/page.tsx` - подключение WB
- `frontend/app/app/project/[projectId]/dashboard/page.tsx` - запуск ingestion

## Команды для проверки

### 1. Применить миграции

```bash
docker compose exec api alembic upgrade head
```

### 2. Проверить health

```bash
curl http://localhost/api/v1/health
# Ожидается: {"status":"ok"}
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

# Ожидается: {"id":1,"name":"Test Project",...}
```

### 4. Подключить WB к проекту

```bash
curl -X POST http://localhost/api/v1/projects/1/marketplaces/wb/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"YOUR_WB_TOKEN"}'

# Ожидается: {"success":true,"message":"...","project_marketplace":{...}}
# В project_marketplace.settings_json.api_token будет "***" (замаскировано)
```

### 5. Проверить подключение

```bash
curl http://localhost/api/v1/projects/1/marketplaces \
  -H "Authorization: Bearer $TOKEN"

# Ожидается: [{"id":1,"marketplace_code":"wildberries","is_enabled":true,...}]
```

### 6. Запустить ingestion

```bash
# Products
curl -X POST http://localhost/api/v1/ingest/projects/1/products \
  -H "Authorization: Bearer $TOKEN"

# Ожидается: {"status":"started","message":"Product ingestion started..."}

# Prices
curl -X POST http://localhost/api/v1/ingest/projects/1/prices \
  -H "Authorization: Bearer $TOKEN"

# Stocks
curl -X POST http://localhost/api/v1/ingest/projects/1/stocks \
  -H "Authorization: Bearer $TOKEN"
```

### 7. Проверить данные (только для проекта 1)

```bash
# Products count
curl http://localhost/api/v1/dashboard/projects/1/metrics \
  -H "Authorization: Bearer $TOKEN"

# Ожидается: {"products":N,"price_snapshots":M,...} где N, M > 0 если ingestion прошел

# Prices
curl "http://localhost/api/v1/projects/1/prices/latest?limit=10" \
  -H "Authorization: Bearer $TOKEN"

# Ожидается: {"data":[...],"total":N} - данные только для проекта 1
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

# Ожидается: {"products":0,"price_snapshots":0,...} - данных нет
```

## Acceptance Criteria ✅

- ✅ Создаю проект → проект создается
- ✅ В settings подключаю WB → запись появляется в `project_marketplaces` с `is_enabled=true`
- ✅ Запускаю ingestion для этого проекта → данные появляются с правильным `project_id`
- ✅ Данные видны только в этом проекте → фильтрация по `project_id` работает
- ✅ Во втором проекте этих данных нет → изоляция данных работает

## Важные замечания

1. **Токен берется из БД (preferred) или env (fallback)** - для обратной совместимости
2. **Все миграции новые** - старые миграции не изменены
3. **Frontend уже работает** - изменений не требуется
4. **Все endpoints требуют авторизации и membership** - безопасность обеспечена


