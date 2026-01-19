# Инструкция по запуску Docker контейнеров

## Расположение docker-compose.yml

**Точный путь:** `wb-automation\docker-compose.yml`

От корня репозитория `C:\Users\pavel\OneDrive\wb-automation`:
- Полный путь: `C:\Users\pavel\OneDrive\wb-automation\wb-automation\docker-compose.yml`
- Относительный путь: `wb-automation\docker-compose.yml`

## Пошаговые команды PowerShell

### Вариант 1: Автоматический скрипт

```powershell
# Из каталога C:\Users\pavel\OneDrive\wb-automation
.\START_DOCKER.ps1
```

### Вариант 2: Ручные команды

```powershell
# 1. Перейти в каталог с docker-compose.yml
cd wb-automation

# 2. Проверить текущий статус контейнеров
docker compose ps

# 3. Запустить контейнеры (с пересборкой при необходимости)
docker compose up -d --build

# 4. Дождаться запуска (10-15 секунд)
Start-Sleep -Seconds 10

# 5. Проверить статус контейнеров (должны быть Up)
docker compose ps
```

## Проверка доступности API

### 1. Health endpoint

```powershell
# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -Method GET -UseBasicParsing

# Ожидаемый ответ: {"status": "ok"}
# HTTP Status: 200
```

**Или через curl (если установлен):**
```bash
curl http://localhost:8000/api/v1/health
```

### 2. API Documentation

```powershell
# PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/docs" -Method GET -UseBasicParsing

# Ожидаемый ответ: HTML страница Swagger UI
# HTTP Status: 200
```

**Или через curl:**
```bash
curl http://localhost:8000/docs
```

**Или просто открыть в браузере:**
```
http://localhost:8000/docs
```

## Если API не поднимается или сразу падает

### 1. Проверить логи API контейнера

```powershell
# Последние 200 строк логов
docker compose logs -n 200 api

# Логи в реальном времени
docker compose logs -f api
```

### 2. Типичные ошибки и решения

#### Ошибка: "relation does not exist" или "table 'projects' does not exist"

**Причина:** Миграции Alembic не применены

**Решение:**
```powershell
# Применить миграции
docker compose exec api alembic upgrade head

# Проверить текущую версию миграций
docker compose exec api alembic current
```

#### Ошибка: "could not connect to server" (PostgreSQL)

**Причина:** Postgres контейнер не запущен или еще стартует

**Решение:**
```powershell
# Проверить статус Postgres
docker compose ps postgres

# Проверить логи Postgres
docker compose logs -n 50 postgres

# Перезапустить Postgres
docker compose restart postgres

# Подождать и проверить снова
Start-Sleep -Seconds 5
docker compose logs -n 20 postgres
```

#### Ошибка: "port 8000 is already allocated"

**Причина:** Порт 8000 занят другим процессом

**Решение:**
```powershell
# Найти процесс на порту 8000
netstat -ano | findstr :8000

# Остановить контейнеры
docker compose down

# Изменить порт в docker-compose.yml (если нужно)
# Или остановить процесс, занимающий порт
```

#### Ошибка: "DATABASE_URL is not set" или "env file not found"

**Причина:** Отсутствует файл `.env` с переменными окружения

**Решение:**
```powershell
# Проверить наличие .env файла
Test-Path .env

# Если файла нет - создать из примера (если есть)
# Скопировать переменные из docker-compose.yml или другого места
# Обязательные переменные:
# DATABASE_URL=postgresql://wb:${POSTGRES_PASSWORD}@postgres:5432/wb
# POSTGRES_PASSWORD=your_password_here
# SECRET_KEY=your_secret_key_here
```

#### Ошибка: "ModuleNotFoundError" или "ImportError"

**Причина:** Зависимости Python не установлены или проблемы с PYTHONPATH

**Решение:**
```powershell
# Пересобрать образ API
docker compose build --no-cache api

# Перезапустить API
docker compose up -d api

# Проверить логи
docker compose logs -n 50 api
```

#### Ошибка: "uvicorn: command not found"

**Причина:** Зависимости не установлены в Docker образе

**Решение:**
```powershell
# Проверить Dockerfile и requirements.txt
# Пересобрать образ
docker compose build --no-cache api

# Запустить заново
docker compose up -d api
```

## Проверка конфигурации Frontend API

### Текущая конфигурация

Frontend использует `http://localhost:8000/api` для запросов к API.

**Файл:** `frontend/lib/api.ts`

```typescript
export function getApiBase(): string {
  // In browser, uses localhost:8000 (direct API access)
  if (typeof window !== 'undefined') {
    return 'http://localhost:8000/api'
  }
  // ...
}
```

**Это правильная конфигурация для:**
- ✅ Локальной разработки (Next.js на `localhost:3000`, API на `localhost:8000`)
- ✅ Docker окружения (порты проброшены на хост)

**Проверка:**
1. Frontend работает на `localhost:3000` ✅
2. API должен работать на `localhost:8000` (нужно проверить после запуска контейнеров)
3. Frontend обращается к `http://localhost:8000/api` ✅

## Полная последовательность проверки

```powershell
# 1. Перейти в правильный каталог
cd wb-automation

# 2. Запустить контейнеры
docker compose up -d --build

# 3. Подождать запуск (15-20 секунд)
Start-Sleep -Seconds 15

# 4. Проверить статус
docker compose ps
# Все сервисы должны быть "Up" (не "Restarting" или "Exited")

# 5. Проверить логи API (должны быть без ошибок)
docker compose logs -n 30 api

# 6. Проверить health endpoint
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -UseBasicParsing

# 7. Проверить docs (открыть в браузере)
Start-Process "http://localhost:8000/docs"

# 8. Если все OK - API готов к работе!
```

## Полезные команды

```powershell
# Остановить все контейнеры
docker compose down

# Остановить и удалить volumes (⚠️ удалит данные БД!)
docker compose down -v

# Перезапустить конкретный сервис
docker compose restart api

# Пересобрать и перезапустить
docker compose up -d --build api

# Посмотреть все логи
docker compose logs

# Посмотреть логи конкретного сервиса
docker compose logs -f api

# Войти в контейнер API
docker compose exec api bash

# Войти в контейнер Postgres
docker compose exec postgres psql -U wb -d wb
```

## Следующие шаги после успешного запуска

1. ✅ Проверить `http://localhost:8000/docs` - должна открыться Swagger UI
2. ✅ Проверить `http://localhost:8000/api/v1/health` - должен вернуть `{"status": "ok"}`
3. ✅ Проверить, что Frontend может делать запросы к API (в браузере открыть DevTools → Network)
4. ✅ Если проблемы с созданием проекта - проверить логи: `docker compose logs -n 100 api`


