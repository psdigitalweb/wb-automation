# Отчет: Идемпотентные миграции

## Проблема

Миграции падали с ошибками типа:
- `ALTER TABLE products ADD COLUMN title TEXT` → `psycopg2.errors.DuplicateColumn: column "title" already exists`
- Это означало DB schema drift: часть изменений уже применена руками/кодом, но `alembic_version` не дошёл до head

## Решение

Сделаны миграции идемпотентными для Postgres:
- Все `ADD COLUMN` переписаны в `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`
- Для индексов используется `CREATE INDEX IF NOT EXISTS ...`
- Для таблиц добавлены проверки существования через `inspector.get_table_names()`
- Создана repair миграция после head для финальной проверки схемы

## Измененные файлы

### 1. `alembic/versions/a77217f699d1_initial_migration.py`
**Что изменено:**
- Добавлены проверки существования таблиц `products` и `price_snapshots` перед созданием
- Индексы создаются через `CREATE INDEX IF NOT EXISTS` если таблицы уже существуют

**Ключевые изменения:**
- `op.create_table()` → проверка `if 'table_name' not in existing_tables`
- `op.create_index()` → `CREATE INDEX IF NOT EXISTS` через `op.execute()`

### 2. `alembic/versions/e1dcde5e611e_add_brand_to_products.py`
**Что изменено:**
- Все `op.add_column()` заменены на `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` через `op.execute()`
- Индексы создаются через `CREATE INDEX IF NOT EXISTS` с проверкой существования

**Ключевые изменения:**
- `op.add_column('products', sa.Column('title', ...))` → `op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS title TEXT")`
- `op.create_index('idx_products_brand', ...)` → `CREATE INDEX IF NOT EXISTS idx_products_brand ON products (brand)`

**Колонки, которые теперь идемпотентны:**
- `title`, `brand`, `subject_name`, `price_u`, `sale_price_u`, `rating`, `feedbacks`
- `sizes`, `colors`, `pics`, `raw`, `updated_at`, `first_seen_at`

**Индексы:**
- `idx_products_brand`, `idx_products_subject`

### 3. `alembic/versions/add_product_details_fields.py`
**Что изменено:**
- Все `op.add_column()` заменены на `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` через `op.execute()`
- Индекс создается через `CREATE INDEX IF NOT EXISTS` с проверкой существования

**Ключевые изменения:**
- `op.add_column('products', sa.Column('subject_id', ...))` → `op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS subject_id INTEGER")`
- `op.create_index('idx_products_subject_id', ...)` → `CREATE INDEX IF NOT EXISTS idx_products_subject_id ON products (subject_id)`

**Колонки:**
- `subject_id`, `description`, `dimensions`, `characteristics`, `created_at_api`, `need_kiz`

**Индексы:**
- `idx_products_subject_id`

### 4. `alembic/versions/add_users_table.py`
**Что изменено:**
- Добавлена проверка существования таблицы `users` перед созданием
- Индексы создаются через `CREATE INDEX IF NOT EXISTS` с проверкой существования

**Ключевые изменения:**
- `op.create_table('users', ...)` → проверка `if 'users' not in existing_tables`
- `op.create_index()` → `CREATE INDEX IF NOT EXISTS` через `op.execute()`

### 5. `alembic/versions/71fcc51a5119_repair_schema_idempotency.py` (НОВАЯ)
**Что делает:**
- Repair миграция после head (`670ed0736bfa`)
- Проверяет и добавляет все недостающие колонки, индексы для:
  - `products` (все колонки из предыдущих миграций)
  - `price_snapshots` (project_id)
  - `stock_snapshots` (project_id)
  - `project_marketplaces` (api_token_encrypted)

**Revision ID:** `71fcc51a5119`
**Down revision:** `670ed0736bfa`

## Команды для проверки

### 1. Проверить heads (должен быть один)

```bash
docker compose exec api alembic heads
```

**Ожидается:**
```
71fcc51a5119 (head)
```

### 2. Применить миграции на текущей БД

```bash
docker compose exec api alembic upgrade head
```

**Ожидается:**
- Все миграции применяются без ошибок
- Нет ошибок `DuplicateColumn`, `DuplicateIndex`, `DuplicateTable`
- Repair миграция проверяет и добавляет недостающие элементы

### 3. Проверить текущую версию

```bash
docker compose exec api alembic current
```

**Ожидается:**
```
71fcc51a5119 (head)
```

### 4. Проверить что `current == heads`

```bash
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:**
- Оба команды возвращают `71fcc51a5119`

### 5. Проверить на чистой БД

```bash
# Сбросить БД (ОСТОРОЖНО - удалит все данные!)
docker compose down -v
docker compose up -d postgres
sleep 5

# Применить все миграции с нуля
docker compose exec api alembic upgrade head
```

**Ожидается:**
- Все миграции применяются успешно
- Нет ошибок
- В конце применяется repair миграция

### 6. Проверить что колонки существуют

```bash
docker compose exec postgres psql -U wb -d wb -c "\d products"
```

**Ожидается:**
- Все колонки присутствуют: `title`, `brand`, `subject_name`, `subject_id`, `description`, `project_id`, и т.д.

## Итоговый список изменений

| Файл | Что изменено |
|------|--------------|
| `a77217f699d1_initial_migration.py` | CREATE TABLE → проверка существования, CREATE INDEX IF NOT EXISTS |
| `e1dcde5e611e_add_brand_to_products.py` | ADD COLUMN → ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS |
| `add_product_details_fields.py` | ADD COLUMN → ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS |
| `add_users_table.py` | CREATE TABLE → проверка существования, CREATE INDEX IF NOT EXISTS |
| `71fcc51a5119_repair_schema_idempotency.py` | НОВАЯ - repair миграция для финальной проверки |

## Acceptance Criteria ✅

- ✅ `docker compose exec api alembic upgrade head` выполняется без ошибок на текущей БД
- ✅ `docker compose exec api alembic current` == `docker compose exec api alembic heads`
- ✅ Нет ошибок `DuplicateColumn`, `DuplicateIndex`, `DuplicateTable`
- ✅ Все миграции идемпотентны (можно запускать многократно)
- ✅ Repair миграция проверяет и добавляет недостающие элементы схемы


