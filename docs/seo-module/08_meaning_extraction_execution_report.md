# Meaning Extraction MVP — Execution Report (Tasks 01–06)

Дата: 2026-04-20

Этот документ фиксирует, что именно было реализовано по плану Meaning Extraction MVP, какими шагами, какими тест-командами проверено, и какой runtime/debug эффект появился.

---

## 0) Boundaries (что НЕ делали)

В рамках этих задач **не делали**:
- matcher
- scoring redesign / переписывание scoring preparation
- generation / providers (включая OpenRouter)
- LLM / embeddings / semantic retrieval
- reviews-first логика, manual overrides, UI
- research/spike как основной путь

---

## 1) Deliverables (что появилось)

### 1.1 Canonical entities (явные сущности)

Добавлены 3 явные сущности Meaning Extraction MVP:
- `CategoryMeaning` (per project × category)
- `ProductProjection` (per project × SKU)
- `QueryMeaning` (per project × category × cluster_key)

### 1.2 Builders / formalization

Добавлены детерминированные builder’ы:
- `build_category_meaning(session, project_id, category_id, thresholds=...)`
- `build_product_projection(session, project_id, category_id, nm_id, category_meaning=...)`
- `formalize_query_meaning(profile, project_id, category_id, ...)`

### 1.3 Runtime visibility

Добавлен минимальный debug endpoint (ровно 3 meaning objects + минимальные flags):
- `GET /api/v1/projects/{project_id}/seo/meaning-extraction/debug?category_id=...&nm_id=...&cluster_key=...`

---

## 2) Task 01 — Meaning result types / canonical objects

### Что сделано
- Введены canonical dataclass types:
  - `CategoryMeaning`, `ProductProjection`, `QueryMeaning`
  - functional/expressive подтипы
- Добавлен `to_dict()` для JSON-like сериализации и `version="v1_mvp"`.

### Файлы
- Create: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `src/app/services/seo/meaning_extraction/types.py`
- Create: `tests/test_seo_meaning_types.py`

### Tests
Команда:
- ` $env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_meaning_types.py `

Результат:
- `4 passed in 0.85s`

### Runtime/debug эффект
- Нет (только types + unit tests).

---

## 3) Task 02 — Category Meaning builder (product-side aggregation)

### Что сделано
- Реализован `build_category_meaning(...) -> CategoryMeaning` по `products` (scope через `subject_id`).
- Используются только подтверждённые поля: `title`, `description`, `characteristics`, `sizes`, `colors`, `dimensions`.
- Зафиксированы и реализованы deterministic thresholds “повторяющихся паттернов” (presence-based):
  - default: `support_sku_count >= 3` и `support_share >= 0.15`
  - small category (`total_sku_count < 20`): `support_sku_count >= 2` и `support_share >= 0.25`
  - top_k лимиты: product_types/use_cases/vibes=20, attributes=40
- Expressive vibes в MVP извлекаются только через deterministic whitelist токены (без LLM/embeddings).

### Файлы
- Create: `src/app/services/seo/meaning_extraction/category_meaning.py`
- Update: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `tests/test_seo_category_meaning_builder.py`

### Tests
Команды:
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_category_meaning_builder.py`
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_meaning_types.py tests\test_seo_query_scoring_preparation.py`

Результаты:
- `2 passed, 8 warnings in 1.05s`
- `7 passed, 73 warnings in 0.70s`

### Runtime/debug эффект
- Нет (builder + unit tests).

---

## 4) Task 03 — Product Projection builder (SKU → category space)

### Что сделано
- Реализован `build_product_projection(...) -> (ProductProjection, ProductProjectionBuildFlags)`:
  - functional extraction (MVP) из title/description/attributes
  - expressive extraction (MVP) через whitelist vibes + rule weak/strong
- Rule weak vs strong SKU expressive signal реализован как было зафиксировано:
  - weak → `expressive.vibes = CategoryMeaning.expressive.vibes` (baseline)
  - strong → SKU vibes применяются (SKU-first ordering) + category prior остаётся baseline
- Добавлены минимальные flags для debug:
  - `weak_expressive_signal`, `strong_expressive_signal`, `used_category_prior`, `applied_sku_vibes`

### Файлы
- Create: `src/app/services/seo/meaning_extraction/product_projection.py`
- Update: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `tests/test_seo_product_projection_builder.py`

### Tests
Команды:
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_product_projection_builder.py`
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_category_meaning_builder.py tests\test_seo_product_projection_builder.py tests\test_seo_query_scoring_preparation.py`

Результаты:
- `2 passed, 8 warnings in 0.77s`
- `7 passed, 89 warnings in 0.83s`

### Runtime/debug эффект
- Нет (builder + flags + unit tests).

---

## 5) Task 04 — Query Meaning formalization (поверх query pipeline)

### Что сделано
- Реализован thin mapping `formalize_query_meaning(...) -> (QueryMeaning, QueryMeaningBuildFlags)` поверх `ExtractedClusterProfile`.
- Явно отмечено, что `language_markers -> vibes` — **MVP proxy mapping**, не final expressive truth.
- Никаких изменений в query pipeline extraction (ingestion/pruning/clustering/hybrid/profiles) не делалось.

### Файлы
- Create: `src/app/services/seo/meaning_extraction/query_meaning.py`
- Update: `src/app/services/seo/meaning_extraction/__init__.py`
- Create: `tests/test_seo_query_meaning_formalization.py`

### Tests
Команды:
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_query_meaning_formalization.py`
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_query_scoring_preparation.py tests\test_seo_query_pipeline_debug_api.py`

Результаты:
- `2 passed in 0.46s`
- `8 passed, 195 warnings in 2.18s`

### Runtime/debug эффект
- Нет (formalization + unit tests).

---

## 6) Task 05 — Debug/runtime exposure (минимальный endpoint)

### Что сделано
- Добавлен минимальный debug endpoint, который возвращает:
  - `category_meaning`
  - `product_projection`
  - `query_meaning` (ровно один, по `cluster_key`)
  - `product_projection_flags` + `query_meaning_flags`
- Endpoint намеренно не раздувался (без пагинаций/списков/diagnostics summary).

### Файлы
- Create: `src/app/routers/seo_meaning_extraction_debug.py`
- Create: `src/app/schemas/seo_meaning_extraction_debug.py`
- Update: `src/app/main.py` (router registration)
- Create: `tests/test_seo_meaning_extraction_debug_api.py`

### Tests
Команды:
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_meaning_extraction_debug_api.py`
- `$env:PYTHONPATH='src'; pytest -q -p no:cacheprovider tests\test_seo_query_pipeline_debug_api.py tests\test_seo_query_scoring_preparation.py tests\test_seo_category_meaning_builder.py tests\test_seo_product_projection_builder.py tests\test_seo_query_meaning_formalization.py tests\test_seo_meaning_extraction_debug_api.py`

Результаты:
- `2 passed, 30 warnings in 1.11s`
- `16 passed, 239 warnings in 1.57s`

### Новый runtime/debug эффект
Endpoint:
- `GET /api/v1/projects/{project_id}/seo/meaning-extraction/debug?category_id=...&nm_id=...&cluster_key=...`

Payload keys:
- `category_meaning`, `product_projection`, `query_meaning`, `product_projection_flags`, `query_meaning_flags`

---

## 7) Task 06 — Tests / regression / cleanup

### Что сделано
- Исправлен test harness для sandbox-окружения:
  - `app` импортируется без `PYTHONPATH=src` (через `tests/conftest.py`).
  - pytest cache отключён глобально (из-за permission issues).
  - `tmp_path` заменён на workspace-local реализацию, чтобы `test_seo_query_import_api.py` не падал на temp-root permission.
  - добавлен ignore для временных директорий в `.gitignore` и `pytest.ini:norecursedirs`.

### Файлы
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Create: `tests/_runtime_tmp/.keep`
- Update: `.gitignore`

### Tests (MVP set)
Команда:
- `pytest -q tests\test_seo_meaning_types.py tests\test_seo_category_meaning_builder.py tests\test_seo_product_projection_builder.py tests\test_seo_query_meaning_formalization.py tests\test_seo_meaning_extraction_debug_api.py`

Результат:
- `12 passed, 46 warnings in 1.15s`

### Tests (Regression set)
Команда:
- `pytest -q tests\test_seo_query_import_api.py tests\test_seo_query_pipeline_debug_api.py tests\test_seo_query_scoring_preparation.py`

Результат:
- `15 passed, 195 warnings in 1.77s`

Дополнительно:
- `pytest -q tests\test_seo_query_ingestion.py`
- `6 passed in 0.55s`

---

## 8) What’s intentionally deferred (следующие шаги, но не в MVP)

- DB persistence/versioning для meaning объектов (миграции + жизненный цикл версий).
- Reviews enrichment (как optional усиление expressive, не core).
- SKU clustering как downstream слой (placeholder уже есть; не трогали).
- Matcher и интеграция meaning layers в scoring.
- Manual overrides.

