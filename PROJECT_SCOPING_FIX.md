# Исправление scoping данных по project_id

## Проблема

Данные создавались без `project_id`, что ломало scoping - все проекты видели одни и те же данные.

## Решение

### 1. Обновлены ingestion endpoints

Все ingestion endpoints теперь требуют `project_id` и проверяют membership:

**Было:**
- `POST /api/v1/ingest/products`
- `POST /api/v1/ingest/stocks`
- `POST /api/v1/ingest/prices`

**Стало:**
- `POST /api/v1/ingest/projects/{project_id}/products`
- `POST /api/v1/ingest/projects/{project_id}/stocks`
- `POST /api/v1/ingest/projects/{project_id}/prices`

Все эндпоинты требуют:
- `Authorization: Bearer TOKEN`
- Проверку membership через `get_project_membership`

### 2. Обновлены INSERT запросы

Все INSERT запросы теперь включают `project_id`:

- **products**: `db_products.py::upsert_products(rows, project_id)`
- **stock_snapshots**: `ingest_stocks.py::ingest_stocks(project_id)`
- **price_snapshots**: `ingest_prices.py::ingest_prices(project_id)`

### 3. Миграция backfill

**Файл:** `alembic/versions/backfill_project_id_and_make_not_null.py`

Миграция:
1. Определяет целевой проект для backfill:
   - Если 1 проект: привязывает все данные к нему
   - Если 0 или >1 проектов: создает "Legacy" проект и привязывает все данные к нему
2. Заполняет `project_id` для всех существующих строк в `products`, `stock_snapshots`, `price_snapshots`
3. Делает `project_id` NOT NULL (после backfill)

**Применить:**
```bash
docker compose exec api alembic upgrade head
```

### 4. Обновлен фронтенд

**Файл:** `frontend/app/app/project/[projectId]/dashboard/page.tsx`

Все ingestion запросы обновлены для передачи `project_id`:
- `triggerIngest()` → `/v1/ingest/projects/${projectId}/${type}`
- `triggerFrontendPricesIngest()` → `/v1/ingest/projects/${projectId}/frontend-prices/brand`

## Manual Test

### Подготовка

```bash
# 1. Убедитесь, что контейнеры запущены и миграции применены
docker compose up -d
docker compose exec api alembic upgrade head

# 2. Получите токен аутентификации (создайте пользователя если нужно)
# TODO: Добавить инструкцию по получению токена

export AUTH_TOKEN="Bearer YOUR_TOKEN_HERE"
```

### Тест 1: Создание проектов и проверка scoping

```bash
# Создайте проект A
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Project A","description":"Test A"}' \
  | jq -r '.id'

# Сохраните ID проекта A (например, PROJECT_A_ID=1)

# Создайте проект B
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Project B","description":"Test B"}' \
  | jq -r '.id'

# Сохраните ID проекта B (например, PROJECT_B_ID=2)

# Загрузите stocks для проекта A (если WB настроен)
curl -X POST "http://localhost:8000/api/v1/ingest/projects/${PROJECT_A_ID}/stocks" \
  -H "Authorization: ${AUTH_TOKEN}"

# Подождите 10-30 секунд для завершения ingestion

# Проверьте stocks в проекте A
curl -X GET "http://localhost:8000/api/v1/projects/${PROJECT_A_ID}/stocks/latest?limit=10" \
  -H "Authorization: ${AUTH_TOKEN}" | jq '.data | length'

# Должно быть > 0 если данные загрузились

# Проверьте stocks в проекте B (должно быть пусто)
curl -X GET "http://localhost:8000/api/v1/projects/${PROJECT_B_ID}/stocks/latest?limit=10" \
  -H "Authorization: ${AUTH_TOKEN}" | jq '.data | length'

# Должно быть 0 - данные из проекта A не видны в проекте B!
```

### Тест 2: Проверка через БД

```bash
# Проверьте stocks в БД для проекта A
docker compose exec postgres psql -U wb -d wb -c \
  "SELECT COUNT(*) FROM stock_snapshots WHERE project_id = ${PROJECT_A_ID};"

# Проверьте stocks в БД для проекта B
docker compose exec postgres psql -U wb -d wb -c \
  "SELECT COUNT(*) FROM stock_snapshots WHERE project_id = ${PROJECT_B_ID};"

# Должно быть 0 - данные из проекта A не должны быть в проекте B!
```

### Тест 3: Автоматический скрипт

```bash
chmod +x scripts/test_project_scoping.sh
export AUTH_TOKEN="Bearer YOUR_TOKEN_HERE"
./scripts/test_project_scoping.sh
```

## Измененные файлы

### Backend

1. `src/app/db_products.py` - добавлен `project_id` в `upsert_products()`
2. `src/app/ingest_products.py` - эндпоинт обновлен для `project_id`
3. `src/app/ingest_stocks.py` - эндпоинт и SQL обновлены для `project_id`
4. `src/app/ingest_prices.py` - эндпоинт и SQL обновлены для `project_id`

### Миграции

1. `alembic/versions/add_project_id_to_data_tables.py` - добавляет `project_id` колонки
2. `alembic/versions/backfill_project_id_and_make_not_null.py` - backfill и NOT NULL

### Frontend

1. `frontend/app/app/project/[projectId]/dashboard/page.tsx` - обновлены ingestion запросы

## Важно

1. **Миграции должны быть применены** перед использованием новых endpoints
2. **Существующие данные** будут автоматически привязаны к проекту (или созданному "Legacy" проекту)
3. **Все новые данные** будут создаваться с `project_id`
4. **Project_id стал обязательным** после backfill миграции

## Откат изменений

Если нужно откатить:

```bash
# Откатить миграцию backfill (сделает project_id nullable)
docker compose exec api alembic downgrade -1

# Откатить добавление project_id колонок
docker compose exec api alembic downgrade -1
```

Однако откат не удалит данные, которые уже были созданы с `project_id`.


