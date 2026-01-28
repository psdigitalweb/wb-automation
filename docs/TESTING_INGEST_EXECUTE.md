# Тестирование execute_ingest с безопасным async runner

## Проблема

Ранее `execute_ingest` использовал `asyncio.run()` напрямую, что приводило к ошибке:
```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

Это происходило, когда event loop уже был запущен в текущем потоке (например, из-за других async операций или конфигурации Celery).

## Решение

Создан универсальный helper `app.utils.asyncio_runner.run_async_safe()`, который:
- Проверяет наличие активного event loop
- Если loop не запущен → использует `asyncio.run()` напрямую
- Если loop уже запущен → запускает coroutine в отдельном потоке с новым event loop

## Инструкция по тестированию

### 1. Подготовка

Убедитесь, что:
- Celery worker запущен
- База данных доступна
- Нет застрявших runs в статусе `running` (используйте `scripts/unlock_stale_runs.py`)

### 2. Ручной запуск ingestion из UI

1. Откройте UI проекта
2. Перейдите в раздел ingestion (или соответствующий раздел для запуска ingestion)
3. Выберите домен (например, `frontend_prices`)
4. Запустите ingestion

### 3. Проверка логов Celery worker

В логах Celery worker должны появиться записи:

**Если event loop не запущен (нормальный случай):**
```
INFO app.utils.asyncio_runner: run_async_safe: detected_running_loop=False, using asyncio.run() (context: {'run_id': 123, 'job_code': 'frontend_prices'})
```

**Если event loop уже запущен:**
```
INFO app.utils.asyncio_runner: run_async_safe: detected_running_loop=True, using thread pool (context: {'run_id': 123, 'job_code': 'frontend_prices'})
```

### 4. Проверка результата в БД

Выполните SQL запрос:

```sql
SELECT 
    id,
    project_id,
    marketplace_code,
    job_code,
    status,
    started_at,
    finished_at,
    duration_ms,
    stats_json,
    error_message
FROM ingest_runs
WHERE id = :run_id  -- замените на актуальный run_id
ORDER BY created_at DESC
LIMIT 1;
```

**Ожидаемый результат:**
- `status` = `'success'` (или `'failed'` если была ошибка)
- `finished_at` заполнен (не NULL)
- `duration_ms` заполнен (не NULL)
- `stats_json` заполнен и содержит данные (например, `{"ok": true, ...}`)
- `error_message` = NULL (если успешно)

### 5. Проверка через API

```bash
# Получить последний run для проекта
curl -X GET "http://localhost:8000/api/v1/projects/1/ingest/runs?limit=1" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Проверить конкретный run
curl -X GET "http://localhost:8000/api/v1/projects/1/ingest/runs/:run_id" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Ожидаемый ответ:**
```json
{
  "id": 123,
  "status": "success",
  "started_at": "2026-01-27T10:00:00Z",
  "finished_at": "2026-01-27T10:05:00Z",
  "duration_ms": 300000,
  "stats_json": {
    "ok": true,
    "project_id": 1,
    "domain": "frontend_prices",
    ...
  },
  "error_message": null
}
```

### 6. Проверка в UI

В UI должен отображаться:
- Статус: `success` (зеленый) или `failed` (красный)
- Время выполнения: заполнено
- Статистика: отображается (если `stats_json` заполнен)

## Отладка

### Если run остался в `running`:

1. Проверьте логи Celery worker на наличие ошибок
2. Проверьте, что worker не упал
3. Используйте `scripts/unlock_stale_runs.py` для разблокировки

### Если видите ошибку "asyncio.run() cannot be called":

Это означает, что `run_async_safe()` не сработал правильно. Проверьте:
1. Что импорт `run_async_safe` корректен
2. Что helper правильно определяет наличие event loop
3. Логи должны показывать `detected_running_loop=True/False`

### Если ingestion не выполняется:

1. Проверьте логи на наличие исключений
2. Проверьте, что `execute_ingest_job()` вызывается
3. Проверьте, что все зависимости (БД, API и т.д.) доступны

## Почему event loop может быть уже запущен?

1. **Celery с async-режимом**: Некоторые конфигурации Celery могут использовать async-режим
2. **Другие async операции**: Если в worker уже выполняются async операции
3. **Библиотеки**: Некоторые библиотеки могут создавать event loop автоматически
4. **Тестовое окружение**: В тестах может быть создан event loop

## Почему ThreadPoolExecutor безопасен для Celery prefork?

1. **Изоляция процессов**: Каждый Celery worker процесс имеет свой собственный набор потоков
2. **Новый event loop**: В новом потоке создается полностью новый event loop, изолированный от основного
3. **Блокирующий вызов**: `future.result()` блокирует до завершения, гарантируя синхронное поведение
4. **Ограниченный пул**: Используется `max_workers=1`, что минимизирует накладные расходы

## Пример успешного выполнения

```
[2026-01-27 10:00:00] INFO app.tasks.ingest.execute_ingest: Starting run 123
[2026-01-27 10:00:00] INFO app.utils.asyncio_runner: run_async_safe: detected_running_loop=False, using asyncio.run() (context: {'run_id': 123, 'job_code': 'frontend_prices'})
[2026-01-27 10:05:00] INFO app.tasks.ingest.execute_ingest: Run 123 completed successfully
```
