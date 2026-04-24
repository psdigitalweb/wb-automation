# Risks And Smells Inventory

This inventory is factual and repo-grounded. It is not a final judgment.

## Dirty/Untracked Runtime Surface

- Many SEO files are untracked or modified in `git status --short`: routers, schemas, services, migrations, docs, frontend pages, tests.
- Examples: `src/app/routers/seo_generation.py`, `src/app/services/seo/generation/service.py`, `src/app/services/seo/products.py`, `src/app/services/seo/category_bootstrap.py`, `frontend/app/app/project/[projectId]/seo/`, migrations from `20260414` onward.
- Risk: committed history may not reflect the actual implementation; audit/review must use current working tree.

## Runtime Import From Experiment Package

- `src/app/services/seo/query_meaning_matcher/matcher.py` imports Atoms matching from `src/app/services/seo/experiments/meaning_atoms/v1.py::match_atoms_v1`.
- `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md` says not to directly promote current experiment code to production.
- Risk: experimental code is now on the runtime path.

## Placeholder SKU Clustering

- `src/app/services/seo/clustering/service.py::cluster_skus_placeholder`.
- `src/app/services/seo/clustering/hdbscan_hook.py::run_hdbscan_placeholder`.
- `src/app/models.py::SeoSkuClusterRun` has defaults `placeholder`, `todo_rule_based`, `trust_aware_placeholder`, `hdbscan_placeholder`.
- Direct search found use mainly via exports/tests.
- Risk: SKU clustering tables/services can be mistaken for implemented clustering.

## Profile Persistence Gap

- `src/app/models.py::SeoClusterProfile`, `SeoClusterProfileVersion` and migration tables exist.
- `src/app/services/seo/query_pipeline/profiles.py::run_query_profile_extraction` returns diagnostics/projection and does not persist those model classes.
- Direct search found `SeoClusterProfile` classes only in model definitions.
- Risk: model surface implies persistence that current runtime does not provide.

## Score Persistence Gap

- `src/app/models.py::SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation` exist.
- `src/app/services/seo/scoring/service.py::create_score_run`, `persist_query_score` exist.
- Current active scoring functions are `scoring/preparation.py::run_query_scoring_preparation` and `scoring/actual.py::run_query_actual_scoring`; direct search did not show them writing via `persist_query_score`.
- Risk: score APIs/scripts may look complete but produce diagnostics only.

## Multiple Meaning Representations

- MVP dataclasses: `meaning_extraction/types.py::CategoryMeaning`, `ProductProjection`, `QueryMeaning`.
- Persistent axes: `src/app/models.py::SeoCategoryMeaningAxes`.
- Persistent query meanings: `SeoQueryMeaning`.
- Persistent atoms: `SeoMeaningAtom`.
- Generation brief: internal dict in `generation/service.py::_build_generation_brief`.
- Risk: no single authoritative meaning representation; audit must trace which layer feeds which path.

## JSON Meta As Soft Schema

- Hybrid annotation projection is stored in `SeoQueryAnnotation.meta["hybrid_annotation"]`.
- Generation stores validation/relevance in `SeoContentVersion.score_breakdown`.
- `SeoGenerationRun.request_payload` and `response_payload` contain operational payloads.
- Risk: important state lacks explicit relational schema/invariants.

## Raw SQL And Schema Drift

- Raw/text SQL is used in:
  - `query_pipeline/unified_dataset.py`
  - `meaning_extraction/category_meaning.py`
  - `meaning_extraction/product_projection.py`
  - `sku_meaning/evidence.py`
  - `expressive_llm/reviews_source.py`
  - `products.py`
- Risk: cross-module schema leakage from products/search/reviews into SEO code; migrations/model changes can silently break queries.

## File Caches Outside DB Trace

- `expressive_llm/storage.py::CategoryExpressiveStore`.
- `sku_meaning/draft.py::SkuMeaningDraftStore`.
- `category_bootstrap.py` artifact root uses `SEO_CATEGORY_BOOTSTRAP_CACHE_DIR` or `settings.INTERNAL_DATA_DIR`.
- `query_meaning_matcher/library.py::_store_artifact`.
- `meaning_atoms/storage.py::_cache_dir`.
- Risk: important prompts/responses/artifacts may not be recoverable from DB alone.

## Generation Policy Split Across Docs, Prompt, Code, UI

- Docs: `docs/seo-module/24_wb_seo_generation_adaptation.md`, imported `docs/seo-module/wb-seo-generator/*`.
- Runtime prompt: `src/app/services/seo/generation/prompts/wb_card_system_v1.md`.
- Validation/relevance code: `src/app/services/seo/generation/service.py`.
- UI rules panel: `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`.
- Risk: rule drift between prompt/docs/code/UI.

## Hardcoded Frontend Model Names

- Backend settings: `src/app/settings.py::SEO_GENERATION_PRIMARY_MODEL`, `SEO_GENERATION_FALLBACK_MODEL`.
- Frontend preview: `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx` hardcodes `anthropic/claude-haiku-4.5` and `anthropic/claude-sonnet-4.5` in `briefPreview`.
- Risk: UI can display stale model policy if env settings differ.

## User-Facing Status Labels As Logic

- `products.py` generates Russian status labels in `_label_category_status`, `_label_product_status`, `_label_vision_status`.
- Frontend checks values such as product/category readiness labels in SEO pages.
- Risk: label text changes can break UI readiness logic.

## Old Docs Contradict New Code

- `docs/seo-module/00_master_context.md` says do not implement final text generation yet.
- `docs/seo-module/01_architecture.md` lists generation as a non-goal for current stage.
- `src/app/services/seo/generation/service.py` and `docs/seo-module/24_wb_seo_generation_adaptation.md` implement/document generation.
- Risk: audit must identify doc chronology and update old constraints or mark them superseded.

## Category ID Ambiguity

- `src/app/models.py` explicitly says category id is WB scope, not `internal_categories.id`.
- Multiple APIs accept `category_id`; frontend routes also use `category_id` in query strings.
- Risk: without this invariant, calls can pass internal category ids by mistake.

## Silent Fallbacks

- `category_meaning.py::_load_llm_expressive_from_cache` catches exceptions and returns empty expressive meaning.
- `products.py::run_product_analysis` catches SKU draft failures and writes fallback meaning.
- `meaning_atoms/storage.py::ensure_sku_atoms` falls back to `_fallback_sku_atoms` if extraction fails.
- Risk: degraded quality can appear as successful pipeline completion unless diagnostics are inspected.

## No WB Publish Boundary In Generation

- `generation/service.py::run_seo_generation` writes draft content and run payload.
- `docs/seo-module/24_wb_seo_generation_adaptation.md` says human review remains mandatory and MVP must not publish to WB Content API.
- No publish path was identified in generation service.
- Risk: safe boundary exists, but any future publish path must explicitly check `needs_review`/human approval.

## Observability Is Mostly Payload-Based

- Debug endpoints/pages exist, but no dedicated metrics/logging/trace framework was identified in inspected SEO code.
- Persistence is spread across versions, meta JSON, score breakdowns, run payloads, file artifacts.
- Risk: production diagnosis may require reconstructing state from several places.

## Tests Exist But Coverage Needs Mapping

- SEO tests are extensive: e.g. `tests/test_seo_query_ingestion.py`, `test_seo_query_pruning.py`, `test_seo_query_clustering.py`, `test_seo_query_hybrid_annotation.py`, `test_seo_query_meaning_matcher.py`, `test_seo_generation_validator.py`, `test_seo_product_query_selection.py`.
- Risk: presence of tests does not guarantee end-to-end generation/readiness behavior; audit should map tests to pipelines.

