# Полноценная локальная разработка

## Архитектура

- **Backend (API)**: Docker контейнеры (postgres, redis, api, worker, beat)
- **Frontend**: Docker контейнер в dev режиме (Next.js dev server с hot reload)
- **Nginx**: Опционально, для production-like окружения

## Быстрый старт

### 1. Подготовка

```powershell
cd wb-automation

# Создайте .env файл
cp .env.example .env
# Отредактируйте .env, укажите POSTGRES_PASSWORD и WB_TOKEN (если есть)

# Создайте .htpasswd для Adminer (опционально)
# Используйте скрипт: scripts/create_htpasswd.sh
# Или создайте вручную через htpasswd
```

### 2. Запуск всех сервисов

```powershell
# Соберите и запустите все сервисы
docker compose up -d --build

# Примените миграции
docker compose exec api alembic upgrade head
```

### 3. Доступ к приложению

- **Frontend (Next.js dev)**: http://localhost:3000
- **API**: http://localhost:8000 (прямой доступ)
- **API через Nginx**: http://localhost/api
- **API Docs**: http://localhost:8000/docs или http://localhost/api/docs
- **Adminer**: http://localhost/adminer/

## Преимущества этого подхода

✅ **Frontend в dev режиме**:
- Hot reload при изменении кода
- Быстрый старт (без production сборки)
- Удобная отладка

✅ **Backend в Docker**:
- Изолированное окружение
- Легко перезапустить
- Все зависимости в контейнерах

✅ **Полная функциональность**:
- Все сервисы работают
- API доступен напрямую и через nginx
- Frontend подключается к API автоматически

## Работа с кодом

### Изменения в Frontend

1. Откройте `frontend/` в редакторе
2. Внесите изменения
3. Next.js автоматически перезагрузит страницу (hot reload)
4. Логи frontend: `docker compose logs -f frontend`

### Изменения в Backend

1. Откройте `src/app/` в редакторе
2. Внесите изменения
3. FastAPI автоматически перезагрузится (благодаря `--reload`)
4. Логи API: `docker compose logs -f api`

## Полезные команды

### Просмотр логов

```powershell
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f frontend
docker compose logs -f api
docker compose logs -f postgres
```

### Перезапуск сервисов

```powershell
# Перезапустить frontend
docker compose restart frontend

# Перезапустить API
docker compose restart api

# Перезапустить все
docker compose restart
```

### Остановка

```powershell
# Остановить все
docker compose down

# Остановить и удалить volumes (БД будет очищена!)
docker compose down -v
```

### Выполнение команд в контейнерах

```powershell
# Войти в контейнер frontend
docker compose exec frontend sh

# Выполнить команду в API контейнере
docker compose exec api alembic upgrade head
docker compose exec api python -c "from app.utils.vendor_code import normalize_vendor_code; print(normalize_vendor_code('560/ZKPY-1138'))"
```

## Решение проблем

### Frontend не запускается

```powershell
# Проверьте логи
docker compose logs frontend

# Пересоберите frontend
docker compose build frontend --no-cache
docker compose up -d frontend
```

### API не отвечает

```powershell
# Проверьте логи
docker compose logs api

# Проверьте подключение к БД
docker compose exec api python -c "from app.db import engine; engine.connect(); print('OK')"
```

### Проблемы с зависимостями frontend

Если `npm install` в контейнере зависает:

1. Удалите `node_modules` в контейнере:
```powershell
docker compose exec frontend rm -rf node_modules
docker compose restart frontend
```

2. Или пересоберите контейнер:
```powershell
docker compose build frontend --no-cache
docker compose up -d frontend
```

## Production сборка frontend (опционально)

Если нужно собрать production версию frontend:

```powershell
# Используйте production Dockerfile
docker compose -f docker-compose.yml -f docker-compose.prod.yml build frontend
```

Или создайте `docker-compose.prod.yml`:
```yaml
services:
  frontend:
    build:
      dockerfile: Dockerfile  # Production версия
```

## Структура проекта

```
wb-automation/
├── .env                    # Переменные окружения
├── docker-compose.yml      # Основная конфигурация
├── frontend/
│   ├── Dockerfile.dev      # Dev версия (используется по умолчанию)
│   ├── Dockerfile          # Production версия
│   └── ...
├── src/                    # Backend код
└── ...
```

## Следующие шаги

1. ✅ Запустите все сервисы: `docker compose up -d`
2. ✅ Примените миграции: `docker compose exec api alembic upgrade head`
3. ✅ Откройте http://localhost:3000
4. ✅ Начните разработку!






