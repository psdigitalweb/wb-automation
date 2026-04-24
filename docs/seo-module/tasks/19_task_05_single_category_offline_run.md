# Task 19.05 — Single-Category Offline Run Path

## Purpose

Сделать controlled offline execution path для одной категории:

`reviews/titles → LLM → parse/validate → cache/persist`

Без batch и без runtime endpoint.

## Scope

Входит:
- CLI script с параметрами:
  - `--project-id`
  - `--category-id`
  - `--model` (default baseline `openai/gpt-4.1-mini`)
  - `--prompt-version`
  - `--max-reviews` (default 100)
- cache-first поведение:
  - cache hit → печать summary + выход
  - cache miss → один LLM call + persist

Не входит:
- обход всех категорий
- scheduler/orchestrator
- runtime API endpoint

## Files to touch

- create: `src/app/services/seo/expressive_llm/category_extractive_service.py`
- create: `scripts/run_category_expressive_single_category.py`

## Implementation notes

- LLM provider: `OpenRouterProvider`
- Параметры вызова:
  - `temperature=0`
  - `top_p=1`
  - `max_tokens` ограничен (по умолчанию 900)
- Логировать:
  - latency
  - cost (если присутствует в OpenRouter `usage.cost`)
  - evidence quality

## Tests to run

- `pytest -q tests/test_seo_expressive_llm_single_category_smoke.py`

## Expected output

- outputs сохранены в store root
- CLI выводит понятный summary (cache hit/miss, cost, evidence)

## Done criteria

- Один запуск категории end-to-end возможен, без изменения runtime SEO endpoints/pipelines.

