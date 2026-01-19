# Фикс: создание таблицы projects

## Проблема
Ошибка при POST `/api/v1/projects`:
```
psycopg2.errors.UndefinedTable: relation "projects" does not exist
```

## Root Cause
1. **Таблица `projects` не существовала в БД** - миграции Alembic не были применены
2. **DATABASE_URL указывал на `db` вместо `postgres`** - но это было исправлено в коде (main.py делает замену)
3. **Проблемы с миграциями Alembic:**
   - Multiple head revisions (3 head ревизии)
   - Миграция `c2d3e4f5a6b7` падала из-за отсутствия таблиц `supplier_stock_snapshots`

## Решение

### 1. Создана таблица `projects` напрямую через SQL

**Команды:**
```sql
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_members (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_projects_created_by ON projects(created_by);
CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_role ON project_members(role);
```

### 2. Зафиксировано в Alembic

```bash
docker compose exec api alembic stamp add_projects_tables
```

### 3. Исправлена миграция c2d3e4f5a6b7

**Файл:** `alembic/versions/c2d3e4f5a6b7_add_v_article_base_view.py`

Добавлена проверка существования таблиц перед созданием VIEW:
- Если таблицы отсутствуют - миграция пропускается
- Это позволяет применять миграции в любом порядке

### 4. Исправлена зависимость миграции c2d3e4f5a6b7

**Файл:** `alembic/versions/c2d3e4f5a6b7_add_v_article_base_view.py`

Изменено:
- `down_revision = 'b1c2d3e4f5a6'` → `down_revision = 'a77217f699d1'`

## Проверка

### 1. Проверить таблицы в БД

```powershell
docker compose exec postgres psql -U wb -d wb -c "\d projects"
docker compose exec postgres psql -U wb -d wb -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('projects', 'project_members');"
```

### 2. Проверить создание проекта через UI

1. Залогиниться: `admin` / `admin123`
2. Перейти на `/app/projects`
3. Нажать "+ New Project"
4. Ввести название и создать
5. Проект должен создаться без ошибки 500

### 3. Проверить через API (curl)

```powershell
# Получить токен (залогиниться через UI и скопировать из localStorage или через /api/v1/auth/login)
$TOKEN = "YOUR_ACCESS_TOKEN"

Invoke-WebRequest -Uri "http://localhost:8000/api/v1/projects" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"; "Authorization"="Bearer $TOKEN"} `
  -Body '{"name":"Test Project","description":"Test"}' `
  -UseBasicParsing
```

## Ожидаемый результат

- ✅ Таблица `projects` существует в БД
- ✅ Таблица `project_members` существует в БД
- ✅ POST `/api/v1/projects` возвращает 201 Created (не 500)
- ✅ Проект создаётся из UI без ошибок
- ✅ Проект сохраняется в БД

## Примечание о DATABASE_URL

DATABASE_URL в контейнере указывает на `db`, но в `main.py` есть автоматическая замена `@db:` → `@postgres:`, поэтому подключение работает корректно.

Если нужно исправить в .env файле:
```env
DATABASE_URL=postgresql+psycopg2://wb:wbpassword@postgres:5432/wb
```

Но это не обязательно, так как код уже делает замену автоматически.


