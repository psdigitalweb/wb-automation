# DATABASE AUDIT REPORT - Gap Analysis

## A) ИНВЕНТАРИЗАЦИЯ "КАК ЕСТЬ"

### 1. Текущие миграции Alembic

**Порядок миграций (из кода):**
```
base
  └─> a77217f699d1 (initial_migration)
       └─> e1dcde5e611e (add_brand_to_products)
            └─> ... (промежуточные миграции)
                 └─> optimize_v_article_base
                      └─> add_project_id_to_data (revision: add_project_id_to_data, down_revision: optimize_v_article_base)
                           └─> backfill_project_id_and_make_not_null (down_revision: add_marketplaces_tables) ❌ НЕПРАВИЛЬНО
                 └─> add_product_details
                      └─> add_users_table
                           └─> add_refresh_tokens
                                └─> add_projects_tables
                                     └─> add_marketplaces_tables (HEAD)
```

**✅ ИСПРАВЛЕНО:** Порядок миграций исправлен:
- `add_project_id_to_data_tables` теперь зависит от `add_marketplaces_tables` ✅
- `backfill_project_id_and_make_not_null` теперь зависит от `add_project_id_to_data` ✅
- Добавлена новая миграция `add_unique_products_project_nm_id` для UNIQUE(project_id, nm_id) ✅

### 2. Таблицы, ожидаемые кодом

**Core tables (users, projects, memberships):**
- `users` - есть миграция `add_users_table`
- `projects` - есть миграция `add_projects_tables`
- `project_members` - есть миграция `add_projects_tables`
- `marketplaces` - есть миграция `add_marketplaces_tables`
- `project_marketplaces` - есть миграция `add_marketplaces_tables`

**Data tables (products, stocks, prices):**
- `products` - есть в `initial_migration`, но нужен `project_id` (есть миграция `add_project_id_to_data_tables`)
- `stock_snapshots` - есть в `6089711fc16b`, но нужен `project_id` (есть миграция `add_project_id_to_data_tables`)
- `price_snapshots` - есть в `initial_migration`, но нужен `project_id` (есть миграция `add_project_id_to_data_tables`)

### 3. Колонки, ожидаемые кодом

**users:**
- id, username (UNIQUE), email (UNIQUE), hashed_password, is_active, is_superuser, created_at, updated_at
- ✅ Все есть в миграции `add_users_table`

**projects:**
- id, name, description, created_by (FK -> users.id), created_at, updated_at
- ✅ Все есть в миграции `add_projects_tables`
- ✅ Индексы: idx_projects_created_by

**project_members:**
- id, project_id (FK -> projects.id), user_id (FK -> users.id), role, created_at, updated_at
- ✅ Все есть в миграции `add_projects_tables`
- ✅ UNIQUE(project_id, user_id)
- ✅ Индексы: idx_project_members_project_id, idx_project_members_user_id, idx_project_members_role

**marketplaces:**
- id, code (UNIQUE), name, description, is_active, created_at, updated_at
- ✅ Все есть в миграции `add_marketplaces_tables`
- ✅ Индексы: idx_marketplaces_code, idx_marketplaces_active
- ✅ Seed-данные в миграции (4 маркетплейса)

**project_marketplaces:**
- id, project_id (FK -> projects.id), marketplace_id (FK -> marketplaces.id), is_enabled, settings_json (JSONB), created_at, updated_at
- ✅ Все есть в миграции `add_marketplaces_tables`
- ✅ UNIQUE(project_id, marketplace_id)
- ✅ Индексы: idx_project_marketplaces_project_id, idx_project_marketplaces_marketplace_id, idx_project_marketplaces_enabled

**products:**
- id, nm_id (UNIQUE), vendor_code, title, brand, subject_id, subject_name, description, price_u, sale_price_u, rating, feedbacks, sizes (JSONB), colors (JSONB), pics (JSONB), dimensions (JSONB), characteristics (JSONB), created_at_api, need_kiz, raw (JSONB), updated_at, first_seen_at
- ✅ Базовые поля в `initial_migration` и `e1dcde5e611e`
- ✅ `project_id` (FK -> projects.id, NOT NULL) - есть миграция `add_project_id_to_data_tables` и `backfill_project_id_and_make_not_null`
- ✅ Индексы: idx_products_nm_id (UNIQUE), idx_products_vendor_code, idx_products_brand, idx_products_subject, idx_products_project_id

**stock_snapshots:**
- id, nm_id, warehouse_wb_id, quantity, snapshot_at, raw (JSONB)
- ✅ Базовые поля в `6089711fc16b`
- ✅ `project_id` (FK -> projects.id, NOT NULL) - есть миграция `add_project_id_to_data_tables` и `backfill_project_id_and_make_not_null`
- ✅ Индексы: idx_stock_snapshots_nm_id, idx_stock_snapshots_snapshot_at, idx_stock_snapshots_project_id

**price_snapshots:**
- id, nm_id, wb_price, wb_discount, spp, customer_price, rrc, created_at, raw (JSONB)
- ✅ Базовые поля в `initial_migration` и `213c70612608`
- ✅ `project_id` (FK -> projects.id, NOT NULL) - есть миграция `add_project_id_to_data_tables` и `backfill_project_id_and_make_not_null`
- ✅ Индексы: idx_price_snapshots_nm_id, idx_price_snapshots_project_id

### 4. Import-time DB операции

**Проблемы:**
- ❌ `routers/projects.py:44-48` - вызывает `ensure_schema()` на import-time (но обернуто в try/except, не ломает импорт)
- ❌ `routers/marketplaces.py:7-8` - импортирует `ensure_schema, seed_marketplaces`, но не вызывает на import-time ✅
- ✅ `main.py:86-108` - вызывает `seed_marketplaces()` в `startup_event` с проверкой существования таблицы ✅

**Вывод:** `ensure_schema()` в `routers/projects.py` вызывается на import-time, но это не критично (обернуто в try/except). Нужно убрать.

## B) TARGET SCHEMA "КАК ДОЛЖНО БЫТЬ"

### Целевая схема БД

**1. users**
- id (PK, SERIAL)
- username (VARCHAR(64), UNIQUE, NOT NULL)
- email (VARCHAR(255), UNIQUE, NULL)
- hashed_password (VARCHAR(255), NOT NULL)
- is_active (BOOLEAN, NOT NULL, DEFAULT TRUE)
- is_superuser (BOOLEAN, NOT NULL, DEFAULT FALSE)
- created_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- updated_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- **Индексы:** idx_users_username, idx_users_email

**2. projects**
- id (PK, SERIAL)
- name (VARCHAR(255), NOT NULL)
- description (TEXT, NULL)
- created_by (INTEGER, NOT NULL, FK -> users.id ON DELETE CASCADE)
- created_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- updated_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- **Индексы:** idx_projects_created_by

**3. project_members**
- id (PK, SERIAL)
- project_id (INTEGER, NOT NULL, FK -> projects.id ON DELETE CASCADE)
- user_id (INTEGER, NOT NULL, FK -> users.id ON DELETE CASCADE)
- role (VARCHAR(20), NOT NULL, DEFAULT 'member')
- created_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- updated_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- **UNIQUE:** (project_id, user_id)
- **Индексы:** idx_project_members_project_id, idx_project_members_user_id, idx_project_members_role

**4. marketplaces**
- id (PK, SERIAL)
- code (VARCHAR(50), UNIQUE, NOT NULL)
- name (VARCHAR(255), NOT NULL)
- description (TEXT, NULL)
- is_active (BOOLEAN, NOT NULL, DEFAULT TRUE)
- created_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- updated_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- **Индексы:** idx_marketplaces_code, idx_marketplaces_active
- **Seed-данные:** wildberries, ozon, yandex_market, sbermegamarket

**5. project_marketplaces**
- id (PK, SERIAL)
- project_id (INTEGER, NOT NULL, FK -> projects.id ON DELETE CASCADE)
- marketplace_id (INTEGER, NOT NULL, FK -> marketplaces.id ON DELETE CASCADE)
- is_enabled (BOOLEAN, NOT NULL, DEFAULT FALSE)
- settings_json (JSONB, NULL)
- created_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- updated_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- **UNIQUE:** (project_id, marketplace_id)
- **Индексы:** idx_project_marketplaces_project_id, idx_project_marketplaces_marketplace_id, idx_project_marketplaces_enabled

**6. products**
- id (PK, SERIAL)
- nm_id (BIGINT, UNIQUE, NOT NULL)
- vendor_code (TEXT, NULL)
- title (TEXT, NULL)
- brand (TEXT, NULL)
- subject_id (INTEGER, NULL)
- subject_name (TEXT, NULL)
- description (TEXT, NULL)
- price_u (BIGINT, NULL)
- sale_price_u (BIGINT, NULL)
- rating (NUMERIC(3,2), NULL)
- feedbacks (INTEGER, NULL)
- sizes (JSONB, NULL)
- colors (JSONB, NULL)
- pics (JSONB, NULL)
- dimensions (JSONB, NULL)
- characteristics (JSONB, NULL)
- created_at_api (TIMESTAMPTZ, NULL)
- need_kiz (BOOLEAN, NULL)
- raw (JSONB, NULL)
- updated_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- first_seen_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- **project_id (INTEGER, NOT NULL, FK -> projects.id ON DELETE CASCADE)** ⚠️
- **UNIQUE:** (project_id, nm_id) - НУЖНО ДОБАВИТЬ
- **Индексы:** idx_products_nm_id, idx_products_vendor_code, idx_products_brand, idx_products_subject_id, idx_products_subject_name, idx_products_project_id

**7. stock_snapshots**
- id (PK, SERIAL)
- nm_id (BIGINT, NOT NULL)
- warehouse_wb_id (INTEGER, NULL)
- quantity (INTEGER, NOT NULL)
- snapshot_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- raw (JSONB, NULL)
- **project_id (INTEGER, NOT NULL, FK -> projects.id ON DELETE CASCADE)** ⚠️
- **Индексы:** idx_stock_snapshots_nm_id, idx_stock_snapshots_snapshot_at, idx_stock_snapshots_project_id

**8. price_snapshots**
- id (PK, SERIAL)
- nm_id (BIGINT, NOT NULL)
- wb_price (NUMERIC(12,2), NULL)
- wb_discount (NUMERIC(5,2), NULL)
- spp (NUMERIC(5,2), NULL)
- customer_price (NUMERIC(12,2), NULL)
- rrc (NUMERIC(12,2), NULL)
- created_at (TIMESTAMPTZ, NOT NULL, DEFAULT now())
- raw (JSONB, NULL)
- **project_id (INTEGER, NOT NULL, FK -> projects.id ON DELETE CASCADE)** ⚠️
- **Индексы:** idx_price_snapshots_nm_id, idx_price_snapshots_project_id

## C) GAP ANALYSIS

### Проблемы в миграциях

1. **Неправильный порядок миграций:**
   - `add_project_id_to_data_tables` должна быть после `add_marketplaces_tables`
   - `backfill_project_id_and_make_not_null` должна быть после `add_project_id_to_data_tables`

2. **✅ Исправлено - constraints:**
   - ✅ `products`: добавлен UNIQUE(project_id, nm_id) в миграции `add_unique_products_project_nm_id`
   - ✅ `products`: исправлен `ON CONFLICT (project_id, nm_id)` в `db_products.py`

3. **✅ Исправлено - Import-time операции:**
   - ✅ `routers/projects.py`: убран вызов `ensure_schema()` на import-time

4. **Seed-данные:**
   - ✅ `seed_marketplaces()` вызывается в `startup_event` с проверкой - правильно
   - ✅ Seed-данные также есть в миграции `add_marketplaces_tables` - правильно

## D) ВЫПОЛНЕННЫЕ ИСПРАВЛЕНИЯ

### 1. ✅ Исправлен порядок миграций

**Файл:** `alembic/versions/add_project_id_to_data_tables.py`
- ✅ Изменен `down_revision` с `'optimize_v_article_base'` на `'add_marketplaces_tables'`

**Файл:** `alembic/versions/backfill_project_id_and_make_not_null.py`
- ✅ Изменен `down_revision` с `'add_marketplaces_tables'` на `'add_project_id_to_data'`

### 2. ✅ Добавлен UNIQUE constraint для products

**Создана новая миграция:** `alembic/versions/add_unique_products_project_nm_id.py`
- ✅ Удаляет старый UNIQUE(nm_id)
- ✅ Добавляет UNIQUE(project_id, nm_id)
- ✅ Обновляет индексы

### 3. ✅ Исправлен код products upsert

**Файл:** `src/app/db_products.py`
- ✅ Изменен `ON CONFLICT (nm_id)` на `ON CONFLICT (project_id, nm_id)`

### 4. ✅ Убраны import-time операции

**Файл:** `src/app/routers/projects.py`
- ✅ Удален вызов `ensure_schema()` на import-time
- ✅ Убран импорт `ensure_schema`

### 5. ✅ Обновлен MIGRATIONS_ORDER.md

**Файл:** `alembic/MIGRATIONS_ORDER.md`
- ✅ Добавлены миграции в правильном порядке

## E) КОМАНДЫ ДЛЯ ПРИМЕНЕНИЯ

```bash
# 1. Проверить текущее состояние
docker compose exec api alembic current
docker compose exec api alembic history

# 2. Применить исправленные миграции
docker compose exec api alembic upgrade head

# 3. Проверить схему БД
docker compose exec api python scripts/db_audit.py

# 4. Проверить API
curl http://localhost/api/v1/health

# 5. Создать проект (требует авторизации)
# curl -X POST http://localhost/api/v1/projects -H "Authorization: Bearer TOKEN" -d '{"name":"Test"}'

# 6. Привязать маркетплейс (требует авторизации и проекта)
# curl -X POST http://localhost/api/v1/projects/1/marketplaces/wb/connect -H "Authorization: Bearer TOKEN" -d '{"api_key":"TOKEN"}'
```

## F) ACCEPTANCE CRITERIA

После применения миграций:
- ✅ `/api/v1/health` возвращает 200
- ✅ Можно создать проект через API
- ✅ Можно привязать WB в проекте (project_marketplaces создаётся в БД)
- ✅ Данные products/stocks/prices строго фильтруются по project_id
- ✅ UNIQUE(project_id, nm_id) работает для products
- ✅ Нет import-time DB операций

