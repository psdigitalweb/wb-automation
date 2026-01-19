# DB Schema Recovery Guide

## Диагностика состояния БД

Запустите автоматическую диагностику:

```powershell
docker compose exec api python scripts/alembic_db_diagnose.py
```

Скрипт выведет:
- Текущую версию Alembic (`alembic current`)
- Heads (`alembic heads`)
- Список таблиц в БД
- Наличие ключевых колонок (project_id, api_token_encrypted)
- Рекомендацию по восстановлению

## Варианты восстановления

### Вариант 1: Сброс volume (РЕКОМЕНДУЕТСЯ для локальной БД)

Если локальная БД не содержит важных данных, самый простой способ - сбросить volume:

```powershell
# Остановить контейнеры
docker compose down

# Удалить volume с БД (ОСТОРОЖНО - удалит все данные!)
docker volume rm wb-automation_postgres_data

# Запустить контейнеры заново
docker compose up -d postgres

# Подождать 5 секунд для инициализации Postgres
Start-Sleep -Seconds 5

# Применить все миграции
docker compose exec api alembic upgrade head

# Проверить что current == head
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:** Обе команды возвращают одинаковый revision ID (например, `71fcc51a5119`)

### Вариант 2: Repair без сброса (если данные важны)

Если нужно сохранить данные, но БД в состоянии drift:

```powershell
# 1. Запустить диагностику
docker compose exec api python scripts/alembic_db_diagnose.py

# 2. Если диагностика показала "Schema drift" или "no alembic_version":
#    - Если нет alembic_version таблицы, создать её и установить начальную версию
#    - Определить правильную версию по наличию таблиц

# 3. Если есть только users таблица - stamp на add_users_table
#    Если есть projects, но нет project_marketplaces - stamp на add_projects_tables
#    Если есть все таблицы - stamp на 670ed0736bfa (merge head)

# Пример: если есть users, но нет alembic_version
docker compose exec api alembic stamp add_users_table

# Затем применить все миграции (включая repair)
docker compose exec api alembic upgrade head

# Проверить
docker compose exec api alembic current
docker compose exec api alembic heads
```

## Проверки после восстановления

### 1. Проверить что current == head

```powershell
$current = docker compose exec api alembic current | Select-String -Pattern "^\s*[a-f0-9]{12}" | ForEach-Object { $_.Matches.Value }
$heads = docker compose exec api alembic heads | Select-String -Pattern "^\s*[a-f0-9]{12}" | ForEach-Object { $_.Matches.Value }
if ($current -eq $heads) { Write-Host "✅ OK: current == head" } else { Write-Host "❌ FAIL: current != head" }
```

**Ожидается:** `✅ OK: current == head`

### 2. Проверить что POST /api/v1/auth/login работает

```powershell
# Проверить health endpoint
curl http://localhost/api/v1/health

# Попробовать login (нужен существующий пользователь)
curl -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin&password=password"
```

**Ожидается:** `200 OK` от health endpoint, login возвращает токен или 401 (если пользователь не существует)

### 3. Проверить что POST /api/v1/projects создаёт проект

```powershell
# Сначала получить токен (замените на реальные credentials)
$response = curl -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin&password=password"
$token = ($response | ConvertFrom-Json).access_token

# Создать проект
curl -X POST http://localhost/api/v1/projects -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d '{"name":"Test Project","description":"Test"}'

# Проверить что проект создан
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name FROM projects;"
```

**Ожидается:** Проект создается, запись появляется в таблице `projects`

### 4. Проверить что POST /api/v1/projects/{id}/marketplaces/wb/connect создаёт запись

```powershell
# Получить project_id (из предыдущего шага или БД)
$projectId = 1

# Подключить WB
curl -X POST "http://localhost/api/v1/projects/$projectId/marketplaces/wb/connect" -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d '{"api_key":"test_token"}'

# Проверить что запись создана в project_marketplaces
docker compose exec postgres psql -U wb -d wb -c "SELECT id, project_id, marketplace_id, is_enabled, api_token_encrypted IS NOT NULL as has_token FROM project_marketplaces;"
```

**Ожидается:** Запись в `project_marketplaces` с `is_enabled=true` и `has_token=true`

### 5. Проверить что ingestion пишет данные с project_id и данные изолированы

```powershell
# Проверить что products имеют project_id
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM products GROUP BY project_id;"

# Проверить что price_snapshots имеют project_id  
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM price_snapshots GROUP BY project_id;"

# Проверить что второй проект не видит данные первого
# (нужно создать второй проект и проверить что запросы возвращают только свои данные)
```

**Ожидается:** 
- Все записи имеют `project_id` (не NULL)
- Данные разных проектов разделены по `project_id`
- Запросы по project_id возвращают только данные этого проекта


