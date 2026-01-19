# DB Recovery: PowerShell Commands

## Диагностика текущего состояния

```powershell
# Запустить автоматическую диагностику
docker compose exec api python scripts/alembic_db_diagnose.py
```

Скрипт выведет текущее состояние и рекомендацию.

---

## Перед выполнением команд

**Важно:** Убедитесь что контейнеры запущены:
```powershell
docker compose up -d
Start-Sleep -Seconds 5
```

---

## Вариант 1: Сброс volume (РЕКОМЕНДУЕТСЯ для локальной БД)

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

**Ожидается:** Обе команды возвращают `71fcc51a5119` (repair migration - head)

---

## Вариант 2: Repair без сброса (если данные важны)

```powershell
# 1. Убедиться что контейнеры запущены
docker compose up -d
Start-Sleep -Seconds 5

# 2. Запустить диагностику для определения состояния
docker compose exec api python scripts/alembic_db_diagnose.py

# 2. Если диагностика показала "no alembic_version" и определила stamp_revision:
#    (например, если есть только users таблица -> stamp на add_users_table)

# 3. Stamp на определенную ревизию (замените на ревизию из диагностики)
docker compose exec api alembic stamp add_users_table

# 4. Применить все миграции (включая repair)
docker compose exec api alembic upgrade head

# 5. Проверить что current == head
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:** Обе команды возвращают `71fcc51a5119`

---

## Проверки после восстановления

### 1. Проверить что current == head

```powershell
$current = (docker compose exec api alembic current | Select-String -Pattern "[a-f0-9]{12}|71fcc51a5119|670ed0736bfa" | ForEach-Object { $_.Line.Trim() }).Split()[0]
$heads = (docker compose exec api alembic heads | Select-String -Pattern "[a-f0-9]{12}|71fcc51a5119|670ed0736bfa" | ForEach-Object { $_.Line.Trim() }).Split()[0]
Write-Host "Current: $current"
Write-Host "Heads: $heads"
if ($current -eq $heads) { Write-Host "✅ OK: current == head" } else { Write-Host "❌ FAIL: current != head" }
```

**Ожидается:** `✅ OK: current == head`

### 2. Проверить что POST /api/v1/auth/login работает

```powershell
# Проверить health endpoint
Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET

# Попробовать login (нужен существующий пользователь)
Invoke-WebRequest -Uri "http://localhost/api/v1/auth/login" -Method POST -ContentType "application/x-www-form-urlencoded" -Body "username=admin&password=password"
```

**Ожидается:** `200 OK` от health endpoint

### 3. Проверить что POST /api/v1/projects создаёт проект

```powershell
# Получить токен (замените на реальные credentials)
$loginBody = @{
    username = "admin"
    password = "password"
}
$loginResponse = Invoke-RestMethod -Uri "http://localhost/api/v1/auth/login" -Method POST -ContentType "application/x-www-form-urlencoded" -Body $loginBody
$token = $loginResponse.access_token

# Создать проект
$projectBody = @{
    name = "Test Project"
    description = "Test"
} | ConvertTo-Json
$headers = @{
    Authorization = "Bearer $token"
    "Content-Type" = "application/json"
}
Invoke-RestMethod -Uri "http://localhost/api/v1/projects" -Method POST -Headers $headers -Body $projectBody

# Проверить что проект создан
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name FROM projects;"
```

**Ожидается:** Проект создается, запись появляется в таблице `projects`

### 4. Проверить что POST /api/v1/projects/{id}/marketplaces/wb/connect создаёт запись

```powershell
# Получить project_id (из предыдущего шага, например 1)
$projectId = 1

# Подключить WB
$connectBody = @{
    api_key = "test_token"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost/api/v1/projects/$projectId/marketplaces/wb/connect" -Method POST -Headers $headers -Body $connectBody

# Проверить что запись создана
docker compose exec postgres psql -U wb -d wb -c "SELECT id, project_id, marketplace_id, is_enabled, api_token_encrypted IS NOT NULL as has_token FROM project_marketplaces;"
```

**Ожидается:** Запись в `project_marketplaces` с `is_enabled=true` и `has_token=true`

### 5. Проверить что ingestion пишет данные с project_id и данные изолированы

```powershell
# Проверить что products имеют project_id
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM products GROUP BY project_id;"

# Проверить что price_snapshots имеют project_id
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM price_snapshots GROUP BY project_id;"
```

**Ожидается:** Все записи имеют `project_id` (не NULL), данные разных проектов разделены

