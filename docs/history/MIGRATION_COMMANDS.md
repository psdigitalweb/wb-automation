# Команды для применения миграций БД

## Предварительные проверки

```bash
# 1. Проверить текущее состояние миграций
docker compose exec api alembic current
docker compose exec api alembic history

# 2. Проверить схему БД (если скрипт доступен)
docker compose exec api python scripts/db_audit.py
```

## Применение миграций

```bash
# Применить все миграции до HEAD
docker compose exec api alembic upgrade head

# Или пошагово (для отладки)
docker compose exec api alembic upgrade +1  # Применить следующую миграцию
```

## Проверка после миграций

### 1. Проверка API health

```bash
curl http://localhost/api/v1/health
# Ожидается: {"status":"ok"}
```

### 2. Проверка создания проекта (требует авторизации)

```bash
# Получить токен (пример)
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

### 3. Проверка привязки маркетплейса (требует авторизации и проекта)

```bash
# Привязать WB к проекту
curl -X POST http://localhost/api/v1/projects/1/marketplaces/wb/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"YOUR_WB_TOKEN"}'

# Ожидается: {"success":true,"message":"...","project_marketplace":{...}}
```

### 4. Проверка фильтрации по project_id

```bash
# Получить продукты проекта (должны быть пустыми для нового проекта)
curl http://localhost/api/v1/projects/1/prices/latest \
  -H "Authorization: Bearer $TOKEN"

# Ожидается: {"data":[],"limit":50,"offset":0,"count":0,"total":0}
```

### 5. Проверка UNIQUE constraint на products

```bash
# Попытка создать продукт с дублирующимся nm_id в том же проекте должна обновить существующий
# Попытка создать продукт с тем же nm_id в другом проекте должна создать новый
```

## Откат миграций (если нужно)

```bash
# Откатить последнюю миграцию
docker compose exec api alembic downgrade -1

# Откатить до конкретной версии
docker compose exec api alembic downgrade add_marketplaces_tables

# Откатить все (ОСТОРОЖНО!)
docker compose exec api alembic downgrade base
```

## Список созданных/измененных миграций

1. **add_project_id_to_data_tables.py** - ИСПРАВЛЕН: изменен `down_revision` с `optimize_v_article_base` на `add_marketplaces_tables`

2. **backfill_project_id_and_make_not_null.py** - ИСПРАВЛЕН: изменен `down_revision` с `add_marketplaces_tables` на `add_project_id_to_data`

3. **add_unique_products_project_nm_id.py** - СОЗДАН: добавляет UNIQUE(project_id, nm_id) вместо UNIQUE(nm_id)

## Изменения в коде

1. **src/app/db_products.py** - ИСПРАВЛЕН: `ON CONFLICT (nm_id)` → `ON CONFLICT (project_id, nm_id)`

2. **src/app/routers/projects.py** - ИСПРАВЛЕН: убран вызов `ensure_schema()` на import-time

3. **alembic/MIGRATIONS_ORDER.md** - ОБНОВЛЕН: добавлены новые миграции в правильном порядке

## Важные замечания

1. **Порядок миграций критичен** - миграции должны применяться в правильном порядке
2. **Backfill может создать "Legacy" проект** - если данных много и проектов нет/много
3. **UNIQUE constraint может упасть** - если есть дубликаты nm_id в разных проектах (но это нормально после миграции)
4. **Seed-данные marketplaces** - автоматически создаются в миграции `add_marketplaces_tables` и в `startup_event` (с проверкой)


