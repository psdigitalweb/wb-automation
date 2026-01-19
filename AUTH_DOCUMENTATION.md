# Документация по системе авторизации

## Обзор

Система авторизации реализована с использованием JWT (JSON Web Tokens) с поддержкой access и refresh токенов.

## Компоненты системы

### 1. Модель User (`app/db_users.py`)
- Таблица `users` с полями:
  - `id` - уникальный идентификатор
  - `username` - уникальное имя пользователя
  - `email` - email (опционально, уникальный)
  - `hashed_password` - хешированный пароль (bcrypt)
  - `is_active` - активен ли пользователь
  - `is_superuser` - является ли суперпользователем
  - `created_at`, `updated_at` - временные метки

### 2. Security (`app/core/security.py`)
- `verify_password()` - проверка пароля
- `get_password_hash()` - хеширование пароля
- `create_access_token()` - создание access токена (30 минут по умолчанию)
- `create_refresh_token()` - создание refresh токена (7 дней по умолчанию)
- `decode_token()` - декодирование и проверка токена

### 3. Dependencies (`app/deps.py`)
- `get_current_user` - получение текущего пользователя из access токена
- `get_current_active_user` - получение активного пользователя
- `get_current_superuser` - получение суперпользователя

### 4. Auth Router (`app/routers/auth.py`)
- `POST /api/v1/auth/register` - регистрация нового пользователя
- `POST /api/v1/auth/login` - вход и получение токенов
- `POST /api/v1/auth/refresh` - обновление access токена
- `GET /api/v1/auth/me` - информация о текущем пользователе
- `POST /api/v1/auth/logout` - выход (клиент должен удалить токены)

## Использование

### 1. Регистрация пользователя

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "securepassword123"
  }'
```

### 2. Вход и получение токенов

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "securepassword123"
  }'
```

Ответ:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. Использование access токена

```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 4. Обновление access токена

```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "YOUR_REFRESH_TOKEN"
  }'
```

### 5. Защита эндпоинтов

#### Пример 1: Защищенный эндпоинт (требует аутентификации)

```python
from fastapi import APIRouter, Depends
from app.deps import get_current_active_user

router = APIRouter(prefix="/api/v1/my-endpoint", tags=["my"])

@router.get("/protected")
async def protected_endpoint(current_user: dict = Depends(get_current_active_user)):
    return {
        "message": "This endpoint requires authentication",
        "user_id": current_user["id"]
    }
```

#### Пример 2: Эндпоинт только для суперпользователей

```python
from fastapi import APIRouter, Depends
from app.deps import get_current_superuser

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

@router.get("/admin-only")
async def admin_endpoint(current_user: dict = Depends(get_current_superuser)):
    return {
        "message": "This endpoint requires superuser",
        "user_id": current_user["id"]
    }
```

#### Пример 3: Опциональная аутентификация

```python
from fastapi import APIRouter, Depends
from typing import Optional
from app.deps import get_current_user

router = APIRouter(prefix="/api/v1/public", tags=["public"])

@router.get("/optional-auth")
async def optional_auth_endpoint(
    current_user: Optional[dict] = Depends(get_current_user)
):
    if current_user:
        return {"message": f"Hello, {current_user['username']}!"}
    return {"message": "Hello, anonymous user!"}
```

## Настройка

### Переменные окружения

В `.env` файле можно настроить:

```env
# JWT Secret Key (обязательно изменить в продакшене!)
JWT_SECRET=your-secret-key-here

# Время жизни токенов (опционально)
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Примеры защищенных эндпоинтов

В проекте уже есть примеры:
- `GET /api/v1/protected/me` - защищенный эндпоинт
- `GET /api/v1/protected/admin` - эндпоинт только для суперпользователей

## Безопасность

1. **Пароли** хешируются с использованием bcrypt
2. **Access токены** имеют короткое время жизни (30 минут)
3. **Refresh токены** имеют длительное время жизни (7 дней)
4. **Токены** содержат тип (`type: "access"` или `type: "refresh"`)
5. **Проверка активности** пользователя перед выдачей токенов

## Миграции

Таблицы создаются автоматически через:
- `app/db_users.py` - `ensure_schema()` для users
- Alembic миграции для users и refresh_tokens

Применить миграции:
```bash
docker compose exec api alembic upgrade head
```




