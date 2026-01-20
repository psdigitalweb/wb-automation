# Исправление группировки WB Finances отчётов

## Проблема

UI "WB Finances — Reports" показывал десятки/сотни "Report ID" для одного периода, у каждой записи `rows_count=1`. Это неверно: за период должен быть 1–2 отчёта, а не множество.

**Ошибка:** В ingestion использовался `rrd_id` (ID строки) как `report_id` вместо `realizationreport_id` (ID отчёта). Код пытался найти "report_id" среди полей `["rrd_id", "realizationreport_id", "report_id", ...]`, и если первым находился `rrd_id`, он использовался как ID отчёта. В результате каждая строка отчёта (с уникальным `rrd_id`) создавала отдельную запись в `wb_finance_reports`.

## Исправление

### Правильные поля WB API

Из ответа `/api/v5/supplier/reportDetailByPeriod`:
- **`realizationreport_id`** (BIGINT) — ID ОТЧЁТА (все строки с одинаковым ID относятся к одному отчёту)
- **`rrd_id`** (BIGINT) — ID СТРОКИ (уникальный идентификатор строки в рамках отчёта)

### Логика хранения

**wb_finance_reports:**
- `report_id` = `realizationreport_id` (ID отчёта)
- `rows_count` = реальное количество строк отчёта
- Один отчёт = один `realizationreport_id`

**wb_finance_report_lines:**
- `report_id` = `realizationreport_id` (связь с header)
- `line_id` = `rrd_id` (ID строки)
- Уникальность: `(project_id, report_id, line_id)`

### Ingestion

1. Группировка строк по `realizationreport_id`
2. Для каждого `realizationreport_id`:
   - Создать/обновить **ОДИН** header в `wb_finance_reports`
   - Сохранить **ВСЕ** строки отчёта в `wb_finance_report_lines` с `line_id = rrd_id`
3. Повторная загрузка того же периода не создаёт новые отчёты (идемпотентность)

## Изменённые файлы

1. **`src/app/ingest_wb_finances.py`**
   - Группировка по `realizationreport_id` вместо `rrd_id`
   - Использование `rrd_id` как `line_id` для строк

2. **`src/app/db_wb_finances.py`**
   - Функция `insert_report_line_if_new` принимает `line_id` (int)
   - Уникальность по `(project_id, report_id, line_id)`

3. **`alembic/versions/fix_wb_finances_report_grouping.py`**
   - Добавлена колонка `line_id BIGINT` в `wb_finance_report_lines`
   - Изменён уникальный индекс с `(project_id, report_id, line_uid)` на `(project_id, report_id, line_id)`

## Результат

**До исправления:**
- 100+ "отчётов" за период (каждая строка = отдельный "отчёт")
- `rows_count` = 1 для каждого "отчёта"

**После исправления:**
- 1–2 отчёта за период (корректно)
- `rows_count` = реальное количество строк (например, 150, 200)

## Почему фронт теперь покажет корректные данные

API endpoint `GET /api/v1/projects/{project_id}/marketplaces/wildberries/finances/reports` возвращает данные из `wb_finance_reports` (headers). После исправления группировки:

- В таблице `wb_finance_reports` хранятся только headers отчётов (`report_id` = `realizationreport_id`)
- Каждый header представляет один реальный отчёт с корректным `rows_count`
- UI получает список из 1–2 отчётов за период вместо сотен записей

Frontend без изменений, т.к. контракт API остался прежним, изменилась только логика группировки данных в БД.
