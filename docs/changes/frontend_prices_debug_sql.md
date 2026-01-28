# Frontend prices: debug SQL smoke commands

> Эти команды помогают быстро понять: есть ли `ingest_runs`, корректен ли `job_code`, и связываются ли строки через `ingest_run_id`.

## A) Последние ingest_runs по project_id и job_code

```sql
SELECT
  id,
  project_id,
  marketplace_code,
  job_code,
  status,
  started_at,
  finished_at,
  created_at,
  stats_json,
  params_json
FROM ingest_runs
WHERE project_id = 1
ORDER BY started_at DESC NULLS LAST, created_at DESC
LIMIT 30;
```

Узкий фильтр под витринные цены:

```sql
SELECT
  id,
  project_id,
  marketplace_code,
  job_code,
  status,
  started_at,
  finished_at,
  created_at,
  stats_json,
  params_json
FROM ingest_runs
WHERE project_id = 1
  AND marketplace_code = 'wildberries'
  AND job_code IN ('frontend_prices', 'frontend-prices')
ORDER BY started_at DESC NULLS LAST, created_at DESC
LIMIT 30;
```

## B) Rows total vs rows linked (ingest_run_id is not null)

```sql
SELECT
  COUNT(*) AS rows_total,
  COUNT(*) FILTER (WHERE ingest_run_id IS NOT NULL) AS rows_linked,
  COUNT(*) FILTER (WHERE ingest_run_id IS NULL) AS rows_unlinked
FROM frontend_catalog_price_snapshots;
```

## C) Count(*) по конкретному run_id

```sql
SELECT COUNT(*) AS rows_for_run
FROM frontend_catalog_price_snapshots
WHERE ingest_run_id = 12345; -- подставить run_id
```

Дополнительно: список top run_id по количеству строк:

```sql
SELECT ingest_run_id, COUNT(*) AS rows_for_run
FROM frontend_catalog_price_snapshots
WHERE ingest_run_id IS NOT NULL
GROUP BY ingest_run_id
ORDER BY rows_for_run DESC
LIMIT 20;
```

