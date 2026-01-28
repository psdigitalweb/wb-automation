# Автоматическая диагностика отчёта "Расхождение цен"

## Обзор

После пересборки БД отчёт "Расхождение цен" может не работать из-за отсутствия данных в одной из таблиц или неправильной конфигурации. Для решения этой проблемы добавлена автоматическая диагностика и логирование.

## Что было сделано

### 1. Диагностический Celery task

**Файл:** `src/app/tasks/price_discrepancies.py`

**Задачи:**
- `app.tasks.price_discrepancies.diagnose_data_availability` - диагностика для одного проекта
- `app.tasks.price_discrepancies.diagnose_all_projects_data_availability` - диагностика для всех проектов с WB

**Проверяет:**
- Наличие `brand_id` в `project_marketplaces.settings_json` для WB
- Количество записей в `rrp_snapshots`
- Количество записей в `price_snapshots`
- Количество записей в `frontend_catalog_price_snapshots`
- Количество записей в `stock_snapshots`
- Количество записей в `products`
- Mapping между `products.vendor_code_norm` и `rrp_snapshots.vendor_code_norm`
- Тестовый запрос для проверки наличия данных в отчёте

**Логирование:**
- Все проверки логируются с уровнем INFO
- Предупреждения (warnings) логируются с уровнем WARNING
- Ошибки (errors) логируются с уровнем ERROR
- Время выполнения и количество найденных проблем

### 2. Логирование в API endpoint

**Файл:** `src/app/api_wb_price_discrepancies.py`

**Добавлено:**
- Логирование начала запроса с параметрами
- Логирование завершения запроса с количеством найденных записей и временем выполнения
- Предупреждение, если отчёт пустой (total_count=0)

### 3. Post-ingest hook

**Файл:** `src/app/tasks/ingest_execute.py`

**Добавлено:**
- После успешного завершения ingest для доменов `rrp_xml`, `frontend_prices`, `prices`, `products`, `stocks` автоматически запускается диагностика
- Диагностика запускается асинхронно (не блокирует ingest)
- Ошибки при запуске диагностики не влияют на результат ingest

### 4. Периодическое расписание

**Файл:** `src/app/celery_app.py`

**Добавлено:**
- Расписание `diagnose-price-discrepancies-data-every-6-hours` - запускается каждые 6 часов
- Проверяет все проекты с включённым Wildberries marketplace
- Обеспечивает обнаружение проблем даже если post-ingest hooks не сработали

## Как проверить

### 1. Проверка регистрации tasks

**Windows PowerShell:**
```powershell
# В контейнере worker или beat
docker compose exec worker celery -A app.celery_app inspect registered | Select-String "price_discrepancies"
```

**Linux/Mac:**
```bash
docker compose exec worker celery -A app.celery_app inspect registered | grep price_discrepancies
```

Должны быть видны:
- `app.tasks.price_discrepancies.diagnose_data_availability`
- `app.tasks.price_discrepancies.diagnose_all_projects_data_availability`

### 2. Ручной запуск диагностики для проекта

**Windows PowerShell / Linux / Mac:**
```bash
# В контейнере worker
docker compose exec worker celery -A app.celery_app call app.tasks.price_discrepancies.diagnose_data_availability --args='[1]'
```

Или через Python:

```python
from app.tasks.price_discrepancies import diagnose_data_availability
result = diagnose_data_availability(project_id=1)
print(result)
```

### 3. Проверка логов после ingest

**Windows PowerShell:**
```powershell
# После запуска ingest для rrp_xml, frontend_prices, prices, products или stocks
docker compose logs worker | Select-String "price_discrepancies diagnostics"
```

**Linux/Mac:**
```bash
docker compose logs worker | grep "price_discrepancies diagnostics"
```

Должны быть видны логи:
```
INFO: execute_ingest: triggered price_discrepancies diagnostics for project_id=1 after job_code=rrp_xml
INFO: diagnose_data_availability: starting for project_id=1
INFO: diagnose_data_availability: completed for project_id=1 warnings=2 errors=0 elapsed=123.45ms
```

### 4. Проверка логов API endpoint

**Windows PowerShell:**
```powershell
# После запроса к API
docker compose logs api | Select-String "get_wb_price_discrepancies"
```

**Linux/Mac:**
```bash
docker compose logs api | grep "get_wb_price_discrepancies"
```

Должны быть видны логи:
```
INFO: get_wb_price_discrepancies: starting for project_id=1 page=1 page_size=25 only_below_rrp=True
INFO: get_wb_price_discrepancies: completed for project_id=1 total_count=42 items_returned=25 elapsed=45.67ms
```

Если отчёт пустой:
```
WARNING: get_wb_price_discrepancies: no data found for project_id=1. Consider running diagnose_data_availability task to check prerequisites.
```

### 5. Проверка периодического расписания

**Windows PowerShell:**
```powershell
# Проверка расписания в beat
docker compose logs beat | Select-String "diagnose-price-discrepancies"
```

**Linux/Mac:**
```bash
docker compose logs beat | grep "diagnose-price-discrepancies"
```

Должны быть видны логи каждые 6 часов:
```
INFO: diagnose_all_projects_data_availability: starting
INFO: diagnose_all_projects_data_availability: found 2 projects with WB enabled
INFO: diagnose_all_projects_data_availability: completed projects_checked=2 projects_with_warnings=1 projects_with_errors=0 elapsed=234.56ms
```

### 6. Проверка через API endpoint

**Windows PowerShell:**
```powershell
# Запрос к API
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/projects/1/wildberries/price-discrepancies?only_below_rrp=true&page_size=1" -Method GET
```

**Linux/Mac:**
```bash
curl "http://localhost:8000/api/v1/projects/1/wildberries/price-discrepancies?only_below_rrp=true&page_size=1"
```

Проверить логи:
```powershell
# Windows PowerShell
docker compose logs api | Select-Object -Last 20
```

```bash
# Linux/Mac
docker compose logs api | tail -20
```

### 7. Диагностика проблем

Если отчёт не работает, проверьте логи диагностики:

**Windows PowerShell:**
```powershell
# Найти все предупреждения и ошибки
docker compose logs worker | Select-String -Pattern "(WARNING|ERROR).*price_discrepancies"
```

**Linux/Mac:**
```bash
docker compose logs worker | grep -E "(WARNING|ERROR).*price_discrepancies"
```

Типичные проблемы:

1. **Нет brand_id:**
   ```
   WARNING: brand_id is not configured in project_marketplaces.settings_json
   ```
   **Решение:** Настроить brand_id в настройках проекта для Wildberries marketplace

2. **Нет RRP snapshots:**
   ```
   WARNING: No RRP snapshots found for project_id=1. Run RRP XML ingestion to populate data.
   ```
   **Решение:** Запустить ingest для `rrp_xml`

3. **Нет frontend prices:**
   ```
   WARNING: No frontend catalog price snapshots found for brand_id=41189
   ```
   **Решение:** Запустить ingest для `frontend_prices`

4. **Нет mapping:**
   ```
   WARNING: No mapping found between products.vendor_code_norm and rrp_snapshots.vendor_code_norm
   ```
   **Решение:** Проверить, что `vendor_code_norm` в products совпадает с `vendor_code_norm` в rrp_snapshots

## Структура диагностического отчёта

```json
{
  "project_id": 1,
  "started_at": "2026-01-26T10:00:00Z",
  "completed_at": "2026-01-26T10:00:01Z",
  "elapsed_ms": 123.45,
  "checks": {
    "brand_id": {
      "configured": true,
      "brand_id": 41189,
      "is_enabled": true
    },
    "rrp_snapshots": {
      "count": 150,
      "distinct_skus": 150,
      "latest_snapshot_at": "2026-01-26T09:00:00Z"
    },
    "price_snapshots": {
      "count": 200,
      "distinct_nm_ids": 200
    },
    "frontend_catalog_price_snapshots": {
      "count": 180,
      "distinct_nm_ids": 180
    },
    "stock_snapshots": {
      "count": 200,
      "distinct_nm_ids": 200
    },
    "products": {
      "count": 200,
      "distinct_nm_ids": 200,
      "distinct_vendor_codes": 200
    },
    "vendor_code_mapping": {
      "products_with_rrp": 150,
      "coverage_percent": 75.0
    },
    "sample_report_query": {
      "rows_with_both_rrp_and_showcase": 120
    }
  },
  "warnings": [
    "Low mapping coverage: only 150/200 products have matching RRP snapshots (75.0%)."
  ],
  "errors": [],
  "summary": {
    "total_warnings": 1,
    "total_errors": 0,
    "has_data": true
  }
}
```

## Точки в коде

### API Endpoint
- **Файл:** `src/app/api_wb_price_discrepancies.py`
- **Endpoint:** `GET /api/v1/projects/{project_id}/wildberries/price-discrepancies`
- **Функция:** `get_wb_price_discrepancies()`
- **SQL builder:** `_build_discrepancies_sql()`

### Celery Tasks
- **Файл:** `src/app/tasks/price_discrepancies.py`
- **Tasks:**
  - `diagnose_data_availability(project_id)` - диагностика одного проекта
  - `diagnose_all_projects_data_availability()` - диагностика всех проектов

### Post-ingest Hook
- **Файл:** `src/app/tasks/ingest_execute.py`
- **Функция:** `execute_ingest(run_id)`
- **Триггер:** После успешного завершения ingest для доменов: `rrp_xml`, `frontend_prices`, `prices`, `products`, `stocks`

### Расписание
- **Файл:** `src/app/celery_app.py`
- **Schedule:** `diagnose-price-discrepancies-data-every-6-hours`
- **Cron:** `crontab(minute=0, hour="*/6")` - каждые 6 часов

## Минимальный дифф изменений

1. **Создан новый файл:** `src/app/tasks/price_discrepancies.py`
   - Добавлены 2 Celery tasks для диагностики

2. **Изменён файл:** `src/app/api_wb_price_discrepancies.py`
   - Добавлен import `logging`
   - Добавлено логирование в `get_wb_price_discrepancies()`

3. **Изменён файл:** `src/app/tasks/ingest_execute.py`
   - Добавлен import `logging`
   - Добавлен post-ingest hook для автоматической диагностики

4. **Изменён файл:** `src/app/celery_app.py`
   - Добавлено расписание `diagnose-price-discrepancies-data-every-6-hours`

## Проверка после чистой БД

После сноса БД и пересборки данных:

1. Запустить ingest для всех доменов:
   ```bash
   # Через API или через ingest schedules
   curl -X POST "http://localhost:8000/api/v1/projects/1/ingest/run" \
     -H "Content-Type: application/json" \
     -d '{"domain": "products"}'
   ```

2. Проверить логи диагностики:
   ```bash
   docker compose logs worker | grep "diagnose_data_availability"
   ```

3. Проверить отчёт через API:
   ```bash
   curl "http://localhost:8000/api/v1/projects/1/wildberries/price-discrepancies?only_below_rrp=true&page_size=1"
   ```

4. Если отчёт пустой, запустить диагностику вручную:
   ```bash
   docker compose exec worker celery -A app.celery_app call app.tasks.price_discrepancies.diagnose_data_availability --args='[1]'
   ```
   
   Или использовать кнопку "Собрать отчёт" на странице `/app/project/1/wildberries/price-discrepancies`

5. Проверить логи на наличие предупреждений и ошибок:
   
   **Windows PowerShell:**
   ```powershell
   docker compose logs worker | Select-String -Pattern "(WARNING|ERROR).*price_discrepancies"
   ```
   
   **Linux/Mac:**
   ```bash
   docker compose logs worker | grep -E "(WARNING|ERROR).*price_discrepancies"
   ```

## Важные замечания

1. **Отчёт рассчитывается on-the-fly** - нет материализованного view или кэша. Данные всегда актуальные.

2. **Диагностика не исправляет проблемы** - она только обнаруживает и логирует их. Исправление нужно делать вручную (настроить brand_id, запустить ingest и т.д.).

3. **Post-ingest hook срабатывает только для WB проектов** - проверка `marketplace_code == "wildberries"`.

4. **Диагностика запускается асинхронно** - не блокирует ingest, ошибки диагностики не влияют на результат ingest.

5. **Периодическое расписание проверяет все проекты** - даже если post-ingest hooks не сработали, проблемы будут обнаружены в течение 6 часов.
