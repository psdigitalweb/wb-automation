# DB Recovery: Итоговый отчет

## Что найдено диагностикой

Диагностика показала:
- **Alembic current:** нет (таблица `alembic_version` не существует)
- **Alembic heads:** `71fcc51a5119` (repair migration)
- **Таблицы в БД:** только `users` (8 колонок)
- **Отсутствуют:** `projects`, `project_members`, `marketplaces`, `project_marketplaces`, `products`, `stock_snapshots`, `price_snapshots`
- **Рекомендация:** Stamp на `add_users_table`, затем `alembic upgrade head`

## Что изменено

### 1. Создан скрипт диагностики
- **Файл:** `scripts/alembic_db_diagnose.py`
- **Функции:**
  - Проверяет `alembic current` vs `alembic heads`
  - Выводит список таблиц и ключевые колонки
  - Проверяет наличие критичных полей (`project_id`, `api_token_encrypted`, UNIQUE constraints)
  - Автоматически определяет нужную ревизию для stamp на основе схемы
  - Выдает рекомендацию с командами

### 2. Repair миграция
- **Файл:** `alembic/versions/71fcc51a5119_repair_schema_idempotency.py`
- **Down revision:** `670ed0736bfa` (merge head)
- **Функции:**
  - Добавляет недостающие колонки через `ADD COLUMN IF NOT EXISTS`
  - Создает индексы через `CREATE INDEX IF NOT EXISTS`
  - Идемпотентная - безопасна для запуска на чистой БД

### 3. Старые миграции не изменены
- Все старые миграции остались в исходном виде (immutable)
- Используют стандартные `op.add_column()`, `op.create_table()`, `op.create_index()`

## PowerShell команды для восстановления

### Вариант 1: Сброс volume (РЕКОМЕНДУЕТСЯ для локальной БД)

```powershell
docker compose down
docker volume rm wb-automation_postgres_data
docker compose up -d postgres
Start-Sleep -Seconds 5
docker compose exec api alembic upgrade head
docker compose exec api alembic current
docker compose exec api alembic heads
```

### Вариант 2: Repair без сброса (если данные важны)

```powershell
docker compose exec api python scripts/alembic_db_diagnose.py
docker compose exec api alembic stamp add_users_table
docker compose exec api alembic upgrade head
docker compose exec api alembic current
docker compose exec api alembic heads
```

## Проверки после восстановления

### 1. Проверить что current == head
```powershell
$current = (docker compose exec api alembic current | Select-String -Pattern "[a-f0-9]{12}|71fcc51a5119" | ForEach-Object { $_.Line.Trim() }).Split()[0]
$heads = (docker compose exec api alembic heads | Select-String -Pattern "[a-f0-9]{12}|71fcc51a5119" | ForEach-Object { $_.Line.Trim() }).Split()[0]
if ($current -eq $heads) { Write-Host "✅ OK" } else { Write-Host "❌ FAIL" }
```

### 2. Проверить что POST /api/v1/auth/login работает
```powershell
Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET
```

### 3. Проверить что POST /api/v1/projects создаёт проект
```powershell
$loginResponse = Invoke-RestMethod -Uri "http://localhost/api/v1/auth/login" -Method POST -ContentType "application/x-www-form-urlencoded" -Body "username=admin&password=password"
$token = $loginResponse.access_token
$headers = @{Authorization = "Bearer $token"; "Content-Type" = "application/json"}
Invoke-RestMethod -Uri "http://localhost/api/v1/projects" -Method POST -Headers $headers -Body '{"name":"Test Project"}' | ConvertTo-Json
```

### 4. Проверить что POST /api/v1/projects/{id}/marketplaces/wb/connect создаёт запись
```powershell
Invoke-RestMethod -Uri "http://localhost/api/v1/projects/1/marketplaces/wb/connect" -Method POST -Headers $headers -Body '{"api_key":"test_token"}' | ConvertTo-Json
docker compose exec postgres psql -U wb -d wb -c "SELECT id, project_id, is_enabled, api_token_encrypted IS NOT NULL FROM project_marketplaces;"
```

### 5. Проверить что ingestion пишет данные с project_id
```powershell
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM products GROUP BY project_id;"
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM price_snapshots GROUP BY project_id;"
```


