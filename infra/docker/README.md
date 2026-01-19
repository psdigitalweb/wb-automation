# Docker Compose для EcomCore

## Быстрый старт

```powershell
cd D:\Work\EcomCore
.\scripts\start-docker-compose.ps1 -Force
```

## Ручной запуск

```powershell
cd D:\Work\EcomCore\infra\docker
docker compose down
docker compose up -d --build
docker compose exec api alembic upgrade head
```

## Порты

- **80**: nginx (http://localhost)
- **8000**: API (http://localhost:8000)
- **3000**: Frontend dev server (http://localhost:3000)

## Структура

- `docker-compose.yml` - основной файл конфигурации
- `.env` - должен находиться в корне репозитория (`../../.env`)

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
