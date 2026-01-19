# Фикс создания проекта: диагностика и исправление

## Проблема
Создание проекта на `/app/projects` перестало работать. UI показывает alert "Failed to create project" без деталей ошибки.

## Root Cause Analysis

### 1. Фронтенд: потеря деталей ошибки
**Файл:** `frontend/app/app/projects/page.tsx`
- **Проблема:** Обработка ошибки слишком простая: `alert(error.detail || 'Failed to create project')`
- **Причина:** Если `error.detail` отсутствует, теряется реальная ошибка из API
- **Исправление:** Добавлен вывод полного сообщения об ошибке из API с fallback на разные поля

### 2. Backend: отсутствие логирования ошибок
**Файл:** `src/app/db_projects.py`
- **Проблема:** `create_project()` не логирует ошибки, исключения не обрабатываются
- **Причина:** Ошибки БД (например, "relation does not exist" или "column does not exist") теряются без stacktrace
- **Исправление:** Добавлен try/except с логированием и stacktrace

### 3. Backend: ensure_schema() может скрывать ошибки
**Файл:** `src/app/routers/projects.py`
- **Проблема:** `ensure_schema()` вызывается на уровне модуля без обработки исключений
- **Причина:** Если `ensure_schema()` падает, ошибка может скрыть реальную проблему создания проекта
- **Исправление:** Обернут в try/except с логированием, ошибки не останавливают импорт модуля

### 4. Backend endpoint: нет обработки исключений
**Файл:** `src/app/routers/projects.py`
- **Проблема:** `create_project_endpoint()` не обрабатывает исключения из `create_project()`
- **Причина:** Ошибки БД возвращаются как 500 без деталей
- **Исправление:** Добавлен try/except с логированием и возвратом детализированного HTTPException

## Изменения

### Backend: `src/app/db_projects.py`
1. Добавлены импорты: `logging`, `traceback`
2. Создан `logger = logging.getLogger(__name__)`
3. `ensure_schema()`: обернут в try/except с логированием ошибок
4. `create_project()`:
   - Обернут в try/except с логированием
   - Проверка на `project_row is None` перед использованием
   - Логирование успешного создания с уровнем INFO
   - Логирование ошибок с уровнем ERROR и stacktrace

### Backend: `src/app/routers/projects.py`
1. Добавлены импорты: `logging`, `traceback`
2. Создан `logger = logging.getLogger(__name__)`
3. `ensure_schema()`: обернут в try/except при вызове на уровне модуля
4. `create_project_endpoint()`: добавлен try/except с логированием и HTTPException с детализированным сообщением

### Frontend: `frontend/app/app/projects/page.tsx`
1. `handleCreateProject()`: улучшена обработка ошибок
   - Добавлен `console.error` для отладки
   - Используется `error?.detail || error?.message || String(error)` для получения полного сообщения

## Проверка

### 1. Проверить логи контейнера API
```bash
docker compose logs api | grep -i "error\|create_project\|ensure_schema" | tail -50
```

### 2. Проверить состояние БД (таблица projects существует)
```bash
docker compose exec api python -c "
from app.db_projects import engine
from sqlalchemy import text
conn = engine.connect()
result = conn.execute(text(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'projects' ORDER BY ordinal_position\"))
for r in result:
    print(f'{r[0]}: {r[1]}')
conn.close()
"
```

### 3. Проверить миграции Alembic
```bash
docker compose exec api alembic current
docker compose exec api alembic history --verbose | head -30
```

### 4. Тест создания проекта (curl)
```bash
# Получить токен (предварительно залогиниться)
AUTH_TOKEN="Bearer YOUR_ACCESS_TOKEN"

# Создать проект
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Project",
    "description": "Test description"
  }'

# Ожидаемый ответ (200/201):
# {
#   "id": 1,
#   "name": "Test Project",
#   "description": "Test description",
#   "created_by": 1,
#   "created_at": "2024-...",
#   "updated_at": "2024-..."
# }
```

### 5. Тест через UI
1. Открыть `http://localhost:3000/app/projects`
2. Нажать "+ New Project"
3. Ввести название проекта
4. Нажать "Create"
5. **Если ошибка:** Проверить alert - должен показать детальное сообщение из API
6. **Если успех:** Проект должен появиться в списке и произойти переход на dashboard

## Ожидаемые результаты после фикса

1. **Логирование:** Все ошибки создания проекта логируются с stacktrace в контейнере API
2. **UI:** При ошибке отображается детальное сообщение из API (не просто "Failed to create project")
3. **Отладка:** Легко найти root cause через логи контейнера

## Возможные причины ошибки (проверить после фикса)

1. **Таблица `projects` не существует** - проверить миграции Alembic
2. **Таблица `project_members` не существует** - проверить миграции Alembic
3. **Foreign key violation** - пользователь `created_by` не существует в таблице `users`
4. **Проблемы с подключением к БД** - проверить `DATABASE_URL` и доступность Postgres

## Следующие шаги (если проблема сохраняется)

1. Проверить логи контейнера API: `docker compose logs api`
2. Проверить миграции: `docker compose exec api alembic upgrade head`
3. Проверить схему БД напрямую через `psql` или Python
4. Проверить переменные окружения: `docker compose exec api env | grep DATABASE`


