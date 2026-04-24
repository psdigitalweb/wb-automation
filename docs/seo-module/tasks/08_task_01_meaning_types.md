# Task 01 — Meaning Result Types / Canonical Objects

## Title
Meaning Extraction MVP: canonical result types (`CategoryMeaning`, `ProductProjection`, `QueryMeaning`)

## Purpose
Ввести 3 явные сущности Meaning Extraction MVP как стабильные structured объекты, совместимые с архитектурой и пригодные для debug/runtime экспозиции.

## Scope
Входит:
- Определение canonical shape для:
  - `CategoryMeaning` (functional + expressive)
  - `ProductProjection` (functional + expressive)
  - `QueryMeaning` (functional + expressive)
- Версионирование (минимум `version` поле/строка) и сериализация (`to_dict()`).
- Минимальные вспомогательные типы: `FunctionalMeaning`, `ExpressiveMeaning`, value-items (если нужно).

Не входит:
- Любая логика extraction/matching/scoring.
- DB persistence / migrations.
- Использование LLM/embeddings.

## Files to touch
Create:
- `src/app/services/seo/meaning_extraction/__init__.py`
- `src/app/services/seo/meaning_extraction/types.py`
- `tests/test_seo_meaning_types.py`

Optional (только если потребуется для debug API позже):
- `src/app/schemas/seo_meaning_extraction_debug.py`

## Implementation notes
- Держать shape близко к docs:
  - `functional.product_types/use_cases/attributes`
  - `expressive.vibes`
- Сериализация должна быть стабильной и “json-like”.
- Не переиспользовать существующие SEO “diagnostics dataclasses” как types, чтобы не смешивать pipeline артефакты и meaning layer.
- Никаких зависимостей на `sentence_transformers`, OpenRouter и т.п.

## Tests to run
- `pytest -q tests/test_seo_meaning_types.py`

## Expected output
- Импортируемые canonical types в `app.services.seo.meaning_extraction`.
- Юнит-тесты подтверждают:
  - shape
  - сериализацию
  - наличие functional/expressive слоёв (даже если пустые списки)

## Done criteria
- Типы доступны для импортов.
- `to_dict()` возвращает JSON-совместимый payload.
- Тесты `tests/test_seo_meaning_types.py` проходят.

