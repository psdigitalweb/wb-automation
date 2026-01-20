# Исправление группировки WB Finances отчётов

## Проблема

UI "WB Finances — Reports" показывал десятки/сотни "Report ID" для одного периода, у каждой записи `rows_count=1`. Это неверно: за период должен быть 1–2 отчёта, а не множество.

**Корневая причина:** В коде использовался `rrd_id` (ID строки) как `report_id` вместо `realizationreport_id` (ID отчёта). Код пытался найти "report_id" среди полей `["rrd_id", "realizationreport_id", "report_id", ...]`, и если первым находился `rrd_id`, он использовался как ID отчёта. В результате каждая строка отчёта (с уникальным `rrd_id`) создавала отдельную запись в `wb_finance_reports`, а не группировалась в один отчёт.

## Что было неправильно

1. **Неправильная группировка в ingestion:**
   - Код пытался найти "report_id" среди полей `["rrd_id", "realizationreport_id", "report_id", ...]`
   - Если первым находился `rrd_id`, он использовался как ID отчёта
   - В результате каждая строка (с уникальным `rrd_id`) создавала отдельный "отчёт"

2. **Структура данных:**
   - `report_id` в `wb_finance_reports` содержал ID строки вместо ID отчёта
   - `line_uid` использовал hash строки вместо реального `rrd_id` из API

## Что исправлено

### 1. Определены правильные поля из WB API

**WB Finances API v5 (`reportDetailByPeriod`) возвращает:**
- `realizationreport_id` (BIGINT) — ID отчёта (все строки с одинаковым `realizationreport_id` относятся к одному отчёту)
- `rrd_id` (BIGINT) — ID строки/строки в рамках отчёта

**Использование:**
- `report_id` = `realizationreport_id` (для группировки в `wb_finance_reports`)
- `line_id` = `rrd_id` (для уникальности строк в `wb_finance_report_lines`)

### 2. Миграция БД

**Файл:** `alembic/versions/fix_wb_finances_report_grouping.py`

**Изменения:**
- Добавлена колонка `line_id BIGINT` в таблицу `wb_finance_report_lines`
- Изменён уникальный ключ с `(project_id, report_id, line_uid)` на `(project_id, report_id, line_id)`
- `line_uid` оставлен для обратной совместимости (хранит hash)

**DDL:**
```sql
ALTER TABLE wb_finance_report_lines 
  ADD COLUMN line_id BIGINT;

DROP INDEX uq_wb_finance_report_lines_project_report_line;

CREATE UNIQUE INDEX uq_wb_finance_report_lines_project_report_line_id 
  ON wb_finance_report_lines(project_id, report_id, line_id);
```

### 3. Исправлен ingestion

**Файл:** `src/app/ingest_wb_finances.py`

**Изменения:**
- Группировка строк по `realizationreport_id` (ID отчёта)
- Использование `realizationreport_id` как `report_id` для `wb_finance_reports`
- Использование `rrd_id` как `line_id` для `wb_finance_report_lines`
- `rows_count` теперь корректно показывает количество строк в отчёте

**Логика:**
```python
# Группируем строки по realizationreport_id
for line in lines:
    report_id = line.get("realizationreport_id")  # ID отчёта
    line_id = line.get("rrd_id")  # ID строки
    
    # Группировка по report_id
    reports_dict[report_id].append(line)

# Для каждого отчёта создаём один header
for report_id, report_lines in reports_dict.items():
    upsert_report_header(
        report_id=report_id,  # realizationreport_id
        rows_count=len(report_lines),  # реальное количество строк
        ...
    )
    
    # Для каждой строки
    for line in report_lines:
        insert_report_line_if_new(
            report_id=report_id,  # realizationreport_id
            line_id=line.get("rrd_id"),  # rrd_id
            ...
        )
```

### 4. Обновлён DB сервис

**Файл:** `src/app/db_wb_finances.py`

**Изменения:**
- Функция `insert_report_line_if_new` теперь принимает `line_id` (int) вместо `line_uid` (str)
- Уникальность обеспечивается `(project_id, report_id, line_id)`
- Обновлены комментарии для ясности

### 5. API endpoint (без изменений)

**Endpoint:** `GET /api/v1/projects/{project_id}/marketplaces/wildberries/finances/reports`

Уже возвращает headers из `wb_finance_reports` (не строки), поэтому после исправления группировки будет возвращать правильное количество отчётов.

### 6. Frontend (без изменений)

UI уже правильно отображает данные из API. После исправления бэкенда будет показывать корректное количество отчётов.

## Изменённые файлы

1. **`alembic/versions/fix_wb_finances_report_grouping.py`** — новая миграция
2. **`src/app/ingest_wb_finances.py`** — исправлена группировка и извлечение полей
3. **`src/app/db_wb_finances.py`** — обновлена функция `insert_report_line_if_new` для использования `line_id`

## Результат

### До исправления:
- За период возвращалось 100+ "отчётов" (каждая строка = отдельный "отчёт")
- `rows_count` = 1 для каждого "отчёта"

### После исправления:
- За период возвращается 1–2 отчёта (корректное количество)
- `rows_count` = реальное количество строк в отчёте (например, 150, 200)

## Подтверждение исправления

**После перезагрузки периода:**
1. Открыть страницу `/app/project/{projectId}/wildberries/finances/reports`
2. Увидеть 1–2 отчёта за период вместо десятков/сотен
3. Каждый отчёт имеет `rows_count > 1` (реальное количество строк)

**Данные:**
- `report_id` = `realizationreport_id` (ID отчёта из WB API)
- `rows_count` = количество строк, принадлежащих этому отчёту
- Строки сохраняются отдельно в `wb_finance_report_lines` с `line_id = rrd_id`

## Технические детали

**Структура ответа WB API:**
```json
[
  {
    "realizationreport_id": 12345,  // ID отчёта (один для всех строк отчёта)
    "rrd_id": 67890,  // ID строки (уникален для каждой строки)
    "doc_date": "2026-01-01",
    "currency": "RUB",
    // ... другие поля
  },
  {
    "realizationreport_id": 12345,  // тот же отчёт
    "rrd_id": 67891,  // другая строка
    // ...
  }
]
```

**Хранение в БД:**
- `wb_finance_reports.report_id` = `realizationreport_id` (один header на отчёт)
- `wb_finance_report_lines.report_id` = `realizationreport_id` (связь с header)
- `wb_finance_report_lines.line_id` = `rrd_id` (уникальный ID строки)
