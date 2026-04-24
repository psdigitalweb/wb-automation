# Task 05 — Debug / Runtime Exposure

## Title
Meaning Extraction MVP: debug endpoint for CategoryMeaning / ProductProjection / QueryMeaning

## Purpose
Дать контролируемую видимость результата meaning extraction в runtime без вмешательства в scoring/matcher.

## Scope
Входит:
- Debug API (предпочтительно отдельный router) для получения:
  - `category_meaning` (project_id, category_id)
  - `product_projection` (project_id, category_id, nm_id)
  - `query_meaning` (ровно один, по `cluster_key` или иному явному target)
  - минимальные flags (например: `weak_expressive_signal`, `used_category_prior`)

Не входит:
- UI.
- Переписывание существующего `seo_query_pipeline_debug` (в идеале только re-use нужных сервисов).
- Matcher/scoring.

## Files to touch
Create:
- `src/app/routers/seo_meaning_extraction_debug.py`
- `src/app/schemas/seo_meaning_extraction_debug.py`
- `tests/test_seo_meaning_extraction_debug_api.py`

Update (если требуется для регистрации роутера):
- `src/app/main.py` (или место, где подключаются роутеры)

## Implementation notes
- Re-use существующие подходы:
  - dependency `allow_local_debug_read`
  - session injection через `SessionLocal` override в тестах
- Endpoint должен быть безопасен:
  - deterministic
  - не требует новых источников данных
  - не использует embeddings/LLM

## Tests to run
- `pytest -q tests/test_seo_meaning_extraction_debug_api.py`

## Expected output
- Новый endpoint возвращает payload для 3 сущностей в JSON-friendly форме.

## Done criteria
- Endpoint работает в тестах (FastAPI TestClient).
- Payload содержит `category_meaning`, `product_projection`, `query_meanings`.
- Нет регрессии существующих debug API и scoring preparation тестов.
