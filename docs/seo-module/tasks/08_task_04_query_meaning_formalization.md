# Task 04 — Query Meaning Formalization

## Title
Meaning Extraction MVP: `QueryMeaning` formalization over existing query pipeline

## Purpose
Сформировать `QueryMeaning` как явный слой поверх уже существующего query pipeline (profiles/hybrid), без переписывания pipeline и без использования product-side данных.

## Scope
Входит:
- Маппинг из `ExtractedClusterProfile` (query pipeline) в canonical `QueryMeaning`:
  - functional intent: product_type/use_cases/attributes
  - expressive intent: vibes (MVP proxy = `language_markers`)
- Стабильные правила выбора значений:
  - продуктовый тип (MVP: top selected marker / top support)
  - use_cases/attributes (списки с приоритетом)
  - vibes из language markers

Не входит:
- embeddings/semantic clustering experiment (`semantic.py`)
- matcher/scoring
- изменения в extraction logic query pipeline

## Files to touch
Create:
- `src/app/services/seo/meaning_extraction/query_meaning.py`
- `tests/test_seo_query_meaning_formalization.py`

Update:
- `src/app/services/seo/meaning_extraction/__init__.py`

## Implementation notes
- Не смешивать query-side “pipeline artifacts” и meaning types: формализация должна быть thin mapping layer.
- Expressive intent в MVP делается максимально “безопасно”:
  - если language markers отсутствуют → `vibes=[]`
- Важно: `language_markers -> vibes` помечается как **MVP proxy mapping**, а не final expressive truth.
- Важно: этот слой не должен менять существующий scoring preparation.

## Tests to run
- `pytest -q tests/test_seo_query_meaning_formalization.py`
- Regression: `pytest -q tests/test_seo_query_scoring_preparation.py`

## Expected output
- `formalize_query_meaning(profile: ExtractedClusterProfile, ...) -> QueryMeaning`
- `QueryMeaning` строится без доступа к продуктам и без новых data sources.

## Done criteria
- Формализация покрыта unit тестами.
- Regression тесты query pipeline/scoring preparation проходят.
