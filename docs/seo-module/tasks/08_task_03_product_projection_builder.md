# Task 03 — Product Projection Builder

## Title
Meaning Extraction MVP: `ProductProjection` builder (SKU → category meaning space)

## Purpose
Построить `ProductProjection` для конкретного SKU на основе SKU evidence + `CategoryMeaning`, включая cold-start expressive baseline.

## Scope
Входит:
- SQL чтение SKU evidence (те же confirmed поля, что уже используются в scoring preparation):
  - `title`, `description`, `characteristics`, `sizes`, `colors`, `dimensions`, `subject_id`
- Functional profile:
  - deterministic extraction из attributes/title/description (weak)
  - нормализация относительно `CategoryMeaning` axes (MVP: “best-effort” match)
- Expressive profile:
  - baseline = `CategoryMeaning.expressive` prior
  - SKU signals из `title/description` (MVP)
  - merge: слабый сигнал → prior; сильный → уточнение/override (правило зафиксировать)

Не входит:
- Reviews enrichment как активный источник.
- Matcher/scoring.

## Files to touch
Create:
- `src/app/services/seo/meaning_extraction/product_projection.py`
- `tests/test_seo_product_projection_builder.py`

Update:
- `src/app/services/seo/meaning_extraction/__init__.py`

## Implementation notes
- Cold-start обязателен: пустой SKU expressive не ломает `ProductProjection`.
- Не расширять product inputs beyond confirmed ones.
- Сохранить explainability: минимум — признаки того, что expressive пришёл из prior vs из SKU (можно как поле/flag/diagnostics).

MVP rule: weak vs strong SKU expressive signal
- Expressive candidates извлекаются только из `title` и `description` (description = weak source).
- `strong_expressive_signal = True`, если выполняется хотя бы одно:
  1) найдены ≥ 2 expressive candidates в `title`, или
  2) найден ≥ 1 candidate в `title`, который пересекается с `CategoryMeaning.expressive.vibes`, или
  3) найдены ≥ 3 candidates суммарно (title+description) и хотя бы 1 из них из `title`.
- Иначе сигнал считается weak:
  - `expressive.vibes` берём baseline из `CategoryMeaning.expressive.vibes`
  - SKU candidates не применяем как override (можно только как diagnostics)

## Tests to run
- `pytest -q tests/test_seo_product_projection_builder.py`

## Expected output
- `build_product_projection(session, project_id, category_id, nm_id, category_meaning=...) -> ProductProjection`
- Фиксируется, что expressive baseline применяется при слабых SKU сигналах.

## Done criteria
- Projection строится детерминированно и деградирует корректно при пустых полях.
- Тесты `tests/test_seo_product_projection_builder.py` проходят.
