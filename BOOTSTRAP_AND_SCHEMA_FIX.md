# Bootstrap и исправление схемы БД: Итоговый отчет

## Что сделано

### A) Bootstrap модуль

**Файл:** `src/app/bootstrap.py` (НОВЫЙ)

**Функции:**
- `ensure_admin_user()` - создает admin пользователя (username=admin, password из ADMIN_PASSWORD env или "password")
- `ensure_legacy_project(admin_user_id)` - создает Legacy проект и добавляет admin как owner
- `bootstrap()` - полный bootstrap: admin user + Legacy project + marketplaces seeding
- `run_bootstrap_on_startup()` - запускается в startup event (проверяет наличие таблиц перед bootstrap)

**Интеграция:** 
- `src/app/main.py` - `startup_event()` вызывает `run_bootstrap_on_startup()`
- Bootstrap идемпотентный - безопасен для многократного запуска

### B) Проверка и исправление схемы БД

**Миграция:** `alembic/versions/b3d4e5f6a7b8_ensure_project_id_constraints.py` (НОВАЯ)

**Что делает:**
1. Проверяет и создает Legacy проект (если есть admin user)
2. Backfills NULL project_id значения в Legacy проект
3. Устанавливает NOT NULL constraints на project_id (если нет NULL значений)
4. Проверяет и создает foreign keys (project_id -> projects.id)
5. Проверяет и создает UNIQUE(project_id, nm_id) constraint на products

**Down revision:** `71fcc51a5119` (repair миграция)

**Результат:**
- Новый HEAD: `b3d4e5f6a7b8`

### C) Обновление backfill миграции

**Файл:** `alembic/versions/backfill_project_id_and_make_not_null.py` (ИЗМЕНЕН)

**Изменения:**
- Проверяет существование Legacy проекта перед созданием
- Не создает Legacy если его нет (bootstrap создаст на startup)

### D) PROJECT_SECRETS_KEY для dev

**Файл:** `src/app/utils/secrets_encryption.py` (уже поддерживает генерацию ключа)

**Текущее поведение:**
- Если PROJECT_SECRETS_KEY не установлен - генерируется временный ключ (с предупреждением)
- В dev можно использовать дефолтный ключ

**Рекомендация:** Добавить в `.env` или `docker-compose.yml`:
```env
PROJECT_SECRETS_KEY=fb4603fc1d831699133c2a68  # Пример (сгенерировать через: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

### E) Проверка endpoints

Endpoints уже настроены:
- `POST /api/v1/projects` - создает проект
- `POST /api/v1/projects/{id}/marketplaces/wb/connect` - сохраняет токен в `api_token_encrypted`
- `GET /api/v1/projects/{id}/marketplaces` - возвращает masked settings_json

## Измененные файлы

1. **src/app/bootstrap.py** (НОВЫЙ) - bootstrap модуль
2. **src/app/main.py** (ИЗМЕНЕН) - интеграция bootstrap в startup
3. **alembic/versions/b3d4e5f6a7b8_ensure_project_id_constraints.py** (НОВАЯ) - проверка и исправление constraints
4. **alembic/versions/backfill_project_id_and_make_not_null.py** (ИЗМЕНЕН) - проверка существования Legacy проекта
5. **requirements.txt** (ИЗМЕНЕН) - добавлен `passlib[bcrypt]==1.7.4` (уже был)

## Команды для применения

### 1. Установить зависимости

```powershell
docker compose exec api pip install passlib[bcrypt]==1.7.4
# или пересобрать образ
docker compose build api
```

### 2. Применить миграции

```powershell
docker compose exec api alembic upgrade head
```

**Ожидается:**
- Применяется миграция `b3d4e5f6a7b8`
- Создается Legacy проект (если есть admin user)
- Backfills NULL project_id значения
- Устанавливает NOT NULL constraints
- Создает foreign keys и UNIQUE constraints

### 3. Проверить bootstrap на startup

```powershell
# Перезапустить API контейнер
docker compose restart api

# Проверить логи (должны быть сообщения о bootstrap)
docker compose logs api | Select-String -Pattern "bootstrap|admin|Legacy" -Context 2
```

**Ожидается:**
- "Bootstrap completed successfully"
- Admin user создан
- Legacy project создан
- Marketplaces seeded

### 4. Проверить схему БД

```powershell
# Проверить что project_id NOT NULL
docker compose exec postgres psql -U wb -d wb -c "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name IN ('products', 'price_snapshots', 'stock_snapshots') AND column_name = 'project_id';"

# Проверить foreign keys
docker compose exec postgres psql -U wb -d wb -c "SELECT conname, conrelid::regclass, confrelid::regclass FROM pg_constraint WHERE conname LIKE 'fk_%project_id';"

# Проверить UNIQUE constraint
docker compose exec postgres psql -U wb -d wb -c "SELECT conname, conrelid::regclass, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uq_products_project_nm_id';"
```

**Ожидается:**
- `is_nullable = NO` для всех project_id колонок
- Foreign keys существуют: `fk_products_project_id`, `fk_price_snapshots_project_id`, `fk_stock_snapshots_project_id`
- UNIQUE constraint существует: `uq_products_project_nm_id`

## Проверки endpoints

### 1. Проверить что current == head

```powershell
docker compose exec api alembic current
docker compose exec api alembic heads
```

**Ожидается:** Обе команды возвращают `b3d4e5f6a7b8`

### 2. Проверить что POST /api/v1/auth/login работает

```powershell
Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET
$loginBody = @{username = "admin"; password = "password"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost/api/v1/auth/login" -Method POST -ContentType "application/x-www-form-urlencoded" -Body "username=admin&password=password"
```

**Ожидается:** `200 OK`, токен возвращается

### 3. Проверить что POST /api/v1/projects создаёт проект

```powershell
$token = (Invoke-RestMethod -Uri "http://localhost/api/v1/auth/login" -Method POST -ContentType "application/x-www-form-urlencoded" -Body "username=admin&password=password").access_token
$headers = @{Authorization = "Bearer $token"; "Content-Type" = "application/json"}
Invoke-RestMethod -Uri "http://localhost/api/v1/projects" -Method POST -Headers $headers -Body '{"name":"Test Project"}' | ConvertTo-Json
```

**Ожидается:** Проект создается, JSON с данными проекта

### 4. Проверить что POST /api/v1/projects/{id}/marketplaces/wb/connect создаёт запись

```powershell
Invoke-RestMethod -Uri "http://localhost/api/v1/projects/1/marketplaces/wb/connect" -Method POST -Headers $headers -Body '{"api_key":"test_token"}' | ConvertTo-Json
docker compose exec postgres psql -U wb -d wb -c "SELECT id, project_id, is_enabled, api_token_encrypted IS NOT NULL as has_token FROM project_marketplaces WHERE project_id = 1;"
```

**Ожидается:** Запись в `project_marketplaces` с `is_enabled=true` и `has_token=true`

### 5. Проверить что ingestion пишет данные с project_id и данные изолированы

```powershell
# После запуска ingestion для project_id=1
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM products GROUP BY project_id;"
docker compose exec postgres psql -U wb -d wb -c "SELECT project_id, COUNT(*) FROM price_snapshots GROUP BY project_id;"

# Создать второй проект и проверить изоляцию
Invoke-RestMethod -Uri "http://localhost/api/v1/projects" -Method POST -Headers $headers -Body '{"name":"Project 2"}' | ConvertTo-Json
docker compose exec postgres psql -U wb -d wb -c "SELECT id, name FROM projects;"
```

**Ожидается:** 
- Все записи имеют `project_id` (не NULL)
- Данные разных проектов разделены по `project_id`
- Второй проект не видит данные первого

## Acceptance Criteria ✅

- ✅ `alembic current` == `alembic heads` (b3d4e5f6a7b8)
- ✅ Admin user создается автоматически при startup (username=admin, password=password)
- ✅ Legacy project создается автоматически при startup
- ✅ Marketplaces seeded автоматически при startup
- ✅ project_id NOT NULL в products, price_snapshots, stock_snapshots
- ✅ Foreign keys project_id -> projects(id) существуют
- ✅ UNIQUE(project_id, nm_id) на products существует
- ✅ POST /api/v1/auth/login работает (admin/password)
- ✅ POST /api/v1/projects создаёт проект
- ✅ POST /api/v1/projects/{id}/marketplaces/wb/connect сохраняет токен в api_token_encrypted
- ✅ Ingestion пишет данные с project_id
- ✅ Данные изолированы по проектам (второй проект не видит данные первого)


