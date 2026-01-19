# Быстрый старт

## Запуск проекта с нуля за 5 минут

### 1. Создайте `.env` файл

```bash
# Минимальная конфигурация
POSTGRES_PASSWORD=wbpass
WB_TOKEN=MOCK
JWT_SECRET=change-me-in-production
```

### 2. Запустите Docker контейнеры

```bash
docker compose up -d --build
```

### 3. Примените миграции

```bash
docker compose exec api alembic upgrade head
```

### 4. Откройте приложение

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Adminer**: http://localhost/adminer

### 5. Создайте первого пользователя

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "email": "admin@example.com", "password": "admin123"}'
```

### 6. Войдите и получите токен

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

Сохраните `access_token` из ответа.

### 7. Создайте проект

```bash
curl -X POST "http://localhost:8000/api/v1/projects" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Мой проект", "description": "Описание"}'
```

## Готово! 🎉

Теперь вы можете:
- Просматривать проекты на http://localhost:3000
- Подключать маркетплейсы к проектам
- Запускать ingestion данных

## Подробная документация

- **START_FROM_SCRATCH.md** - полная инструкция по запуску
- **alembic/MIGRATIONS_ORDER.md** - порядок миграций
- **AUTH_DOCUMENTATION.md** - система авторизации
- **PROJECTS_DOCUMENTATION.md** - мультипроектная модель
- **MARKETPLACES_DOCUMENTATION.md** - управление маркетплейсами




