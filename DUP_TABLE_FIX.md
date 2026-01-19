# Исправление ошибки DuplicateTable для users

## Проблема

**Ошибка:** `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.DuplicateTable) relation "users" already exists`

**Причина:** Таблица `users` уже существует в БД (создана ранее, возможно вручную или через `ensure_schema`), но миграция `add_users_table.py` пытается создать её снова.

**Контекст:** При применении миграций с нуля, если таблица `users` уже существует (например, создана через `ensure_schema` или предыдущими попытками миграций), миграция падает с ошибкой `DuplicateTable`.

## Исправление

Добавлена проверка существования таблицы `users` перед созданием в миграции:
- `alembic/versions/add_users_table.py`

**Изменение:** 
- Проверяется существование таблицы через `inspector.get_table_names()`
- Если таблица существует - пропускается создание
- Индексы создаются через `CREATE INDEX IF NOT EXISTS` с проверкой существования

## Проверка

```powershell
# 1. Применить миграции (должны пройти без ошибок DuplicateTable)
docker compose exec api alembic upgrade head

# 2. Проверить что миграции применены успешно
docker compose exec api alembic current

# 3. Проверить что health endpoint работает
Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET

# 4. Проверить что таблица users существует и имеет все колонки
docker compose exec postgres psql -U wb -d wb -c "\d users"

# 5. Проверить что индексы созданы
docker compose exec postgres psql -U wb -d wb -c "SELECT indexname FROM pg_indexes WHERE tablename = 'users';"
```

**Ожидается:**
- Миграции применяются без ошибок `DuplicateTable`
- Health endpoint возвращает `200 OK`
- Таблица `users` существует со всеми колонками и индексами


