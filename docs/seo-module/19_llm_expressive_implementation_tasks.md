# SEO Module — LLM Expressive Layer (Category) — Implementation Tasks (Iteration 19)

## 0. Purpose

Подготовить **контролируемую** первую итерацию LLM-backed expressive layer для **product-side**:

- только **Category expressive extraction** через LLM
- input строится из **reviews (primary)** + **titles (secondary)**
- результаты **кэшируются / сохраняются** (persistence) и используются только **offline / precompute**

При этом:
- не менять архитектуру SEO-модуля
- не добавлять runtime hot-path dependency на LLM
- не лезть в matcher / scoring / query pipeline / generation / UI

---

## A. Scope итерации

### A1. Что входит

1) **Reviews source access (read-only)**
- найти и формализовать read-layer для получения review snippets по `(project_id, category_id)`
- rating filter: `rating >= 4`
- сохранить связь review → `nm_id` (для выбора titles)

2) **Category LLM input builder**
- собрать payload:
  - `category_name`
  - `reviews[]` (primary)
  - `titles[]` (secondary, optional)
- правила нормализации:
  - trim
  - truncate (reviews ≤ 220 chars, titles ≤ 120 chars)
  - dedup по нормализованному тексту
  - up to 100 reviews
  - короткие отзывы не выкидывать

3) **LLM response parser + validation**
- строгий JSON parse
- `vibes[]` shape validation
- `evidence_spans`:
  - 2–3 на vibe (строго)
  - ≤ 80 chars, без переносов строк
  - **exact-substring match** во входных evidence текстах (MVP: по reviews; titles только контекст)

4) **Storage / cache (persistence)**
- key:
  - `project_id`
  - `category_id`
  - `model`
  - `prompt_version`
  - `input_hash`
- сохранять:
  - raw response (audit)
  - parsed normalized JSON
  - validation report (evidence quality / hallucinations)

5) **Offline single-category run path**
- controlled run только для одной категории (не batch по проекту)
- CLI-script, который:
  - собирает input
  - проверяет cache hit
  - делает один LLM call (если cache miss)
  - валидирует и сохраняет артефакты

6) **Tests / regression**
- unit тесты на builder / parser / validation / cache key stability
- smoke test offline-run path **без реального LLM** (через фикстурный raw_response)
- regression: существующий Meaning Extraction MVP и SEO тесты не ломаются от новых модулей/импортов

### A2. Что НЕ входит (явно)

- SKU expressive LLM extraction
- ProductProjection integration
- Query expressive via LLM
- runtime endpoint / синхронные runtime вызовы LLM
- matcher / scoring / generation / UI
- full batch orchestration по всем категориям
- DB migrations (если можно избежать) — в этой итерации выбираем file-based persistence

---

## B. Source of truth

### B1. Docs (обязательные)

- `docs/seo-module/01_architecture.md`
- `docs/seo-module/03_category_meaning_spec.md`
- `docs/seo-module/04_product_projection_spec.md`
- `docs/seo-module/SEO Module — Expressive LLM Integration Spec.md` (актуальный файл вместо `17_expressive_llm_integration_spec.md`)
- `docs/seo-module/18_llm_expressive_implementation_plan.md`

### B2. Runtime/Repo code reviewed (relevant)

- Reviews / DB access:
  - `src/app/db_wb_reviews.py`
  - `scripts/export_in_stock_product_reviews.py`
  - `docs/seo-module/15_reviews_source_discovery.md` (итог discovery)
- Meaning Extraction MVP types/builders:
  - `src/app/services/seo/meaning_extraction/types.py`
  - `src/app/services/seo/meaning_extraction/category_meaning.py`
- LLM provider abstraction:
  - `src/app/services/seo/providers/base.py`
  - `src/app/services/seo/providers/openrouter.py`
- Offline spike tooling (как reference для guards/caching подхода, НЕ как production path):
  - `scripts/expressive_llm_eval.py`
  - `scripts/prepare_category_expressive_input_preview.py`
  - `scripts/run_category_expressive_once.py`
- Tests (existing patterns):
  - `tests/test_expressive_llm_eval_evidence_validation.py`
  - `tests/test_seo_category_meaning_builder.py`
  - `tests/test_seo_meaning_extraction_debug_api.py`

---

## C. Decomposition (implementation subtasks)

Минимальная декомпозиция (фиксируется как Task 01..06):

- Task 01 — reviews source access
- Task 02 — category LLM input builder
- Task 03 — LLM response parser + validation
- Task 04 — expressive storage/cache
- Task 05 — single category offline run path
- Task 06 — tests / regression / cleanup

---

## D. Details per task

### Task 01 — Reviews source access

**Goal**
- Реализовать read-only слой получения данных для категории:
  - category_name
  - reviews (rating>=4)
  - nm_ids из scope (для titles)

**Files to touch**
- create: `src/app/services/seo/expressive_llm/reviews_source.py`
- create: `src/app/services/seo/expressive_llm/models.py` (dataclasses для review/title snippets)

**Expected runtime output**
- Python API: `fetch_category_review_snippets(project_id, category_id, limit=...) -> CategoryReviewScope`
- `CategoryReviewScope` содержит counts + `review_snippets[]` + `nm_ids[]`

**Test/checkpoint**
- unit tests на:
  - rating filter
  - сбор review text из raw (`text/pros/cons`)
  - technical normalization (trim)

**Done criteria**
- есть стабильная функция fetch (read-only), которую можно использовать в builder

---

### Task 02 — Category LLM input builder

**Goal**
- Собрать LLM input payload для category expressive extraction:
  - reviews primary, titles secondary
- Реализовать deterministic normalization:
  - truncate / dedup / limit

**Files to touch**
- create: `src/app/services/seo/expressive_llm/category_input_builder.py`
- create: `src/app/services/seo/expressive_llm/text_normalization.py`

**Expected runtime output**
- `build_category_expressive_input(...) -> CategoryExpressiveInput`
  - `payload` (JSON-serializable)
  - `evidence_text` (string, used for exact-span validation)
  - `input_hash` (sha256 of canonical payload)

**Test/checkpoint**
- unit tests:
  - dedup correctness
  - truncate limits (reviews 220, titles 120)
  - up-to-100 reviews cap
  - titles inclusion is optional but full dedupbed scope (не “5–10”)

**Done criteria**
- builder produces stable payload + stable input_hash

---

### Task 03 — LLM response parser + validation

**Goal**
- Превратить raw LLM response content в нормализованный объект + validation report
- Hard validation:
  - strict JSON object
  - vibes list max 5
  - evidence_spans: 2–3, <=80 chars, no newlines
  - evidence spans **must appear as substrings** in evidence_text

**Files to touch**
- create: `src/app/services/seo/expressive_llm/category_output_parser.py`
- create: `src/app/services/seo/expressive_llm/validation.py`

**Expected runtime output**
- `parse_category_expressive_output(content, evidence_text, ...) -> ParsedCategoryExpressiveResult`
  - `parsed` (normalized JSON)
  - `validation` (hallucinations, evidence quality)

**Test/checkpoint**
- unit tests:
  - invalid JSON → error
  - missing spans → hallucination flags
  - wrong evidence_spans count / too long / newline → invalid

**Done criteria**
- parser/validator deterministic and test-covered

---

### Task 04 — Expressive storage/cache

**Goal**
- File-based persistence (no DB migrations in iteration 19)
- Cache key:
  - project_id, category_id, model, prompt_version, input_hash

**Files to touch**
- create: `src/app/services/seo/expressive_llm/storage.py`

**Expected runtime output**
- `CategoryExpressiveStore`:
  - `get(...) -> Optional[StoredArtifact]`
  - `put(...) -> StoredArtifact`
  - writes:
    - `raw_response.json`
    - `parsed.json`
    - `validation.json`
    - `meta.json` (key + timestamps)

**Test/checkpoint**
- unit tests:
  - key stability
  - path layout stability
  - cache hit behavior (no overwrite by default)

**Done criteria**
- artifacts persist and are reproducible via key

---

### Task 05 — Single category offline run path

**Goal**
- Controlled single-category execution (no batch):
  - fetch reviews
  - build input
  - cache check
  - one LLM call (OpenRouter provider) on cache miss
  - parse + validate
  - store artifacts

**Files to touch**
- create: `src/app/services/seo/expressive_llm/category_extractive_service.py`
- create: `scripts/run_category_expressive_single_category.py`

**Expected runtime output**
- CLI prints:
  - selected category info
  - cache hit/miss
  - latency/cost if available
  - evidence quality summary
- writes outputs into INTERNAL_DATA_DIR-backed store

**Test/checkpoint**
- smoke test without LLM:
  - feed fixture content into parser and store output

**Done criteria**
- single category can be processed end-to-end offline with caching

---

### Task 06 — Tests / regression / cleanup

**Goal**
- Add missing tests + run regression suite locally

**Files to touch**
- create: `tests/test_seo_expressive_llm_category_input_builder.py`
- create: `tests/test_seo_expressive_llm_category_output_parser.py`
- create: `tests/test_seo_expressive_llm_storage_key.py`
- optional: `tests/fixtures/expressive_llm/…` (sample raw_response/parsed)

**Expected runtime output**
- `pytest` green on:
  - new unit tests
  - existing SEO meaning extraction tests

**Done criteria**
- tests cover: fetching/selection logic, builder, parser+validation, storage key stability, offline run smoke path

---

## E. Execution order

1) Task 01 (reviews source) → нужен для builder
2) Task 02 (input builder) → нужен до LLM call + caching
3) Task 03 (parser/validation) → нужен до storage
4) Task 04 (storage/cache) → нужен до offline run
5) Task 05 (single category runner) → собирает end-to-end
6) Task 06 (tests/regression/cleanup) → стабилизация

Dependencies:
- Task 05 depends on Task 01–04
- Task 06 depends on all (добавляет coverage + регресс)

---

## F. Risks / boundaries

### F1. Boundaries (куда нельзя лезть)
- `src/app/services/seo/query_pipeline/**` — не трогать
- `src/app/services/seo/scoring/**` — не трогать
- `src/app/services/seo/clustering/**` — не трогать
- matcher/generation — не внедрять
- не добавлять runtime endpoint, который вызывает LLM синхронно

### F2. Known risks
- Reviews coverage может быть неравномерной по категориям (не блокирует: fallback empty expressive OK)
- Evidence exact-match очень строгий: модели могут “нормализовать” цитаты (это должен ловить validator)
- Без DB migrations persistence остаётся file-based; интеграция в runtime будет отдельной итерацией

