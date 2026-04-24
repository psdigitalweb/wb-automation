# Audit Handoff Brief

## Definitely Implemented

- Query CSV import, raw/normalized persistence, and import/corpus APIs.
  - Inspect: `src/app/services/seo/query_pipeline/ingestion.py`, `normalization.py`, `src/app/routers/seo_query_import.py`, models `SeoQueryBatch`, `SeoQueryRaw`, `SeoQueryNormalized`.
- Unified query dataset and pruning/basic annotation with versions.
  - Inspect: `src/app/services/seo/query_pipeline/unified_dataset.py`, `pruning.py`, models `SeoQueryAnnotation`, `SeoQueryAnnotationVersion`.
- Deterministic lexical query clustering and membership persistence.
  - Inspect: `src/app/services/seo/query_pipeline/clustering.py`, models `SeoQueryCluster`, `SeoQueryClusterMembership`.
- Hybrid annotation projection.
  - Inspect: `src/app/services/seo/query_pipeline/hybrid.py`.
- Query profile extraction as diagnostics/projection.
  - Inspect: `src/app/services/seo/query_pipeline/profiles.py`.
- Deterministic MVP meaning dataclasses/builders.
  - Inspect: `src/app/services/seo/meaning_extraction/*`.
- Category expressive offline cache service.
  - Inspect: `src/app/services/seo/expressive_llm/*`.
- Category bootstrap/readiness/axes/query meanings/atoms/embeddings orchestration.
  - Inspect: `src/app/services/seo/category_bootstrap.py`, migrations `20260421*`, `20260422*`.
- SKU meaning evidence/draft/annotation/judgments and product-facing analysis.
  - Inspect: `src/app/services/seo/sku_meaning/*`, `src/app/services/seo/products.py`.
- Meaning-aware matcher and query set persistence.
  - Inspect: `src/app/services/seo/query_meaning_matcher/matcher.py`, `src/app/services/seo/products.py`, models `SeoSkuQuerySet`, `SeoSkuQuerySetItem`.
- Generation draft service with prompt, two-model policy, validation/retry, relevance reports, and DB persistence.
  - Inspect: `src/app/services/seo/generation/service.py`, `src/app/services/seo/generation/prompts/wb_card_system_v1.md`, `src/app/routers/seo_generation.py`, models `SeoGenerationRun`, `SeoContentVersion`.
- Frontend pages for SEO category/product/query-selection/generation workflows.
  - Inspect: `frontend/app/app/project/[projectId]/seo/**`, `frontend/lib/apiClient.ts`.

## Not Implemented Or Not Wired

- Production SKU clustering is not implemented; existing code is placeholder.
  - Inspect: `src/app/services/seo/clustering/*`, model defaults in `src/app/models.py::SeoSkuClusterRun`.
- Cluster profile persistence is not wired.
  - Inspect: `src/app/models.py::SeoClusterProfile`, `SeoClusterProfileVersion`, `src/app/services/seo/query_pipeline/profiles.py`.
- Score persistence/explanation tables are not clearly used by actual scoring.
  - Inspect: `src/app/services/seo/scoring/actual.py`, `preparation.py`, `service.py`, models `SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation`.
- Dedicated Atoms v1 storage/matcher-run tables from docs are not implemented as documented.
  - Actual: `SeoMeaningAtom`, `SeoSkuQuerySet`, `SeoSkuQuerySetItem`.
  - Docs: `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md`.
- WB Content API publishing is not implemented in the generation service.
- Production feedback loop/mass generation is documented but not evident in runtime code.

## Contradictions To Resolve

- Older docs say not to implement generation yet; current code implements draft generation.
  - Docs: `00_master_context.md`, `01_architecture.md`.
  - Newer doc/code: `24_wb_seo_generation_adaptation.md`, `generation/service.py`.
- Atoms v1 docs say not to directly promote experiment code; runtime matcher imports experiment Atoms v1 matcher.
  - Docs: `23_atoms_v1_design_and_implementation_plan.md`.
  - Code: `query_meaning_matcher/matcher.py`, `experiments/meaning_atoms/v1.py`.
- Atoms v1 docs propose separate atom tables and matcher runs; actual migration uses generic `seo_meaning_atoms` plus query set tables.
  - Code/migration: `models.py::SeoMeaningAtom`, `20260422_add_seo_atoms_and_query_sets.py`.
- Frontend generation page hardcodes model names in preview while backend model ids are settings-driven.
  - Frontend: `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`.
  - Backend: `src/app/settings.py::SEO_GENERATION_PRIMARY_MODEL`, `SEO_GENERATION_FALLBACK_MODEL`.

## Highest-Priority Audit Focus

1. Trace generation safety end to end.
   - `products.py::run_query_selection` -> `generation/service.py::_build_generation_brief` -> `run_seo_generation` -> `validate_generated_card` -> `SeoContentVersion`.
2. Audit runtime dependency on experiment Atoms v1.
   - `query_meaning_matcher/matcher.py` -> `experiments/meaning_atoms/v1.py`.
3. Verify scoring architecture and persistence.
   - `scoring/actual.py`, `scoring/preparation.py`, `scoring/service.py`, score models.
4. Verify category bootstrap idempotency/failure semantics.
   - `category_bootstrap.py`, readiness models/migrations.
5. Check docs drift and decide canonical architecture docs.
   - `00_master_context.md`, `01_architecture.md`, `02_roadmap.md`, `23_atoms_v1_design_and_implementation_plan.md`, `24_wb_seo_generation_adaptation.md`.

## Highest-Priority Files For Inspection

- `src/app/services/seo/generation/service.py`
- `src/app/services/seo/products.py`
- `src/app/services/seo/query_meaning_matcher/matcher.py`
- `src/app/services/seo/meaning_atoms/storage.py`
- `src/app/services/seo/category_bootstrap.py`
- `src/app/services/seo/query_meaning_matcher/library.py`
- `src/app/services/seo/sku_meaning/evidence.py`
- `src/app/services/seo/sku_meaning/draft.py`
- `src/app/services/seo/sku_meaning/annotations.py`
- `src/app/services/seo/query_pipeline/pruning.py`
- `src/app/services/seo/query_pipeline/clustering.py`
- `src/app/services/seo/query_pipeline/hybrid.py`
- `src/app/services/seo/query_pipeline/profiles.py`
- `src/app/models.py`
- `alembic/versions/20260422_add_seo_atoms_and_query_sets.py`
- `alembic/versions/20260421_add_query_meaning_library_and_embeddings.py`
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`
- `frontend/lib/apiClient.ts`

## Ambiguities For Second Auditor

- Whether current generation should be treated as approved MVP preview or premature relative to Atoms/eval gates.
- Whether generic `SeoMeaningAtom` is an intentional simplification of the documented separate Atoms v1 storage or an incomplete migration from the design.
- Whether score persistence is intentionally deferred or accidentally disconnected from active scoring.
- Whether category axes, deterministic `CategoryMeaning`, query meanings, and atoms have a clear authority hierarchy.
- Whether file-cache artifacts are adequately versioned/backed up for auditability.

