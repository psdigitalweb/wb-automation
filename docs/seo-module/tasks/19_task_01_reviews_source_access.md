# Task 19.01 — Reviews Source Access (Read-only)

## Purpose

Сделать минимальный **read-only** слой для получения review данных по категории (per `project_id × category_id`) как вход для category expressive LLM extraction.

## Scope

Входит:
- источник отзывов WB (`wb_feedback_snapshots`)
- связь review → `nm_id` → `products.subject_id` (category)
- фильтр `rating >= 4`
- сбор review текста из raw полей (`text`/`pros`/`cons`)

Не входит:
- любая запись в БД
- semantic filtering / query data
- SKU-level extraction

## Files to touch

- create: `src/app/services/seo/expressive_llm/models.py`
- create: `src/app/services/seo/expressive_llm/reviews_source.py`

## Implementation notes

- Использовать существующие источники/паттерны:
  - `src/app/db_wb_reviews.py` (как reference DAO style)
  - `docs/seo-module/15_reviews_source_discovery.md` (discovery итог)
- Возвращать **структурированный scope**:
  - `category_id`, `category_name`
  - `review_snippets[]` + `nm_ids[]` (для titles)
  - counts (сколько отобрано / сколько всего)
- Текст нормализовать только технически:
  - trim
  - (truncate/dedup будет в Task 19.02)

## Tests to run

- `pytest -q tests/test_seo_expressive_llm_reviews_source_selection.py`

## Expected output

- Python API:
  - `fetch_category_review_scope(session, project_id, category_id, min_rating=4) -> CategoryReviewScope`
  - `CategoryReviewScope.review_snippets` содержит `nm_id`, `rating`, `text_parts_combined`

## Done criteria

- Реальный fetch layer существует, read-only, и возвращает детерминированный scope для builder.

