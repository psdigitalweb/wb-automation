# Task 19.06 — Tests / Regression / Cleanup

## Purpose

Закрыть тестами новые компоненты LLM expressive category layer и убедиться, что существующий SEO runtime не сломан.

## Scope

Входит:
- unit tests:
  - reviews selection helpers
  - input builder
  - parser/validation + evidence exact-match
  - storage key stability
- smoke test offline path (без реальных LLM вызовов)
- regression прогон существующих SEO тестов

Не входит:
- performance optimizations
- любые изменения scoring/query pipeline

## Files to touch

- create: `tests/test_seo_expressive_llm_reviews_source_selection.py`
- create: `tests/test_seo_expressive_llm_category_input_builder.py`
- create: `tests/test_seo_expressive_llm_category_output_parser.py`
- create: `tests/test_seo_expressive_llm_storage_key.py`
- create: `tests/test_seo_expressive_llm_single_category_smoke.py`
- optional: `tests/fixtures/expressive_llm/category_response_*.json`

## Tests to run

Focused:
- `pytest -q tests/test_seo_expressive_llm_reviews_source_selection.py`
- `pytest -q tests/test_seo_expressive_llm_category_input_builder.py`
- `pytest -q tests/test_seo_expressive_llm_category_output_parser.py`
- `pytest -q tests/test_seo_expressive_llm_storage_key.py`
- `pytest -q tests/test_seo_expressive_llm_single_category_smoke.py`

Regression:
- `pytest -q tests/test_seo_meaning_types.py`
- `pytest -q tests/test_seo_category_meaning_builder.py`
- `pytest -q tests/test_seo_meaning_extraction_debug_api.py`

## Expected output

- понятный, повторяемый test report (какие тесты, сколько прошло)

## Done criteria

- новые тесты зелёные
- регрессионные SEO тесты зелёные
- offline runner не требует реального LLM в тестах

