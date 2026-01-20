# Docker Compose для EcomCore

## Local Quickstart (Локальный быстрый старт)

**Полный набор команд для первого запуска с нуля:**

### Шаг 1: Создать .env файл

**Расположение:** `D:\Work\EcomCore\.env` (корень репозитория, НЕ в `infra/docker/`)

```powershell
# Создать/открыть .env файл
notepad D:\Work\EcomCore\.env
```

**Содержимое .env:**
```env
# Database credentials (REQUIRED)
POSTGRES_DB=wb
POSTGRES_USER=wb
POSTGRES_PASSWORD=wbpassword

# Auto-apply migrations in dev mode (OPTIONAL, recommended for local dev)
AUTO_MIGRATE=1

# Bootstrap admin user (OPTIONAL, for automatic admin creation)
BOOTSTRAP_ADMIN=1
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=admin123
BOOTSTRAP_ADMIN_EMAIL=admin@local.dev
```

### Шаг 2: Запустить контейнеры

```powershell
# Перейти в директорию docker-compose (ОБЯЗАТЕЛЬНО!)
cd D:\Work\EcomCore\infra\docker

# Остановить старые контейнеры
docker compose down

# Запустить контейнеры с пересборкой
docker compose up -d --build

# Подождать инициализации (15 секунд)
Start-Sleep -Seconds 15
```

**Что происходит:**
- Если `AUTO_MIGRATE=1` → миграции применяются автоматически при старте API
- Если `BOOTSTRAP_ADMIN=1` → admin пользователь создаётся автоматически (если таблица users пуста)

### Шаг 3: Проверить статус

```powershell
# Проверить статус контейнеров
docker compose ps

# Проверить логи API (должны быть сообщения о миграциях и bootstrap)
docker compose logs api | Select-String -Pattern "migration|Bootstrap|PostgreSQL"

# Проверить, что таблицы созданы
docker compose exec postgres psql -U wb -d wb -c "\dt"
```

**Ожидаемые таблицы:** `users`, `projects`, `project_members`, и другие.

### Шаг 4: Проверить вход

```powershell
# Проверить API Docs
curl http://localhost:8000/docs

# Проверить вход (одна строка)
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
```

**Ожидаемый ответ:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### Шаг 5: Создать проект (через UI или API)

После успешного входа можно создать проект через фронтенд или API.

**Проверка через API:**
```powershell
# Получить токен (сохранить в переменную)
$response = curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{\"username\":\"admin\",\"password\":\"admin123\"}' | ConvertFrom-Json
$token = $response.access_token

# Создать проект
curl -X POST http://localhost:8000/api/v1/projects `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $token" `
  -d '{\"name\":\"Test Project\",\"description\":\"Test\"}'
```

---

## Ручной запуск (без AUTO_MIGRATE)

Если `AUTO_MIGRATE=0` или не установлен, миграции нужно применять вручную:

```powershell
cd D:\Work\EcomCore\infra\docker
docker compose down
docker compose up -d --build
Start-Sleep -Seconds 10
docker compose exec api alembic upgrade head
Start-Sleep -Seconds 5
```

## Порты

- **80**: nginx (http://localhost)
- **8000**: API (http://localhost:8000)
- **3000**: Frontend dev server (http://localhost:3000)

## Структура

- `docker-compose.yml` - основной файл конфигурации
- `.env` - **ОБЯЗАТЕЛЬНО** в корне репозитория: `D:\Work\EcomCore\.env` (НЕ в `infra/docker/`)

**Важно:** Docker Compose использует `env_file: ../../.env` (относительно `infra/docker/`), что указывает на корневой `.env` файл.

## Решение проблем

### Порт 8000 занят

Используйте скрипт `scripts/start-docker-compose.ps1 -Force` для автоматической остановки конфликтующих контейнеров.

### Nginx не может найти upstream

Убедитесь, что все сервисы подключены к сети `ecomcore-network` (проверьте `docker compose ps` и `docker network inspect ecomcore_ecomcore-network`).

### Docker filesystem/metadata corruption (I/O errors)

Если при создании контейнеров возникает ошибка:
```
Error response from daemon: open /var/lib/docker/containers/.../.tmp-config.v2.json...: input/output error
```

Это указывает на проблемы с файловой системой Docker или метаданными. Выполните следующие шаги:

#### Шаг 1: Автоматическое восстановление (рекомендуется)

**Вариант A: Из корня репозитория**
```powershell
cd D:\Work\EcomCore
.\scripts\docker_recover.ps1
```

**Вариант B: Из infra/docker**
```powershell
cd D:\Work\EcomCore\infra\docker
..\..\scripts\docker_recover.ps1
```

Скрипт автоматически:
- Останавливает и удаляет контейнеры проекта ecomcore
- Удаляет образы проекта
- Очищает кэш сборки
- Удаляет неиспользуемые ресурсы
- Проверяет конфликты порта 8000 и предлагает решения
- Пересобирает и запускает сервисы

**С опциями:**
```powershell
# Удалить также volumes (удалит данные БД!)
.\scripts\docker_recover.ps1 -RemoveVolumes

# Полная очистка всех неиспользуемых ресурсов Docker
.\scripts\docker_recover.ps1 -FullCleanup
```

#### Шаг 2: Ручное восстановление Docker Desktop

Если автоматическое восстановление не помогло:

1. **Перезапустите Docker Desktop:**
   - Закройте Docker Desktop полностью
   - Запустите снова
   - Дождитесь полной загрузки

2. **Если используется WSL2 backend:**
   ```powershell
   # Остановить все WSL2 дистрибутивы
   wsl --shutdown
   
   # Подождать 10 секунд, затем запустить Docker Desktop снова
   ```

3. **Проверьте свободное место на диске:**
   - Docker Desktop хранит данные в `C:\Users\<user>\AppData\Local\Docker` (или на диске, где установлен Docker)
   - Убедитесь, что есть достаточно свободного места (минимум 10-20 GB)

4. **Очистка через Docker Desktop:**
   - Откройте Docker Desktop
   - Settings → Troubleshoot → Clean / Purge data
   - ⚠️ **ВНИМАНИЕ:** Это удалит ВСЕ контейнеры, образы и volumes во всех проектах!
   - Используйте только если другие методы не помогли

#### Шаг 3: Проверка после восстановления

После выполнения шагов выше выполните проверку (см. раздел "Проверка работы сервисов" ниже).

Все сервисы должны показывать статус "Up" без ошибок I/O.

#### Дополнительная диагностика

Если проблема сохраняется:

```powershell
# Проверить статус Docker
docker info

# Проверить дисковое пространство Docker
docker system df

# Проверить логи Docker Desktop
# (обычно в: %LOCALAPPDATA%\Docker\log.txt)
```

### If recovery script hangs on stopping containers

Если скрипт восстановления зависает на этапе остановки контейнеров (на шаге "Step 1: Stopping and removing ecomcore containers"), это часто происходит из-за проблем с Docker Desktop/WSL2.

**Признаки:**
- Скрипт печатает "Working directory" и "COMPOSE_PROJECT_NAME", затем зависает
- Нет дальнейшего вывода

**Решение:**

1. **Проверьте отзывчивость Docker:**
   ```powershell
   docker info
   ```
   Если команда зависает или возвращает ошибку, Docker Engine не отвечает.

2. **Если Docker не отвечает:**
   - Закройте Docker Desktop полностью
   - Выполните: `wsl --shutdown` (если используется WSL2)
   - Подождите 10 секунд
   - Запустите Docker Desktop снова
   - Дождитесь полной загрузки
   - Повторите запуск скрипта

3. **Запустите скрипт с флагом -SkipStop:**
   ```powershell
   cd D:\Work\EcomCore
   .\scripts\docker_recover.ps1 -SkipStop
   ```
   Это пропустит этап остановки контейнеров и перейдет к очистке и перезапуску.

4. **Настройка таймаутов (если нужно):**
   ```powershell
   # Увеличить таймаут для остановки до 120 секунд
   .\scripts\docker_recover.ps1 -TimeoutSecStop 120
   ```

**Дополнительные опции скрипта:**
```powershell
# Пропустить остановку контейнеров
.\scripts\docker_recover.ps1 -SkipStop

# Настроить таймаут остановки (по умолчанию 60 секунд)
.\scripts\docker_recover.ps1 -TimeoutSecStop 90

# Комбинация опций
.\scripts\docker_recover.ps1 -SkipStop -RemoveVolumes
```

## Проверка работоспособности (Verification)

После успешного запуска всех сервисов выполните проверку:

### 1. Статус контейнеров

```powershell
cd D:\Work\EcomCore\infra\docker
docker compose ps
```

Все сервисы должны показывать статус "Up" (не "Restarting" или "Exited").

### 2. Логи сервисов

```powershell
# Логи API (последние 100 строк)
docker compose logs --tail=100 api

# Логи nginx (последние 100 строк)
docker compose logs --tail=100 nginx

# Логи frontend (последние 100 строк)
docker compose logs --tail=100 frontend
```

Проверьте отсутствие критических ошибок (connection refused, upstream not found, etc.).

### 3. Проверка HTTP endpoints

**Определите порт API:**
```powershell
# Если есть override файл, используется порт 8001, иначе 8000
if (Test-Path "docker-compose.override.yml") { $apiPort = "8001" } else { $apiPort = "8000" }
```

**Проверка nginx (frontend):**
```powershell
try {
    $response = Invoke-WebRequest -Uri "http://localhost/" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Frontend (nginx): $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "✗ Frontend недоступен: $($_.Exception.Message)" -ForegroundColor Red
}
```

**Проверка API через nginx:**
```powershell
try {
    $response = Invoke-WebRequest -Uri "http://localhost/api/v1/health" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ API через nginx: $($response.StatusCode) - $($response.Content)" -ForegroundColor Green
} catch {
    # Если /api/v1/health не существует, проверяем /api/
    try {
        $response = Invoke-WebRequest -Uri "http://localhost/api/" -Method GET -UseBasicParsing -TimeoutSec 5
        Write-Host "✓ API через nginx: $($response.StatusCode) (endpoint доступен)" -ForegroundColor Green
    } catch {
        Write-Host "✗ API через nginx недоступен: $($_.Exception.Message)" -ForegroundColor Red
    }
}
```

**Проверка API напрямую (FastAPI docs):**
```powershell
# Используйте $apiPort (8000 или 8001)
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$apiPort/docs" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ API Docs: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "✗ API Docs недоступны: $($_.Exception.Message)" -ForegroundColor Red
}
```

**Проверка health endpoint:**
```powershell
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$apiPort/api/v1/health" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Health check: $($response.StatusCode) - $($response.Content)" -ForegroundColor Green
} catch {
    Write-Host "✗ Health check failed: $($_.Exception.Message)" -ForegroundColor Red
}
```

### 4. Полная проверка (скрипт)

```powershell
cd D:\Work\EcomCore\infra\docker

# Определить порт API
$apiPort = "8000"
if (Test-Path "docker-compose.override.yml") {
    $apiPort = "8001"
}

Write-Host "=== Verification ===" -ForegroundColor Cyan
Write-Host "API Port: $apiPort" -ForegroundColor Gray

# Frontend
try {
    $null = Invoke-WebRequest -Uri "http://localhost/" -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Frontend: OK" -ForegroundColor Green
} catch {
    Write-Host "✗ Frontend: FAILED" -ForegroundColor Red
}

# API via nginx
try {
    $null = Invoke-WebRequest -Uri "http://localhost/api/v1/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ API (nginx): OK" -ForegroundColor Green
} catch {
    Write-Host "✗ API (nginx): FAILED" -ForegroundColor Red
}

# API direct
try {
    $null = Invoke-WebRequest -Uri "http://localhost:$apiPort/docs" -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ API (direct): OK" -ForegroundColor Green
} catch {
    Write-Host "✗ API (direct): FAILED" -ForegroundColor Red
}
```

### Ожидаемые результаты

- ✅ Все контейнеры в статусе "Up"
- ✅ Логи без критических ошибок
- ✅ Frontend доступен на http://localhost/
- ✅ API доступен через nginx на http://localhost/api/v1/health
- ✅ API Docs доступны на http://localhost:8000/docs (или 8001 если используется override)

## Bootstrap Admin User (Автоматическое создание администратора)

После `docker compose down/up` таблица `users` может быть пустой, что приводит к ошибке 401 при попытке входа.

### ⚠️ ВАЖНО: Расположение .env файла

**Файл `.env` ОБЯЗАТЕЛЬНО должен находиться в корне репозитория:**
- Windows: `D:\Work\EcomCore\.env`
- Linux: `/root/apps/ecomcore/.env` (или путь к корню репозитория)

Docker Compose использует `env_file: ../../.env` (относительно `infra/docker/`), что указывает на корневой `.env` файл.

**Если `.env` файл отсутствует или находится не в корне, Docker Compose выдаст ошибку:**
```
ERROR: .env file not found
```

### Автоматическое создание (рекомендуется)

Добавьте в `.env` файл (`D:\Work\EcomCore\.env`):

```env
# Включить автоматическое создание admin пользователя при пустой таблице users
BOOTSTRAP_ADMIN=1
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=admin123
BOOTSTRAP_ADMIN_EMAIL=admin@local.dev
```

**Важно:**
- Bootstrap создаёт пользователя **только если таблица `users` пуста** (0 строк)
- Если пользователи уже существуют, bootstrap пропускается (безопасно)
- По умолчанию `BOOTSTRAP_ADMIN=0` (отключено) для безопасности
- Пароль хешируется с помощью bcrypt (та же функция, что используется в auth)
- Bootstrap выполняется **после** применения миграций (в startup event)

**После добавления переменных:**

```powershell
# Перейти в директорию docker-compose (ОБЯЗАТЕЛЬНО из этой директории!)
cd D:\Work\EcomCore\infra\docker

# Остановить контейнеры
docker compose down

# Запустить контейнеры с пересборкой
docker compose up -d --build

# Подождать инициализации PostgreSQL (10 секунд)
Start-Sleep -Seconds 10

# Применить миграции (создаст таблицу users и другие таблицы)
docker compose exec api alembic upgrade head

# Подождать запуска API (5 секунд)
Start-Sleep -Seconds 5
```

**Проверка bootstrap в логах:**

```powershell
# Просмотр логов API с фильтром по слову "Bootstrap"
docker compose logs api | Select-String -Pattern "Bootstrap"
```

**Ожидаемые сообщения в логах:**
- Если bootstrap включен и таблица пуста: `Bootstrap admin user: ✓ Created admin user 'admin' (id=1, email=admin@local.dev)`
- Если bootstrap включен, но пользователи уже есть: `Bootstrap admin user: skipped (users table not empty, X user(s) exist)`
- Если bootstrap отключен: сообщений с "Bootstrap" не будет (или только debug-уровень)

### Ручное создание (fallback)

Если автоматический bootstrap не сработал, используйте существующий скрипт:

```powershell
# Из директории infra/docker (ОБЯЗАТЕЛЬНО!)
cd D:\Work\EcomCore\infra\docker

# Использовать существующий скрипт (создаст или обновит admin с указанным паролем)
# Пароль по умолчанию: admin123
docker compose exec api python /app/scripts/create_admin_user.py admin123

# Или с другим паролем:
docker compose exec api python /app/scripts/create_admin_user.py mypassword
```

**Скрипт идемпотентен:**
- Если пользователь не существует → создаст с `is_superuser=true`
- Если пользователь существует с тем же паролем → пропустит (не изменяет)
- Если пользователь существует с другим паролем → обновит пароль и установит `is_superuser=true`

**Альтернатива: создание через Python напрямую (одна строка):**

```powershell
docker compose exec api python -c "from app.core.security import get_password_hash; from app.db_users import create_user, get_user_by_username; username='admin'; password='admin123'; existing=get_user_by_username(username); hashed=get_password_hash(password) if not existing or not existing['hashed_password'].startswith('$2b$') else None; user=create_user(username, 'admin@local.dev', hashed, is_superuser=True) if not existing else existing; print(f'User: {user}')"
```

**Примечание:** Рекомендуется использовать скрипт `/app/scripts/create_admin_user.py` - он проще и надежнее.

### Проверка входа

После создания пользователя проверьте вход:

**Windows PowerShell (многострочные команды):**

```powershell
# Проверка API Docs (прямой доступ)
curl http://localhost:8000/docs

# Проверка API Docs (через nginx)
curl http://localhost/api/docs

# Проверка входа (PowerShell - используйте обратные кавычки ` для переноса строк)
curl -X POST http://localhost:8000/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"admin\",\"password\":\"admin123\"}'

# Или через nginx
curl -X POST http://localhost/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
```

**Windows PowerShell (однострочные команды, без переноса):**

```powershell
# Проверка API Docs
curl http://localhost:8000/docs
curl http://localhost/api/docs

# Проверка входа (одна строка)
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
curl -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/json" -d '{\"username\":\"admin\",\"password\":\"admin123\"}'
```

**Bash/Linux:**

```bash
# Проверка API Docs
curl http://localhost:8000/docs
curl http://localhost/api/docs

# Проверка входа
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'
curl -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}'
```

**Ожидаемый ответ (успешный вход):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Ожидаемый ответ (ошибка 401 - пользователь не найден или неверный пароль):**
```json
{
  "detail": "Incorrect username or password"
}
```

**Примечание:** API доступен по двум адресам:
- **Прямой доступ:** `http://localhost:8000/docs` и `http://localhost:8000/api/v1/auth/login`
- **Через nginx:** `http://localhost/api/docs` и `http://localhost/api/v1/auth/login`

## Troubleshooting (Решение проблем)

### Docker CLI ошибка: "dockerDesktopLinuxEngine pipe missing"

**Симптомы:**
```
error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/v1.24/containers/json": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

**Причина:** Docker Desktop engine не запущен или завис.

**Решение:**
1. Откройте Docker Desktop
2. Если Docker Desktop не отвечает:
   - Закройте Docker Desktop полностью (через системный трей)
   - Если используется WSL2: выполните `wsl --shutdown` в PowerShell
   - Подождите 10 секунд
   - Запустите Docker Desktop снова
   - Дождитесь полной загрузки (иконка в трее должна быть зеленая)
3. Повторите команду `docker compose`

### Ошибка 401 при входе (Incorrect username or password)

**Проверка 1: Существует ли пользователь в БД?**

```powershell
# Проверить количество пользователей
docker compose exec postgres psql -U wb -d wb -c "SELECT COUNT(*) FROM users;"

# Если 0 → пользователь не создан, нужно создать
# Если > 0 → проверить username и пароль
```

**Проверка 2: Проверить логи bootstrap**

```powershell
docker compose logs api | Select-String -Pattern "Bootstrap"
```

Если bootstrap не сработал:
- Убедитесь, что `BOOTSTRAP_ADMIN=1` в `.env` файле
- Убедитесь, что `BOOTSTRAP_ADMIN_PASSWORD=admin123` в `.env` файле
- Перезапустите API: `docker compose restart api`

**Решение: Создать пользователя вручную**

```powershell
cd D:\Work\EcomCore\infra\docker
docker compose exec api python /app/scripts/create_admin_user.py admin123
```

### Ошибка: "relation 'projects' does not exist" или "relation 'projects' does not exist"

**Симптомы:**
```
psycopg2.errors.UndefinedTable: relation "projects" does not exist
```

**Причина:** Миграции Alembic не применены или применены не полностью.

**Решение:**

**Вариант 1: Автоматическое применение (рекомендуется для dev)**

Добавьте в `.env` файл:
```env
AUTO_MIGRATE=1
```

Затем перезапустите API:
```powershell
cd D:\Work\EcomCore\infra\docker
docker compose restart api
```

Миграции применятся автоматически при старте.

**Вариант 2: Ручное применение**

```powershell
cd D:\Work\EcomCore\infra\docker

# Проверить текущую ревизию
docker compose exec api alembic current

# Применить все миграции
docker compose exec api alembic upgrade head

# Проверить, что таблицы созданы
docker compose exec postgres psql -U wb -d wb -c "\dt"
```

**Ожидаемые таблицы:** `users`, `projects`, `project_members`, `marketplaces`, и другие.

**Проверка DATABASE_URL:**

Убедитесь, что API и Alembic используют одну и ту же БД:

```powershell
# Проверить переменные окружения API
docker compose exec api env | Select-String -Pattern "POSTGRES|DATABASE"

# Проверить подключение к БД
docker compose exec api python -c "from app.db import engine; from sqlalchemy import text; conn = engine.connect(); print('DB:', conn.execute(text('SELECT current_database()')).scalar())"
```

**Если миграции не применяются:**

1. Проверить порядок миграций:
   ```powershell
   docker compose exec api alembic history
   ```

2. Проверить heads (не должно быть multiple heads):
   ```powershell
   docker compose exec api alembic heads
   ```

3. Если multiple heads → нужно merge или stamp:
   ```powershell
   # Посмотреть диагностику
   docker compose exec api python /app/scripts/alembic_db_diagnose.py
   ```

### Ошибка: ".env file not found"

**Причина:** Docker Compose не может найти `.env` файл.

**Решение:**
1. Убедитесь, что `.env` файл находится в корне репозитория:
   - Windows: `D:\Work\EcomCore\.env`
   - Linux: `/root/apps/ecomcore/.env` (или ваш путь к корню)
2. Проверьте, что вы запускаете `docker compose` из директории `infra/docker`
3. Проверьте содержимое `.env`:
   ```powershell
   # Windows
   Get-Content D:\Work\EcomCore\.env
   
   # Linux
   cat /root/apps/ecomcore/.env
   ```

### Миграции не применяются

**Проверка:**

```powershell
# Проверить текущую ревизию
docker compose exec api alembic current

# Проверить доступные миграции
docker compose exec api alembic heads
```

**Решение:**

```powershell
# Применить все миграции
docker compose exec api alembic upgrade head

# Если ошибка "Can't locate revision" → возможно нужно stamp
docker compose exec api alembic stamp head
docker compose exec api alembic upgrade head
```

### API не запускается или падает

**Проверка логов:**

```powershell
# Посмотреть последние логи API
docker compose logs api --tail=50

# Следить за логами в реальном времени
docker compose logs api -f
```

**Частые причины:**
- База данных не готова: подождите 10-15 секунд после `docker compose up`
- Неверные переменные окружения: проверьте `.env` файл
- Порт 8000 занят: используйте `docker compose ps` для проверки

## How to run recovery script

```powershell
cd D:\Work\EcomCore
.\scripts\docker_recover.ps1
```

Или с опцией пропуска остановки (если скрипт зависает на остановке):

```powershell
cd D:\Work\EcomCore
.\scripts\docker_recover.ps1 -SkipStop
```
