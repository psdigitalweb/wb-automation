# DB Recovery: Quick Start

## Перед выполнением команд

**Важно:** Убедитесь что контейнеры запущены:

```powershell
# Проверить статус контейнеров
docker compose ps

# Если контейнеры не запущены - запустить
docker compose up -d

# Подождать несколько секунд для инициализации
Start-Sleep -Seconds 5
```

---

## Вариант 1: Сброс volume (РЕКОМЕНДУЕТСЯ для локальной БД)

```powershell
# 1. Остановить контейнеры
docker compose down

# 2. Удалить volume с БД (ОСТОРОЖНО - удалит все данные!)
docker volume rm wb-automation_postgres_data

# 3. Запустить контейнеры
docker compose up -d

# 4. Подождать 5 секунд для инициализации Postgres
Start-Sleep -Seconds 5

# 5. Применить все миграции
docker compose exec api alembic upgrade head

# 6. Проверить что current == head
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:** Обе команды возвращают `71fcc51a5119`

---

## Вариант 2: Repair без сброса (если данные важны)

```powershell
# 1. Убедиться что контейнеры запущены
docker compose up -d
Start-Sleep -Seconds 5

# 2. Запустить диагностику
docker compose exec api python scripts/alembic_db_diagnose.py

# 3. Stamp на определенную ревизию (из диагностики)
docker compose exec api alembic stamp add_users_table

# 4. Применить все миграции (включая repair)
docker compose exec api alembic upgrade head

# 5. Проверить что current == head
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:** Обе команды возвращают `71fcc51a5119`

---

## Устранение ошибки "service is not running"

Если видите ошибку `service "api" is not running`:

```powershell
# 1. Проверить статус
docker compose ps

# 2. Запустить все сервисы
docker compose up -d

# 3. Подождать запуска (особенно postgres)
Start-Sleep -Seconds 5

# 4. Проверить что api запущен
docker compose ps api

# 5. Теперь можно выполнять команды alembic
docker compose exec api alembic upgrade head
```

---

## Быстрая проверка после восстановления

```powershell
# 1. Проверить current == head
docker compose exec api alembic current
docker compose exec api alembic heads

# 2. Проверить health endpoint
Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET

# 3. Проверить что таблицы созданы
docker compose exec postgres psql -U wb -d wb -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
```


