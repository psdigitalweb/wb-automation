# Sprint: Wildberries Finances — загрузка финансовых отчётов

## Обзор

Реализована загрузка финансовых отчётов Wildberries (reportDetailByPeriod) на уровне проекта с хранением данных и списком отчётов в UI.

**Источник:** WB Finances API v5  
**Endpoint:** `/api/v5/supplier/reportDetailByPeriod`  
**Документация:** https://dev.wildberries.ru/swagger/finances

## Добавленные API Endpoints

### 1. POST `/api/v1/projects/{project_id}/marketplaces/wildberries/finances/ingest`

Запуск загрузки финансовых отчётов для проекта.

**Request Body:**
```json
{
  "date_from": "2026-01-01",
  "date_to": "2026-01-31"
}
```

**Response (202 Accepted):**
```json
{
  "status": "started",
  "task_id": "celery-task-id",
  "date_from": "2026-01-01",
  "date_to": "2026-01-31"
}
```

**Требования:**
- Authorization: Bearer TOKEN
- Проект membership (любой участник проекта)
- WB должен быть подключен в проекте и иметь token (иначе 400)

### 2. GET `/api/v1/projects/{project_id}/marketplaces/wildberries/finances/reports`

Получение списка загруженных финансовых отчётов проекта.

**Response (200 OK):**
```json
[
  {
    "report_id": 123,
    "period_from": "2026-01-01",
    "period_to": "2026-01-31",
    "currency": "RUB",
    "total_amount": 1000000.50,
    "rows_count": 456,
    "first_seen_at": "2026-01-21T12:00:00Z",
    "last_seen_at": "2026-01-21T12:00:00Z"
  }
]
```

**Сортировка:** `last_seen_at DESC`

## Добавленные таблицы БД

### 1. `wb_finance_reports`

Таблица шапок отчётов (для списка отчётов).

**DDL:**
```sql
CREATE TABLE wb_finance_reports (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    marketplace_code TEXT NOT NULL DEFAULT 'wildberries',
    report_id BIGINT NOT NULL,
    period_from DATE NULL,
    period_to DATE NULL,
    currency TEXT NULL,
    total_amount NUMERIC(20,2) NULL,
    rows_count INT NOT NULL DEFAULT 0,
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(project_id, marketplace_code, report_id)
);

CREATE INDEX ix_wb_finance_reports_project_last_seen 
    ON wb_finance_reports(project_id, last_seen_at DESC);
```

### 2. `wb_finance_report_lines`

Таблица строк отчётов (raw lines).

**DDL:**
```sql
CREATE TABLE wb_finance_report_lines (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    report_id BIGINT NOT NULL,
    line_uid TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    UNIQUE(project_id, report_id, line_uid)
);

CREATE INDEX ix_wb_finance_report_lines_project_report 
    ON wb_finance_report_lines(project_id, report_id);
```

## Идемпотентность

### Ключи уникальности:

1. **wb_finance_reports:**
   - `UNIQUE(project_id, marketplace_code, report_id)`
   - Если отчёт с таким `report_id` уже существует → обновляется `last_seen_at`, `rows_count`, `payload`

2. **wb_finance_report_lines:**
   - `UNIQUE(project_id, report_id, line_uid)`
   - `line_uid` вычисляется как `sha256(normalized_json)` строки
   - При повторной загрузке существующие строки пропускаются (INSERT ... ON CONFLICT DO NOTHING)

### Логика работы:

- При повторном запросе того же периода:
  - Новые отчёты/строки добавляются
  - Существующие не дублируются
  - `report_header` обновляет `last_seen_at` и `rows_count`
- Логируется summary: `inserted_reports`, `updated_reports`, `inserted_lines`, `skipped_lines`

## Изменённые файлы

### Backend:

1. `src/app/wb/finances_client.py` — клиент для WB Finances API v5
2. `src/app/db_wb_finances.py` — DB сервис для работы с финансовыми отчётами
3. `src/app/ingest_wb_finances.py` — модуль ingestion
4. `src/app/tasks/wb_finances.py` — Celery задача
5. `src/app/routers/marketplaces.py` — добавлены endpoints для finances
6. `src/app/schemas/marketplaces.py` — добавлены схемы для finances
7. `alembic/versions/add_wb_finance_reports_tables.py` — миграция для таблиц

### Frontend:

1. `frontend/app/app/project/[projectId]/marketplaces/page.tsx` — добавлена секция "Wildberries — Finances" с кнопкой загрузки
2. `frontend/app/app/project/[projectId]/wildberries/finances/reports/page.tsx` — страница списка отчётов

## Проверка вручную

### 1. Загрузка отчётов:

1. Откройте страницу проекта: `/app/project/{projectId}/marketplaces`
2. Убедитесь, что Wildberries подключен (статус "Connected ✅")
3. Найдите секцию "Wildberries — Finances"
4. Выберите даты (по умолчанию: первый день текущего месяца — сегодня)
5. Нажмите "Загрузить финансовые отчеты WB"
6. Должно появиться сообщение об успехе с task_id

### 2. Просмотр списка отчётов:

1. На странице marketplaces нажмите "Открыть список отчётов" или перейдите по `/app/project/{projectId}/wildberries/finances/reports`
2. Должна отобразиться таблица с загруженными отчётами (или сообщение "Отчётов пока нет")
3. Можно нажать "Обновить список" для обновления

### 3. Проверка логов (опционально):

```bash
docker compose logs worker --tail=50 | grep "ingest_wb_finance_reports"
```

Должны появиться логи с summary: `inserted_reports`, `updated_reports`, `inserted_lines`, `skipped_lines`.
