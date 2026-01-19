# Скрипт для проверки персистентности проектов (PowerShell)
# Создает 2 проекта, останавливает контейнеры, запускает снова и проверяет, что проекты сохранились

$ErrorActionPreference = "Stop"

Write-Host "=== Тест персистентности проектов ===" -ForegroundColor Cyan
Write-Host ""

$API_URL = "http://localhost:8000/api"

# Проверка, что API доступен
Write-Host "1. Проверка доступности API..." -ForegroundColor Yellow
try {
    $healthCheck = Invoke-RestMethod -Uri "${API_URL}/v1/health" -Method Get -ErrorAction Stop
    Write-Host "✅ API доступен" -ForegroundColor Green
} catch {
    Write-Host "❌ API недоступен по адресу ${API_URL}" -ForegroundColor Red
    Write-Host "Убедитесь, что контейнеры запущены: docker compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Получение токена
Write-Host "2. Получение токена аутентификации..." -ForegroundColor Yellow
if (-not $env:AUTH_TOKEN) {
    Write-Host "⚠️  ВАЖНО: Для этого скрипта нужен токен аутентификации" -ForegroundColor Yellow
    Write-Host "Создайте пользователя и получите токен вручную, затем установите переменную:" -ForegroundColor Yellow
    Write-Host '  $env:AUTH_TOKEN = "Bearer YOUR_TOKEN_HERE"' -ForegroundColor Yellow
    Write-Host ""
    Write-Host "❌ Переменная AUTH_TOKEN не установлена" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Токен найден" -ForegroundColor Green
Write-Host ""

# Проверка существующих проектов
Write-Host "3. Проверка существующих проектов..." -ForegroundColor Yellow
try {
    $headers = @{
        "Authorization" = $env:AUTH_TOKEN
    }
    $existingProjects = Invoke-RestMethod -Uri "${API_URL}/v1/projects" -Method Get -Headers $headers
    Write-Host "Найдено проектов: $($existingProjects.Count)" -ForegroundColor Cyan
} catch {
    Write-Host "⚠️  Не удалось получить список проектов: $_" -ForegroundColor Yellow
}
Write-Host ""

# Создание первого проекта
Write-Host "4. Создание первого проекта 'Test Project 1'..." -ForegroundColor Yellow
try {
    $body = @{
        name = "Test Project 1"
        description = "Test project for persistence check"
    } | ConvertTo-Json

    $project1Response = Invoke-RestMethod -Uri "${API_URL}/v1/projects" -Method Post -Headers $headers -Body $body -ContentType "application/json"
    $project1Id = $project1Response.id
    Write-Host "✅ Проект создан с ID: $project1Id" -ForegroundColor Green
} catch {
    Write-Host "❌ Не удалось создать первый проект: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Создание второго проекта
Write-Host "5. Создание второго проекта 'Test Project 2'..." -ForegroundColor Yellow
try {
    $body = @{
        name = "Test Project 2"
        description = "Second test project"
    } | ConvertTo-Json

    $project2Response = Invoke-RestMethod -Uri "${API_URL}/v1/projects" -Method Post -Headers $headers -Body $body -ContentType "application/json"
    $project2Id = $project2Response.id
    Write-Host "✅ Проект создан с ID: $project2Id" -ForegroundColor Green
} catch {
    Write-Host "❌ Не удалось создать второй проект: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Проверка проектов в БД
Write-Host "6. Проверка проектов в БД (через psql)..." -ForegroundColor Yellow
try {
    $projectsInDb = docker compose exec -T postgres psql -U wb -d wb -t -c "SELECT COUNT(*) FROM projects WHERE id IN ($project1Id, $project2Id);"
    $projectsInDb = $projectsInDb.Trim()
    if ($projectsInDb -ne "2") {
        Write-Host "❌ В БД найдено $projectsInDb проектов вместо 2" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ В БД найдены оба проекта" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Не удалось проверить БД: $_" -ForegroundColor Yellow
}
Write-Host ""

# Остановка контейнеров
Write-Host "7. Остановка контейнеров (docker compose down)..." -ForegroundColor Yellow
docker compose down
Write-Host "✅ Контейнеры остановлены" -ForegroundColor Green
Write-Host ""

# Запуск контейнеров снова
Write-Host "8. Запуск контейнеров снова (docker compose up -d)..." -ForegroundColor Yellow
docker compose up -d
Write-Host "Ожидание готовности PostgreSQL..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
Write-Host "✅ Контейнеры запущены" -ForegroundColor Green
Write-Host ""

# Ожидание готовности API
Write-Host "9. Ожидание готовности API..." -ForegroundColor Yellow
for ($i = 1; $i -le 30; $i++) {
    try {
        $healthCheck = Invoke-RestMethod -Uri "${API_URL}/v1/health" -Method Get -ErrorAction Stop
        Write-Host "✅ API готов" -ForegroundColor Green
        break
    } catch {
        if ($i -eq 30) {
            Write-Host "❌ API не готов после 30 попыток" -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Seconds 1
    }
}
Write-Host ""

# Проверка проектов после перезапуска
Write-Host "10. Проверка проектов после перезапуска..." -ForegroundColor Yellow
try {
    $projectsAfterRestart = Invoke-RestMethod -Uri "${API_URL}/v1/projects" -Method Get -Headers $headers
    $project1Found = $projectsAfterRestart | Where-Object { $_.id -eq $project1Id }
    $project2Found = $projectsAfterRestart | Where-Object { $_.id -eq $project2Id }

    if (-not $project1Found) {
        Write-Host "❌ Проект с ID $project1Id не найден после перезапуска" -ForegroundColor Red
        exit 1
    }

    if (-not $project2Found) {
        Write-Host "❌ Проект с ID $project2Id не найден после перезапуска" -ForegroundColor Red
        exit 1
    }

    Write-Host "✅ Проект 1 найден: $($project1Found.name)" -ForegroundColor Green
    Write-Host "✅ Проект 2 найден: $($project2Found.name)" -ForegroundColor Green
} catch {
    Write-Host "❌ Ошибка при проверке проектов: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Финальная проверка в БД
Write-Host "11. Финальная проверка в БД..." -ForegroundColor Yellow
try {
    $projectsInDbFinal = docker compose exec -T postgres psql -U wb -d wb -t -c "SELECT COUNT(*) FROM projects WHERE id IN ($project1Id, $project2Id);"
    $projectsInDbFinal = $projectsInDbFinal.Trim()
    if ($projectsInDbFinal -ne "2") {
        Write-Host "❌ В БД найдено $projectsInDbFinal проектов вместо 2" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ В БД найдены оба проекта" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Не удалось проверить БД: $_" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=== ✅ ТЕСТ ПРОЙДЕН: Проекты успешно сохранились после перезапуска ===" -ForegroundColor Green


