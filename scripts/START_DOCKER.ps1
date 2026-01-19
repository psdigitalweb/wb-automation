# Скрипт для запуска Docker контейнеров (PowerShell)
# Расположение: C:\Users\pavel\OneDrive\wb-automation

Write-Host "=== Поиск docker-compose.yml ===" -ForegroundColor Cyan
$dockerComposePath = "wb-automation\docker-compose.yml"
if (Test-Path $dockerComposePath) {
    Write-Host "✓ Найден: $dockerComposePath" -ForegroundColor Green
} else {
    Write-Host "✗ Не найден: $dockerComposePath" -ForegroundColor Red
    Write-Host "Текущая директория: $(Get-Location)" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n=== Переход в каталог wb-automation ===" -ForegroundColor Cyan
Set-Location wb-automation

Write-Host "`n=== Проверка статуса контейнеров ===" -ForegroundColor Cyan
docker compose ps

Write-Host "`n=== Запуск контейнеров (build при необходимости) ===" -ForegroundColor Cyan
docker compose up -d --build

Write-Host "`n=== Ожидание запуска API (10 секунд) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 10

Write-Host "`n=== Проверка статуса контейнеров после запуска ===" -ForegroundColor Cyan
docker compose ps

Write-Host "`n=== Проверка доступности API ===" -ForegroundColor Cyan
Write-Host "1. Health check:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Health: $($response.StatusCode) - $($response.Content)" -ForegroundColor Green
} catch {
    Write-Host "✗ Health недоступен: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n2. API Docs:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/docs" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Docs: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "✗ Docs недоступны: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Логи API (последние 20 строк) ===" -ForegroundColor Cyan
docker compose logs -n 20 api

Write-Host "`n=== Готово! ===" -ForegroundColor Green
Write-Host "API должен быть доступен на: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor Cyan


