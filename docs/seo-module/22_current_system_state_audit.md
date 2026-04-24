# Current System State Audit — LLM Expressive + Meaning Extraction

Date: 2026-04-21  
Scope: audit-only (code + existing artifacts). No architecture changes, no new LLM calls.

## 1. CategoryMeaning

### Where implemented
- Builder: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\category_meaning.py` (`build_category_meaning`)
- Canonical types: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\types.py` (`CategoryMeaning`, `CategoryFunctionalMeaning`, `CategoryExpressiveMeaning`)

### Fields (current runtime shape)
`CategoryMeaning` fields (JSON via `.to_dict()`):
- `project_id: int`
- `category_id: int`
- `version: "v1_mvp"`
- `functional`:
  - `product_types: string[]`
  - `use_cases: string[]`
  - `attributes: string[]`
- `expressive`:
  - `vibes: string[]`
  - `llm: object|null` (present in dataclass; omitted in older debug outputs when empty)

### Expressive: exists? where it comes from?
Implemented and wired (cache-only):
- Functional extraction: deterministic, from `products` evidence fields (title/description/characteristics/sizes/colors/dimensions) in `build_category_meaning`. No reviews/LLM here.
- Expressive extraction: **loaded from LLM cache** (offline/precompute artifacts) via `_load_llm_expressive_from_cache(...)` inside `build_category_meaning`.

No deterministic expressive aggregation is currently used in `CategoryMeaning` (the variable `_vibes_by_sku` is collected but not included in the returned object).

### Cache hit logic (CategoryMeaning expressive)
`_load_llm_expressive_from_cache(...)` does:
1) Fetches review scope from DB: `fetch_category_review_scope(...)` (min_rating=4, limit=5000).
2) Fetches titles for nm_ids (same scope).
3) Builds deterministic category LLM input using `build_category_expressive_input(...)` with:
   - `max_reviews=100`
   - reviews primary
   - titles secondary
4) Computes cache key:
   - `project_id`, `category_id`
   - `model = settings.OPENROUTER_CHAT_MODEL` (default `"openai/gpt-4.1-mini"`)
   - `prompt_version = "v1"` (constant `_LLM_EXPRESSIVE_PROMPT_VERSION = "v1"`)
   - `input_hash = sha256(canonical_json(payload))`
5) Calls `CategoryExpressiveStore().get(key)`; cache-hit means:
   - `meta.json` exists for that key dir AND
   - `parsed.json` exists and is a dict (store returns `artifact.parsed` as dict)

### Model / prompt_version used (CategoryMeaning expressive)
- Model: `D:\Work\EcomCore\src\app\settings.py` → `OPENROUTER_CHAT_MODEL` (env) default `"openai/gpt-4.1-mini"`
- Prompt version used for *reading* cache: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\category_meaning.py` → `_LLM_EXPRESSIVE_PROMPT_VERSION = "v1"`

### Fallback behavior
Hard fallback to empty expressive:
- If DB fetch fails, reviews table missing, cache missing, invalid cache files, etc → returns `CategoryExpressiveMeaning(vibes=[], llm=None)`.
- This is enforced by a broad `try/except` in `_load_llm_expressive_from_cache(...)`.

### Example JSON (real execution)
From: `D:\Work\EcomCore\docs\seo-module\09_meaning_extraction_real_data_check.md` (debug endpoint output at 2026-04-20 for category `812`).
```json
{
  "project_id": 1,
  "category_id": 812,
  "version": "v1_mvp",
  "functional": {
    "product_types": [
      "кружка"
    ],
    "use_cases": [
      "для кофе",
      "для вас",
      "для самых",
      "для друзей",
      "для чая",
      "для этого",
      "для посудомоечной"
    ],
    "attributes": [
      "true",
      "день",
      "керамика",
      "китай",
      "кружка",
      "подруге",
      "любимой",
      "рождения",
      "хрупкое",
      "год",
      "новый",
      "подарки",
      "принт",
      "керамическая",
      "ра01",
      "росс",
      "марта",
      "повседневная",
      "домашние",
      "дома",
      "коробка",
      "использование",
      "свч",
      "универсальный",
      "машине",
      "посудомоечной",
      "картонная",
      "ребенка",
      "офис",
      "полезные",
      "чая",
      "кофе",
      "светло",
      "розовый",
      "сестре",
      "белый",
      "пакет",
      "воздушно",
      "голубой",
      "котик"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```

Notes (fact):
- Это реальный вывод debug endpoint на дату отчёта; в этом вызове `expressive.vibes` пустой (`[]`).

---

## 2. ProductProjection

### Where implemented
- Builder: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\product_projection.py` (`build_product_projection`)
- Canonical type: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\types.py` (`ProductProjection`)

### Fields (current shape)
`ProductProjection` fields (JSON via `.to_dict()`):
- `project_id: int`
- `category_id: int`
- `nm_id: int`
- `version: "v1_mvp"`
- `functional`:
  - `product_type: string|null`
  - `use_cases: string[]`
  - `attributes: string[]`
- `expressive`:
  - `vibes: string[]`

Additionally returned (debug/explainability):
- `ProductProjectionBuildFlags` in `product_projection.py`:
  - `weak_expressive_signal: bool`
  - `strong_expressive_signal: bool`
  - `used_category_prior: bool`
  - `applied_sku_vibes: bool`

### Expressive: where it comes from?
Current implementation is deterministic + category prior:
- SKU expressive tokens are extracted from SKU title/description by deterministic `_VIBE_TOKENS` lexicon inside `product_projection.py`.
- Weak vs strong signal is determined by `_is_strong_expressive_signal(...)` (title/description + intersection with category prior).
- If signal is weak: use category prior vibes (`CategoryMeaning.expressive.vibes`) as fallback.
- If signal is strong: use SKU vibes first, then category prior appended.

Fact about LLM:
- There is **no SKU-level LLM extraction** in `ProductProjection`.
- The only LLM-derived input available to `ProductProjection` is the category prior list loaded into `CategoryMeaning.expressive.vibes` (if cache-hit).

### Example JSON (real execution)
From: `D:\Work\EcomCore\docs\seo-module\09_meaning_extraction_real_data_check.md` (debug endpoint output at 2026-04-20 for SKU `17187591` in category `812`).
```json
{
  "project_id": 1,
  "category_id": 812,
  "nm_id": 17187591,
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [
      "для этого",
      "для вас",
      "для самых"
    ],
    "attributes": [
      "кружка",
      "дома",
      "кофе",
      "чая",
      "полезные",
      "подарки",
      "керамика",
      "новый",
      "год",
      "день",
      "рождения",
      "китай",
      "хрупкое",
      "белый",
      "подруге",
      "любимой",
      "true"
    ]
  },
  "expressive": {
    "vibes": []
  }
}
```

---

## 3. QueryMeaning

### Where implemented
- Formalization layer: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\query_meaning.py` (`formalize_query_meaning`)
- Canonical type: `D:\Work\EcomCore\src\app\services\seo\meaning_extraction\types.py` (`QueryMeaning`)

### Expressive: exists? where it comes from?
Yes; currently it is an MVP proxy mapping:
- `QueryMeaning.expressive.vibes` is built from `profile.language_markers`.
- The module explicitly states this is a proxy, not “final expressive truth”:
  - `query_meaning.py` header: “`language_markers -> QueryMeaning.expressive.vibes` is a proxy mapping”.

Flags (returned by formalizer for debug):
- `QueryMeaningBuildFlags` (`expressive_vibes_are_mvp_proxy=true`, `expressive_vibes_source="language_markers"`).

### Example JSON (real execution)
From: `D:\Work\EcomCore\docs\seo-module\09_meaning_extraction_real_data_check.md` (debug endpoint output at 2026-04-20 for category `812` cluster_key `qcl:v1:02f281...`).
```json
{
  "project_id": 1,
  "category_id": 812,
  "cluster_key": "qcl:v1:02f281ac4907c046e5bdde12918116ea851756c7",
  "version": "v1_mvp",
  "functional": {
    "product_type": "кружка",
    "use_cases": [],
    "attributes": []
  },
  "expressive": {
    "vibes": [
      "кружка именем"
    ]
  }
}
```

---

## 4. LLM Expressive Layer

### Implemented files (category-level only)
Directory: `D:\Work\EcomCore\src\app\services\seo\expressive_llm\`

- Reviews source access (DB read-only):
  - `reviews_source.py`
    - `fetch_category_review_scope(session, project_id, category_id, min_rating=4, limit=...)`
    - Uses table `wb_feedback_snapshots` joined with `products` on `(project_id, nm_id)`; category scope via `products.subject_id = category_id`.
- Input builder (deterministic payload + hash):
  - `category_input_builder.py`
    - `build_category_expressive_input(category_name, reviews, titles, max_reviews=100, ...)`
    - `input_hash = sha256(canonical_json(payload))`
    - Evidence surface is **reviews only**: `evidence_text = "\n".join(reviews)`
- LLM call orchestration (offline, cache-first):
  - `category_extractive_service.py`
    - `run_single_category_expressive_extraction(...)`
    - Uses `OpenRouterProvider` to send chat request (temperature/top_p/max_tokens are parameters).
    - Persists `input_payload.json` + `llm_messages.json` to artifact dir before calling LLM.
- Output parser + validation:
  - `category_output_parser.py`
    - `parse_and_validate_category_expressive_output(content, evidence_text, max_vibes, strict=...)`
    - Evidence validation uses exact substring check (see below).
  - `validation.py`
    - `validate_evidence_spans(...)` checks `span in evidence_text` per span.
- Storage/cache:
  - `storage.py` (`CategoryExpressiveStore`, `CategoryExpressiveCacheKey`)
  - Stores `meta.json`, `raw_response.json`, `parsed.json`, `validation.json` under key-based dir.
- Text normalization helpers:
  - `text_normalization.py`

### Used in runtime or scripts?
Fact:
- LLM calling code (`OpenRouterProvider.generate_chat`) is currently only reachable via scripts (offline path).
- Runtime API paths do **not** call LLM.
- Runtime `CategoryMeaning` may read cache artifacts (no LLM calls) because it uses `CategoryExpressiveStore().get(...)` inside `_load_llm_expressive_from_cache(...)`.

---

## 5. Cache / Storage

### Cache key (category expressive)
`CategoryExpressiveCacheKey` (see `storage.py`):
- `project_id`
- `category_id`
- `model`
- `prompt_version`
- `input_hash` (sha256 of canonical JSON payload)

### Default location
`CategoryExpressiveStore` default root dir:
- env override: `SEO_EXPRESSIVE_CACHE_DIR` (if set)
- else: `settings.INTERNAL_DATA_DIR/seo_expressive_cache` where `INTERNAL_DATA_DIR` default is `/data/internal_data` (see `D:\Work\EcomCore\src\app\settings.py`).

### On-disk layout (current)
Root: `<root_dir>/cat_expr/...` (see `storage.py`)
```
cat_expr/
  p{project_id}/
    c{category_id}/
      m_{model_sanitized}/
        pv_{prompt_version}/
          h_{input_hash}/
            meta.json
            raw_response.json
            parsed.json
            validation.json
            input_payload.json
            llm_messages.json
```

### What is stored
- `raw_response.json`: provider raw response + `usage` (includes `cost` when available) + `content`
- `parsed.json`: normalized parsed JSON with `vibes[]`/`summary`
- `validation.json`: evidence exact-match checks + evidence_quality summary
- `meta.json`: cache key + extra prompt stats (prompt_chars/tokens_est)
- `input_payload.json`: exact payload sent as INPUT_JSON
- `llm_messages.json`: exact system+user messages sent

### Hit/miss determination
- Store-level hit: `CategoryExpressiveStore.get(key)` checks existence of `meta.json` under computed artifact dir (or legacy layout).
- CategoryMeaning-level hit: same store-level hit + requires parsed to be a dict.
- Offline runner hit: store-level hit + additionally checks `parsed` and `validation` present before returning `cache_hit=true`.

### Existing real cache artifacts (category 812)
Under: `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\`
- `pv_v1\h_419343aa...` (prompt_version=v1)
- `pv_v2\h_419343aa...` (prompt_version=v2)
- `pv_v3\h_419343aa...` (prompt_version=v3)

Example parsed artifact (v1) file:
- `D:\Work\EcomCore\outputs\seo_expressive_cache\cat_expr\p1\c812\m_openai__gpt-4.1-mini\pv_v1\h_419343aa7636a1489354a1766726a85c7009b40ad0b87be73a258592d9dc0645\parsed.json`

---

## 6. Runtime Entry Points

### API (debug/internal)
Meaning Extraction debug endpoint:
- Router: `D:\Work\EcomCore\src\app\routers\seo_meaning_extraction_debug.py`
- Path: `GET /api/v1/projects/{project_id}/seo/meaning-extraction/debug`
- Returns:
  - `category_meaning` (dict)
  - `product_projection` (dict)
  - `query_meaning` (dict)
  - `product_projection_flags` (dict)
  - `query_meaning_flags` (dict)

Query pipeline debug endpoint (used to discover cluster_key etc):
- Router: `D:\Work\EcomCore\src\app\routers\seo_query_pipeline_debug.py`
- Path: `GET /api/v1/projects/{project_id}/seo/query-pipeline/debug`

Routers are included in app:
- `D:\Work\EcomCore\src\app\main.py` includes `seo_query_pipeline_debug_router` and `seo_meaning_extraction_debug_router`.

### Scripts (offline/precompute)
Category expressive single-category runner:
- `D:\Work\EcomCore\scripts\run_category_expressive_single_category.py`
  - Opens DB session (`SessionLocal`)
  - Calls `run_single_category_expressive_extraction(...)`
  - Writes/reads cache via `CategoryExpressiveStore`

Other scripts exist in repo but are not part of runtime:
- `D:\Work\EcomCore\scripts\expressive_llm_eval.py`
- `D:\Work\EcomCore\scripts\prepare_category_expressive_input_preview.py`
- (plus multiple query pipeline scripts under `D:\Work\EcomCore\scripts\run_query_*.py`)

---

## 7. Data Flow (factual)

### CategoryMeaning flow (current implementation)
1) Fetch SKU evidence rows from `products` (latest snapshot per SKU) in `category_meaning.py` (`_fetch_latest_sku_evidence`).
2) Extract deterministic token sets:
   - `product_types_by_sku`, `use_cases_by_sku`, `attributes_by_sku`
3) Aggregate “repeating patterns” using MVP thresholds (`CategoryMeaningThresholds`) → `functional`.
4) Load expressive from cache (no LLM call):
   - DB reviews scope (`wb_feedback_snapshots` + `products` join)
   - deterministic input payload + `input_hash`
   - `CategoryExpressiveStore.get(key)` → if hit, read `parsed.vibes[].label` → `CategoryMeaning.expressive.vibes`
   - else → empty expressive

### ProductProjection flow (current implementation)
1) Fetch 1 SKU row from `products` (`_fetch_sku_row`).
2) Ensure SKU is in category scope (`subject_id == category_id`).
3) Ensure `CategoryMeaning` is available:
   - uses passed `category_meaning` or builds it via `build_category_meaning(...)`.
4) Deterministic functional extraction:
   - `product_type` from title tokens + category axes fallback
   - `use_cases` from title/description tokens intersecting category axes
   - `attributes` from characteristics/sizes/colors/dimensions flattened + category axes
5) Expressive projection:
   - deterministic `_VIBE_TOKENS` matched in title/description
   - strong/weak rule
   - weak → category prior vibes
   - strong → SKU vibes + category prior
6) Returns `(ProductProjection, ProductProjectionBuildFlags)`.

### QueryMeaning flow (current implementation)
1) Query pipeline profile extraction is executed (debug endpoint does this):
   - `run_query_profile_extraction(...)` in `D:\Work\EcomCore\src\app\services\seo\query_pipeline\profiles.py`
2) For one selected `ExtractedClusterProfile`, `formalize_query_meaning(...)` maps:
   - `product_type_markers` → `QueryMeaning.functional.product_type`
   - `use_case_markers` → `QueryMeaning.functional.use_cases`
   - `attribute_markers` → `QueryMeaning.functional.attributes`
   - `language_markers` → `QueryMeaning.expressive.vibes` (MVP proxy)
3) Returns `(QueryMeaning, QueryMeaningBuildFlags)`.

---

## 8. What is реально используется

### Used in runtime (API server)
- `GET /api/v1/projects/{project_id}/seo/meaning-extraction/debug`:
  - `build_category_meaning(...)`
  - `build_product_projection(...)`
  - `run_query_profile_extraction(...)`
  - `formalize_query_meaning(...)`
- `GET /api/v1/projects/{project_id}/seo/query-pipeline/debug` (query pipeline diagnostics)

### Used only in scripts (offline)
- `run_single_category_expressive_extraction(...)` (LLM call path)
- `scripts/run_category_expressive_single_category.py`
- `scripts/expressive_llm_eval.py`, `scripts/prepare_category_expressive_input_preview.py` (eval/preview tooling)

### Used in tests
Meaning extraction unit/integration tests exist under:
- `D:\Work\EcomCore\tests\test_seo_meaning_types.py`
- `D:\Work\EcomCore\tests\test_seo_category_meaning_builder.py`
- `D:\Work\EcomCore\tests\test_seo_category_meaning_llm_cache_integration.py`
- `D:\Work\EcomCore\tests\test_seo_product_projection_builder.py`
- `D:\Work\EcomCore\tests\test_seo_query_meaning_formalization.py`
- `D:\Work\EcomCore\tests\test_seo_meaning_extraction_debug_api.py`
- `D:\Work\EcomCore\tests\test_seo_expressive_llm_*.py`

### Not used (no call sites found in runtime)
`Meaning Extraction` package (`app.services.seo.meaning_extraction`) is not referenced by scoring/matcher modules; only by the debug router.

---

## 9. Gaps (factual, from code)

- No runtime hot-path LLM calls exist for category expressive (LLM is only in offline script path).
- Runtime `CategoryMeaning` reads category expressive only from **prompt_version="v1"** cache; caches with `prompt_version="v2"/"v3"` are present on disk but are not read by `build_category_meaning` (as implemented).
- No SKU-level LLM expressive extraction exists.
- No query-side LLM expressive extraction exists.
- `Meaning Extraction` outputs are not consumed by scoring pipeline modules (no imports/call sites outside debug endpoint).

---

## 10. Минимальные примеры (из реального выполнения)

Source: `D:\Work\EcomCore\docs\seo-module\09_meaning_extraction_real_data_check.md` (debug endpoint run at 2026-04-20).

### Category JSON (CategoryMeaning)
See section **1** above (category `812`).

### Product JSON (ProductProjection)
See section **2** above (nm_id `17187591`, category `812`).

### Query JSON (QueryMeaning)
See section **3** above (cluster_key `qcl:v1:02f281...`, category `812`).
