# Task 06 — Tests / Regression / Cleanup

## Title
Meaning Extraction MVP: test coverage + regression safety

## Purpose
Закрыть MVP по тестам и убедиться, что существующий query pipeline/runtime не сломан.

## Scope
Входит:
- Доведение тестов для всех 3 сущностей.
- Regression suite (минимум) на существующие SEO тесты, которые затрагивают query pipeline и scoring preparation.
- Минимальный cleanup:
  - убрать dead code paths в meaning extraction (если появятся в ходе реализации)
  - стабилизировать сериализацию и debug payload

Не входит:
- Любые изменения в scoring logic (кроме исправления тестов, если meaning extraction случайно затронул импорт/экспорт).
- Миграции.

## Files to touch
Update:
- Новые тесты из Tasks 01–05 (по необходимости).
- (опционально) `tests/seo_query_pipeline_test_helpers.py` (только additive helpers)

## Implementation notes
- В конце каждой задачи фиксировать:
  - exact test commands
  - exact results (сколько passed/failed)
  - runtime/debug effect
- Regression target: query pipeline и scoring preparation не должны менять поведение.

## Tests to run
Минимальный набор:
- `pytest -q tests/test_seo_meaning_types.py`
- `pytest -q tests/test_seo_category_meaning_builder.py`
- `pytest -q tests/test_seo_product_projection_builder.py`
- `pytest -q tests/test_seo_query_meaning_formalization.py`
- `pytest -q tests/test_seo_meaning_extraction_debug_api.py`

Regression:
- `pytest -q tests/test_seo_query_import_api.py`
- `pytest -q tests/test_seo_query_pipeline_debug_api.py`
- `pytest -q tests/test_seo_query_scoring_preparation.py`

## Expected output
- Полный Meaning Extraction MVP доступен через structured objects + debug endpoint.
- Существующий query pipeline не сломан.

## Done criteria
- Все новые тесты проходят.
- Выбранный regression набор проходит.
- Есть понятный “последний” отчёт о runtime/debug эффекте (через Task 05 endpoint).

