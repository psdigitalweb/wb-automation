# Исправление персистентности проектов

## Проблема

Проекты не сохранялись после перезапуска контейнеров (`docker compose down`), потому что:

1. **Отсутствие volume для PostgreSQL** - данные хранились только в контейнере и терялись при его удалении
2. **Runtime schema creation** - `ensure_schema()` вызывался при каждом импорте модулей, что не является правильным подходом для production

## Исправления

### 1. Добавлен persistent volume для PostgreSQL

**Файл:** `docker-compose.yml`

Добавлен named volume `postgres_data` для хранения данных PostgreSQL:

```yaml
volumes:
  postgres_data:
    driver: local
```

И подключен к контейнеру postgres:

```yaml
postgres:
  volumes:
    - postgres_data:/var/lib/postgresql/data
```

**Почему данные терялись:**
- Без volume данные хранились в `/var/lib/postgresql/data` внутри контейнера
- При `docker compose down` контейнер удалялся вместе с данными
- После `docker compose up` создавался новый пустой контейнер

**Решение:**
- Named volume хранится на хосте в `/var/lib/docker/volumes/wb-automation_postgres_data`
- Данные сохраняются между перезапусками контейнеров
- Volume удаляется только явной командой `docker volume rm`

### 2. Отключен runtime schema creation

**Файлы:**
- `src/app/db_projects.py`
- `src/app/db_marketplaces.py`
- `src/app/routers/projects.py`

`ensure_schema()` теперь работает только в development режиме при установке переменной окружения:

```bash
ENABLE_RUNTIME_SCHEMA_CREATION=true
```

По умолчанию эта переменная не установлена, и schema создается только через Alembic миграции.

**Изменения:**
- Добавлена проверка `ENABLE_RUNTIME_SCHEMA_CREATION` в `ensure_schema()`
- Убран вызов `ensure_schema()` из `create_project()`
- Schema должна создаваться миграцией `add_projects_tables.py`

## Проверка персистентности

### Скрипты проверки

Созданы два скрипта для проверки:

1. **Linux/Mac:** `scripts/test_project_persistence.sh`
2. **Windows:** `scripts/test_project_persistence.ps1`

### Ручная проверка

```bash
# 1. Убедитесь, что контейнеры запущены
docker compose up -d

# 2. Примените миграции (если еще не применены)
docker compose exec api alembic upgrade head

# 3. Получите токен аутентификации (создайте пользователя если нужно)
# TODO: Добавить инструкцию по созданию пользователя и получению токена

# 4. Создайте первый проект
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project 1","description":"Test"}'

# 5. Создайте второй проект
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Project 2","description":"Test"}'

# 6. Проверьте проекты в БД
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name FROM projects;"

# 7. Остановите контейнеры
docker compose down

# 8. Запустите контейнеры снова
docker compose up -d

# 9. Дождитесь готовности (5-10 секунд)
sleep 5

# 10. Проверьте проекты через API
curl -X GET "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 11. Проверьте проекты в БД
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name FROM projects;"

# Оба проекта должны быть на месте!
```

### Автоматическая проверка (Linux/Mac)

```bash
export AUTH_TOKEN="Bearer YOUR_TOKEN_HERE"
chmod +x scripts/test_project_persistence.sh
./scripts/test_project_persistence.sh
```

### Автоматическая проверка (Windows PowerShell)

```powershell
$env:AUTH_TOKEN = "Bearer YOUR_TOKEN_HERE"
.\scripts\test_project_persistence.ps1
```

## Конфигурация БД

### DSN/URL подключения

**Источник:** `src/app/settings.py`

```python
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)
```

**Параметры из .env:**
- `POSTGRES_USER=wb`
- `POSTGRES_PASSWORD=wbpass` (указывается в .env)
- `POSTGRES_HOST=postgres` (имя сервиса в docker-compose)
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=wb`

### Расположение данных

**В Docker:**
- Контейнер: `/var/lib/postgresql/data`
- Named volume: `wb-automation_postgres_data`

**На хосте (Linux):**
```bash
docker volume inspect wb-automation_postgres_data
# Mountpoint: /var/lib/docker/volumes/wb-automation_postgres_data/_data
```

**На хосте (Windows/Mac Docker Desktop):**
```bash
docker volume inspect wb-automation_postgres_data
# Mountpoint в виртуальной машине Docker
```

## Миграции

Таблицы проектов создаются миграцией:

**Файл:** `alembic/versions/add_projects_tables.py`

**Применить миграции:**
```bash
docker compose exec api alembic upgrade head
```

**Проверить статус:**
```bash
docker compose exec api alembic current
docker compose exec api alembic history
```

## Важно

1. **Volume создается автоматически** при первом `docker compose up`
2. **Volume сохраняется** при `docker compose down` (контейнеры удаляются, volume остается)
3. **Volume удаляется** только явной командой `docker volume rm wb-automation_postgres_data` или `docker compose down -v`
4. **Для production** убедитесь, что `ENABLE_RUNTIME_SCHEMA_CREATION` не установлена
5. **Миграции должны применяться** перед запуском приложения в production

## Откат изменений

Если нужно откатить изменения:

```bash
# 1. Остановить контейнеры
docker compose down

# 2. Удалить volume (ОСТОРОЖНО: удалит все данные!)
docker volume rm wb-automation_postgres_data

# 3. Запустить снова (создаст новый пустой volume)
docker compose up -d
```


