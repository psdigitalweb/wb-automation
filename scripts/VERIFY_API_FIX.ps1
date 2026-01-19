# Скрипт для проверки фикса API после удаления ingest_rrp_xml

Write-Host "=== Пересборка API контейнера ===" -ForegroundColor Cyan
cd wb-automation
docker compose build --no-cache api

Write-Host "`n=== Перезапуск API ===" -ForegroundColor Cyan
docker compose up -d api

Write-Host "`n=== Ожидание запуска (15 секунд) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 15

Write-Host "`n=== Проверка статуса контейнера ===" -ForegroundColor Cyan
docker compose ps api

Write-Host "`n=== Проверка логов (последние 30 строк) ===" -ForegroundColor Cyan
docker compose logs -n 30 api

Write-Host "`n=== Проверка health endpoint ===" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Health: HTTP $($response.StatusCode)" -ForegroundColor Green
    Write-Host "  Response: $($response.Content)" -ForegroundColor Green
} catch {
    Write-Host "✗ Health недоступен: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Проверка docs endpoint ===" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/docs" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Docs: HTTP $($response.StatusCode)" -ForegroundColor Green
    Write-Host "  Swagger UI доступен: http://localhost:8000/docs" -ForegroundColor Green
} catch {
    Write-Host "✗ Docs недоступны: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Проверка на ошибки импорта ===" -ForegroundColor Cyan
$logs = docker compose logs -n 100 api
if ($logs -match "ModuleNotFoundError|ingest_rrp_xml") {
    Write-Host "✗ Найдены ошибки импорта!" -ForegroundColor Red
    $logs | Select-String -Pattern "ModuleNotFoundError|ingest_rrp_xml"
} else {
    Write-Host "✓ Ошибок импорта не найдено" -ForegroundColor Green
}

Write-Host "`n=== Готово! ===" -ForegroundColor Green


