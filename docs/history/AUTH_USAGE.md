# Система авторизации JWT

## Описание

Реализована система авторизации с использованием JWT токенов (access + refresh) в FastAPI.

## Компоненты

### 1. Модель User (`db_users.py`)
- Таблица `users` с полями: `id`, `username`, `email`, `hashed_password`, `is_active`, `is_superuser`, `created_at`, `updated_at`
- Функции для работы с пользователями: `get_user_by_username`, `get_user_by_id`, `create_user`

### 2. Схемы Pydantic (`schemas/auth.py`)
- `UserCreate` - для регистрации
- `UserResponse` - для ответов API
- `LoginRequest` - для входа
- `Token` - для токенов
- `RefreshTokenRequest` - для обновления токена

### 3. Security (`core/security.py`)
- Хеширование паролей: `get_password_hash`, `verify_password`
- Создание JWT токенов: `create_access_token`, `create_refresh_token`
- Декодирование токенов: `decode_token`

### 4. Dependencies (`deps.py`)
- `get_current_user` - получение текущего пользователя из токена
- `get_current_active_user` - получение активного пользователя
- `get_current_superuser` - получение суперпользователя

### 5. Auth Router (`routers/auth.py`)
- `POST /api/v1/auth/register` - регистрация нового пользователя
- `POST /api/v1/auth/login` - вход (получение access + refresh токенов)
- `POST /api/v1/auth/refresh` - обновление access токена
- `GET /api/v1/auth/me` - информация о текущем пользователе
- `POST /api/v1/auth/logout` - выход

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

### 2. Вход (получение токенов)

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

```python
from fastapi import APIRouter, Depends
from app.deps import get_current_active_user, get_current_superuser

router = APIRouter()

@router.get("/protected")
async def protected_endpoint(current_user: dict = Depends(get_current_active_user)):
    return {"message": "This is protected", "user": current_user["username"]}

@router.get("/admin")
async def admin_endpoint(current_user: dict = Depends(get_current_superuser)):
    return {"message": "Admin only", "user": current_user["username"]}
```

## Переменные окружения

Добавьте в `.env`:

```env
JWT_SECRET=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Миграция базы данных

Миграция `add_users_table` создает таблицу `users` автоматически при применении:

```bash
docker compose exec api alembic upgrade head
```

## Безопасность

- Пароли хешируются с использованием bcrypt
- Access токены истекают через 30 минут (настраивается)
- Refresh токены истекают через 7 дней (настраивается)
- Токены содержат тип (`access` или `refresh`) для предотвращения перепутывания

