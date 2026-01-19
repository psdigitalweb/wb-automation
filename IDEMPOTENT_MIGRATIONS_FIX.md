# Исправление: Идемпотентные миграции

## Что было неправильно и почему

**Проблема:** Я изменил старые миграции (initial, add_brand, add_users и т.д.), добавив в них проверки и `IF NOT EXISTS`. Это **неправильно**, потому что:

1. **История миграций должна быть неизменяемой** - старые миграции нельзя менять после применения в продакшене
2. Изменение старых миграций нарушает принцип идемпотентности истории Alembic
3. Это может привести к проблемам при откате миграций или при применении на других окружениях

**Правильный подход:** Создать отдельную repair-миграцию после head, которая исправляет schema drift безопасным способом.

## Что я откатил/изменил

### Откатил изменения в старых миграциях (вернул к исходному виду):

1. **`alembic/versions/a77217f699d1_initial_migration.py`**
   - Убрал проверки существования таблиц
   - Вернул стандартные `op.create_table()` и `op.create_index()`

2. **`alembic/versions/e1dcde5e611e_add_brand_to_products.py`**
   - Убрал проверки и `IF NOT EXISTS`
   - Вернул стандартные `op.add_column()` и `op.create_index()`

3. **`alembic/versions/add_product_details_fields.py`**
   - Убрал проверки и `IF NOT EXISTS`
   - Вернул стандартные `op.add_column()` и `op.create_index()`

4. **`alembic/versions/add_users_table.py`**
   - Убрал проверки существования таблицы
   - Вернул стандартные `op.create_table()` и `op.create_index()`

### Оставил repair-миграцию (исправлена):

5. **`alembic/versions/71fcc51a5119_repair_schema_idempotency.py`**
   - Repair-миграция после head (`670ed0736bfa`)
   - Использует безопасные проверки через `inspector` и `IF NOT EXISTS`
   - Исправляет schema drift без изменения истории миграций

## PowerShell команды для пользователя

```powershell
# 1. Диагностика: проверить текущее состояние БД
docker compose exec api alembic current
docker compose exec api alembic heads

# 2. Диагностика: проверить какие таблицы и колонки существуют
docker compose exec postgres psql -U wb -d wb -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
docker compose exec postgres psql -U wb -d wb -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'products' ORDER BY column_name;"
docker compose exec postgres psql -U wb -d wb -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'users' ORDER BY column_name;"
docker compose exec postgres psql -U wb -d wb -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'projects' ORDER BY column_name;"
docker compose exec postgres psql -U wb -d wb -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'project_marketplaces' ORDER BY column_name;"

# 3. Определить нужную ревизию для stamp (если current != head)
# Если есть таблицы users, projects, marketplaces, project_marketplaces - значит миграции применены частично
# Если current показывает старую ревизию (например, add_projects_tables), нужно stamp на более новую

# 4. Если current показывает старую ревизию, но таблицы уже созданы - stamp на нужную ревизию
# Определить нужную ревизию по наличию таблиц:
# - Если есть project_marketplaces.api_token_encrypted -> stamp на 670ed0736bfa (merge head)
# - Если есть project_marketplaces, но нет api_token_encrypted -> stamp на e373f63d276a (add_api_token_encrypted)
# - Если есть projects, но нет project_marketplaces -> stamp на add_marketplaces_tables
# - Если есть users, но нет projects -> stamp на add_projects_tables

# Пример: если current = add_projects_tables, но есть все таблицы включая api_token_encrypted
docker compose exec api alembic stamp 670ed0736bfa

# 5. Применить оставшиеся миграции (включая repair)
docker compose exec api alembic upgrade head

# 6. Проверить что current == head
docker compose exec api alembic current
docker compose exec api alembic heads
```

## Как проверить (3-5 проверок)

### 1. Проверить что current == head

```powershell
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:** Оба команды возвращают `71fcc51a5119` (или `670ed0736bfa` если repair еще не применена)

### 2. Проверить что миграции применяются без ошибок

```powershell
docker compose exec api alembic upgrade head
```

**Ожидается:** 
- Нет ошибок `DuplicateColumn`, `DuplicateIndex`, `DuplicateTable`
- Repair-миграция проверяет и добавляет недостающие элементы

### 3. Проверить что создается проект

```powershell
# Получить токен
$token = (docker compose exec api python -c "from app.db_users import create_user, get_user_by_username; from app.db import engine; from sqlalchemy import text; conn = engine.connect(); result = conn.execute(text('SELECT id FROM users LIMIT 1')); row = result.fetchone(); print(row[0] if row else 'no user')") | Out-String -NoNewline

# Создать проект через API (нужен реальный токен из /api/v1/auth/login)
# curl -X POST http://localhost/api/v1/projects -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d '{\"name\":\"Test Project\"}'
```

**Ожидается:** Проект создается, запись появляется в таблице `projects`

### 4. Проверить что подключается WB (создается project_marketplaces)

```powershell
docker compose exec postgres psql -U wb -d wb -c "SELECT id, project_id, marketplace_id, is_enabled, api_token_encrypted IS NOT NULL as has_token FROM project_marketplaces;"
```

**Ожидается:** Запись в `project_marketplaces` с `is_enabled=true` и `has_token=true`

### 5. Проверить что ingestion пишет данные с project_id и второй проект не видит данные первого

```powershell
# Проверить что products имеют project_id
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM products GROUP BY project_id;"

# Проверить что price_snapshots имеют project_id
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM price_snapshots GROUP BY project_id;"
```

**Ожидается:** 
- Все записи имеют `project_id` (не NULL)
- Данные разных проектов разделены по `project_id`


