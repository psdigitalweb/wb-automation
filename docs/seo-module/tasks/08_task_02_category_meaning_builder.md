# Task 02 — Category Meaning Builder

## Title
Meaning Extraction MVP: `CategoryMeaning` builder (product-side aggregation)

## Purpose
Реализовать детерминированное построение `CategoryMeaning` из продуктовых данных категории (per project × category) без dependency на reviews/LLM/embeddings.

## Scope
Входит:
- SQL чтение товаров в scope `project_id × category_id` (где `category_id` = WB `subject_id`).
- Извлечение функциональных и expressive сигналов из подтверждённых runtime inputs:
  - `title`, `description`, `characteristics`, `sizes`, `colors`, `dimensions`
- Агрегация по множеству SKU с фильтрацией выбросов (MVP-правило: фиксируем повторяющиеся паттерны).
- Результат как `CategoryMeaning` canonical object.

MVP thresholds (минимальные deterministic пороги “повторяющихся паттернов”):
- `support_sku_count` = число SKU, где паттерн встречается (presence-based).
- `support_share` = `support_sku_count / total_sku_count`.
- Базовый порог: `support_sku_count >= 3` и `support_share >= 0.15`.
- Для `total_sku_count < 20`: `support_sku_count >= 2` и `support_share >= 0.25`.
- Лимиты вывода: `top_k=20` для product_types/use_cases/vibes; `top_k=40` для attributes (если нужно).

Не входит:
- Reviews как обязательный источник.
- SKU clustering.
- Matcher / scoring / scoring preparation изменения.

## Files to touch
Create:
- `src/app/services/seo/meaning_extraction/category_meaning.py`
- `tests/test_seo_category_meaning_builder.py`

Update:
- `src/app/services/seo/meaning_extraction/__init__.py` (экспорт builder)

Optional (additive only):
- `tests/seo_query_pipeline_test_helpers.py` (helper для seed products, если удобнее)

## Implementation notes
- Явно зафиксировать “active inputs” и не тянуть поля, которые не подтверждены call sites.
- Нормализация текста: можно использовать существующую `normalize_query_text` (как детерминированную normalization функцию), но не смешивать query-side статистику.
- Degradation rules:
  - без reviews слой валиден
  - пустые поля не ломают builder
- Должна быть explainable структура: хотя бы минимальные diagnostics (например, counts / thresholds) — либо в debug endpoint (Task 05), либо внутри builder (без влияния на runtime).

## Tests to run
- `pytest -q tests/test_seo_category_meaning_builder.py`

## Expected output
- `build_category_meaning(session, project_id, category_id, ...) -> CategoryMeaning`
- В output присутствуют `functional` и `expressive` части (даже если пустые).

## Done criteria
- Builder детерминированный и даёт стабильный результат на тестовых данных.
- Не использует неподтверждённые product fields.
- Тесты `tests/test_seo_category_meaning_builder.py` проходят.
