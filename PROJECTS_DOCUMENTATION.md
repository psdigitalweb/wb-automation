# Документация по мультипроектной модели

## Обзор

Реализована мультипроектная модель с поддержкой ролей и проверкой membership для всех эндпоинтов.

## Компоненты системы

### 1. Модели

#### Project (`app/db_projects.py`)
- Таблица `projects` с полями:
  - `id` - уникальный идентификатор
  - `name` - название проекта (обязательно)
  - `description` - описание проекта (опционально)
  - `created_by` - ID пользователя-создателя
  - `created_at`, `updated_at` - временные метки

#### ProjectMember (`app/db_projects.py`)
- Таблица `project_members` с полями:
  - `id` - уникальный идентификатор
  - `project_id` - ID проекта
  - `user_id` - ID пользователя
  - `role` - роль пользователя в проекте
  - `created_at`, `updated_at` - временные метки
  - Уникальное ограничение на пару (project_id, user_id)

### 2. Роли

Роли определены в `app/db_projects.py`:

- **owner** - владелец проекта (полный доступ, может удалить проект)
- **admin** - администратор (может управлять участниками, обновлять проект)
- **member** - участник (может просматривать и работать с данными проекта)
- **viewer** - наблюдатель (только просмотр)

Иерархия прав:
- `owner` > `admin` > `member` > `viewer`

### 3. Dependencies для проверки membership (`app/deps.py`)

- `get_project_membership(project_id)` - проверяет, что пользователь является членом проекта
- `require_project_role(required_roles, project_id)` - требует одну из указанных ролей
- `require_project_owner(project_id)` - требует роль owner
- `require_project_admin(project_id)` - требует роль owner или admin
- `require_project_member(project_id)` - требует роль owner, admin или member (не viewer)

### 4. Эндпоинты (`app/routers/projects.py`)

Все эндпоинты требуют аутентификации и проверяют membership.

#### Проекты

- `POST /api/v1/projects` - создание проекта (создатель становится owner)
- `GET /api/v1/projects` - список проектов пользователя (с ролью)
- `GET /api/v1/projects/{project_id}` - детали проекта (требует membership)
- `PUT /api/v1/projects/{project_id}` - обновление проекта (требует admin/owner)
- `DELETE /api/v1/projects/{project_id}` - удаление проекта (требует owner)

#### Участники проекта

- `GET /api/v1/projects/{project_id}/members` - список участников (требует membership)
- `POST /api/v1/projects/{project_id}/members` - добавление участника (требует admin/owner)
- `PUT /api/v1/projects/{project_id}/members/{user_id}` - обновление роли (требует admin/owner)
- `DELETE /api/v1/projects/{project_id}/members/{user_id}` - удаление участника (требует admin/owner)

## Использование

### 1. Создание проекта

```bash
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Project",
    "description": "Project description"
  }'
```

Ответ:
```json
{
  "id": 1,
  "name": "My Project",
  "description": "Project description",
  "created_by": 1,
  "created_at": "2026-01-16T12:00:00Z",
  "updated_at": "2026-01-16T12:00:00Z"
}
```

### 2. Получение списка проектов пользователя

```bash
curl -X GET "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Ответ:
```json
[
  {
    "id": 1,
    "name": "My Project",
    "description": "Project description",
    "created_by": 1,
    "created_at": "2026-01-16T12:00:00Z",
    "updated_at": "2026-01-16T12:00:00Z",
    "role": "owner"
  }
]
```

### 3. Получение деталей проекта

```bash
curl -X GET "http://localhost:8000/api/v1/projects/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Ответ:
```json
{
  "id": 1,
  "name": "My Project",
  "description": "Project description",
  "created_by": 1,
  "created_at": "2026-01-16T12:00:00Z",
  "updated_at": "2026-01-16T12:00:00Z",
  "members": [
    {
      "id": 1,
      "project_id": 1,
      "user_id": 1,
      "role": "owner",
      "created_at": "2026-01-16T12:00:00Z",
      "updated_at": "2026-01-16T12:00:00Z",
      "username": "user1",
      "email": "user1@example.com"
    }
  ]
}
```

### 4. Добавление участника

```bash
curl -X POST "http://localhost:8000/api/v1/projects/1/members" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 2,
    "role": "member"
  }'
```

### 5. Обновление роли участника

```bash
curl -X PUT "http://localhost:8000/api/v1/projects/1/members/2" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "admin"
  }'
```

## Защита эндпоинтов

### Пример: Защищенный эндпоинт с проверкой membership

```python
from fastapi import APIRouter, Depends, Path
from app.deps import get_current_active_user, get_project_membership

router = APIRouter(prefix="/api/v1/my-endpoint", tags=["my"])

@router.get("/projects/{project_id}/data")
async def get_project_data(
    project_id: int = Path(...),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)  # Проверка membership
):
    # membership содержит информацию о роли пользователя в проекте
    return {
        "project_id": project_id,
        "user_role": membership["role"],
        "data": "some data"
    }
```

### Пример: Эндпоинт только для администраторов проекта

```python
from app.deps import require_project_admin

@router.delete("/projects/{project_id}/data")
async def delete_project_data(
    project_id: int = Path(...),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(require_project_admin)  # Только admin/owner
):
    # Только администраторы и владельцы могут удалять данные
    return {"message": "Data deleted"}
```

## Правила доступа

1. **Создание проекта**: любой аутентифицированный пользователь
2. **Просмотр проекта**: только участники проекта (любая роль)
3. **Обновление проекта**: только admin или owner
4. **Удаление проекта**: только owner
5. **Управление участниками**: только admin или owner
6. **Изменение роли owner**: только текущий owner
7. **Удаление owner**: невозможно (защита от удаления единственного owner)

## Миграции

Таблицы создаются через Alembic миграцию:
- `alembic/versions/add_projects_tables.py`

Применить миграции:
```bash
docker compose exec api alembic upgrade head
```

## Схемы Pydantic

Схемы определены в `app/schemas/projects.py`:
- `ProjectCreate` - для создания проекта
- `ProjectUpdate` - для обновления проекта
- `ProjectResponse` - базовая информация о проекте
- `ProjectWithRole` - проект с ролью пользователя
- `ProjectDetailResponse` - детальная информация с участниками
- `ProjectMemberCreate` - для добавления участника
- `ProjectMemberUpdate` - для обновления роли
- `ProjectMemberResponse` - информация об участнике




