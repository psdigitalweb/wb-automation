-- SQL script to manually unlock a stale running ingest_run
-- Usage: Replace project_id, marketplace_code, job_code with actual values
-- Example: Unlock stale run for project_id=1, marketplace='wildberries', job_code='frontend_prices'

-- Option 1: Unlock specific run by ID (if you know the run_id)
UPDATE ingest_runs
SET status = 'failed',
    finished_at = now(),
    duration_ms = CASE
        WHEN started_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (now() - started_at)) * 1000::bigint
        ELSE NULL
    END,
    error_message = 'Stale run unlocked manually (was stuck in running state)',
    error_trace = 'Unlocked manually via SQL script',
    stats_json = '{"ok": false, "reason": "stale_run_unlocked"}'::jsonb,
    updated_at = now()
WHERE id = :run_id AND status = 'running';

-- Option 2: Unlock all stale runs for specific (project_id, marketplace_code, job_code)
-- Replace values below with actual ones
UPDATE ingest_runs
SET status = 'failed',
    finished_at = now(),
    duration_ms = CASE
        WHEN started_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (now() - started_at)) * 1000::bigint
        ELSE NULL
    END,
    error_message = 'Stale run unlocked manually (was stuck in running state)',
    error_trace = 'Unlocked manually via SQL script',
    stats_json = '{"ok": false, "reason": "stale_run_unlocked"}'::jsonb,
    updated_at = now()
WHERE project_id = 1
  AND marketplace_code = 'wildberries'
  AND job_code = 'frontend_prices'
  AND status = 'running'
  AND updated_at < now() - interval '30 minutes';

-- Option 3: Find all stale runs first (to see what will be unlocked)
SELECT 
    id,
    project_id,
    marketplace_code,
    job_code,
    started_at,
    updated_at,
    EXTRACT(EPOCH FROM (now() - updated_at)) / 60 AS age_minutes
FROM ingest_runs
WHERE status = 'running'
  AND updated_at < now() - interval '30 minutes'
ORDER BY updated_at ASC;
