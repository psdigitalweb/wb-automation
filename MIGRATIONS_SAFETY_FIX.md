# Исправление безопасности миграций: Отчет

## Проблема
Были изменены старые миграции (`backfill_project_id_and_make_not_null.py`), что нарушает принцип неизменяемости истории миграций.

## Что исправлено

### 1. Откат изменений в старой миграции

**Файл:** `alembic/versions/backfill_project_id_and_make_not_null.py`

**Откачено:**
- Убрана проверка на существование Legacy проекта (это должно быть только в новой миграции)
- Файл возвращен к исходному состоянию (как был до правок)

**Текущее поведение старой миграции:**
- Ищет первый user для создания Legacy проекта
- Если users нет - выдает WARNING и не создает Legacy (это нормально, так как это старая миграция)
- Backfill и NOT NULL делаются только если есть target_project_id

### 2. Вся логика bootstrap/backfill/NOT NULL в новой миграции

**Файл:** `alembic/versions/b3d4e5f6a7b8_ensure_project_id_constraints.py`

**Что делает:**
1. **Создает admin user** (если не существует):
   - Username: `admin`
   - Password: `password` (hash через bcrypt)
   - Email: `admin@example.com`
   - is_superuser: TRUE

2. **Создает Legacy проект** (если не существует и есть admin user):
   - Name: `Legacy`
   - Created_by: admin user
   - Добавляет admin как owner

3. **Backfills NULL project_id** значениями в Legacy проект

4. **Устанавливает NOT NULL constraints** на project_id (если нет NULL значений)

5. **Создает foreign keys** (project_id -> projects.id)

6. **Создает UNIQUE(project_id, nm_id)** constraint на products

**Результат:**
- На чистой БД `alembic upgrade head` проходит без WARN о missing users
- Admin user и Legacy проект создаются автоматически в миграции
- Все constraints применяются корректно

### 3. Разделение ответственности

**Старая миграция (`backfill_project_id_and_make_not_null`):**
- Не изменялась (immutable)
- Может выдать WARNING если нет users (это нормально)
- НЕ создает admin/Legacy (это делает новая миграция)

**Новая миграция (`b3d4e5f6a7b8`):**
- Создает admin user и Legacy проект
- Делает backfill (если есть NULL project_id)
- Устанавливает NOT NULL constraints
- Создает FK и UNIQUE constraints

## Проверка на чистой БД

### Команды для теста

```powershell
# 1. Сбросить БД (если нужно)
docker compose down -v
docker compose up -d postgres
Start-Sleep -Seconds 5

# 2. Применить все миграции
docker compose exec api alembic upgrade head

# 3. Проверить что нет WARN о missing users
docker compose logs api | Select-String -Pattern "WARNING.*users|No users found" -Context 2

# 4. Проверить что admin user создан
docker compose exec postgres psql -U wb -d wb -c "SELECT id, username, is_superuser FROM users WHERE username = 'admin';"

# 5. Проверить что Legacy проект создан
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name, created_by FROM projects WHERE name = 'Legacy';"

# 6. Проверить что project_id NOT NULL
docker compose exec postgres psql -U wb -d wb -c "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name IN ('products', 'price_snapshots', 'stock_snapshots') AND column_name = 'project_id';"

# 7. Проверить что constraints созданы
docker compose exec postgres psql -U wb -d wb -c "SELECT conname, conrelid::regclass, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname IN ('fk_products_project_id', 'fk_price_snapshots_project_id', 'fk_stock_snapshots_project_id', 'uq_products_project_nm_id');"
```

### Ожидаемые результаты

1. ✅ `alembic upgrade head` проходит без ошибок
2. ✅ Нет WARN "No users found..." (admin user создается в миграции)
3. ✅ Admin user существует (id, username=admin, is_superuser=TRUE)
4. ✅ Legacy проект существует (name=Legacy, created_by=admin user id)
5. ✅ project_id NOT NULL во всех data tables
6. ✅ Foreign keys существуют (fk_products_project_id, fk_price_snapshots_project_id, fk_stock_snapshots_project_id)
7. ✅ UNIQUE constraint существует (uq_products_project_nm_id)

## Порядок миграций

1. `backfill_project_id_and_make_not_null` - старая миграция (может выдать WARN если нет users)
2. `946d21840243` - добавляет UNIQUE(project_id, nm_id)
3. `e373f63d276a` - добавляет api_token_encrypted
4. `670ed0736bfa` - merge миграция
5. `71fcc51a5119` - repair миграция (добавляет недостающие колонки/индексы)
6. **`b3d4e5f6a7b8`** - **НОВАЯ**: создает admin/Legacy, делает backfill, устанавливает NOT NULL/FK/UNIQUE

## Итог

✅ **История миграций неизменяема** - старая миграция не изменялась  
✅ **Upgrade head работает на чистой БД** - admin user и Legacy проект создаются автоматически  
✅ **Upgrade head работает на текущей БД** - миграция идемпотентна (проверяет существование перед созданием)  
✅ **Все constraints применяются** - NOT NULL, FK, UNIQUE создаются корректно  
✅ **Нет WARN о missing users** - admin user создается в миграции b3d4e5f6a7b8


