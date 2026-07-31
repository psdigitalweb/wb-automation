# SEO Module Overview

## Purpose From Repo Docs

The SEO module is described as a pipeline for matching SKU/product meaning to search-query meaning, scoring relevance, explaining decisions, and eventually generating WB card text. The clearest architecture intent is in `docs/seo-module/00_master_context.md`, `docs/seo-module/01_architecture.md`, and `docs/seo-module/02_roadmap.md`.

Documented core path:

```text
SKU/Product Meaning -> Query Meaning -> Matcher -> Scoring -> Generation
```

Evidence:

- `docs/seo-module/00_master_context.md`: declares clustering, noise handling, separate semantic layers, review usage, trust-aware SKU representation, scoring, explainability, and versioning as core constraints.
- `docs/seo-module/01_architecture.md`: defines Product Side, Query Side, Matcher, Scoring, and explicit non-goals for the earlier stage.
- `docs/seo-module/02_roadmap.md`: marks the product state as pre-MVP/R&D prototype and phases SKU meaning, eval dataset, LLM query meaning, matcher MVP, meaning-based scoring, generation, and productionization.
- `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md`: defines Atoms v1 as the next target matcher architecture, first in production-preview/shadow mode.
- `docs/seo-module/24_wb_seo_generation_adaptation.md`: documents the imported WB generation prompt/rules/model policy adapted into EcomCore.

## Current Actual Scope In Code

Implemented runtime code now covers:

- Query CSV ingestion and normalization: `src/app/services/seo/query_pipeline/ingestion.py::import_queries_from_csv`, `src/app/services/seo/query_pipeline/normalization.py::normalize_query_text`, router `src/app/routers/seo_query_import.py`.
- Unified query dataset, pruning, deterministic lexical clustering, hybrid annotation, and profile extraction: `src/app/services/seo/query_pipeline/unified_dataset.py`, `pruning.py`, `clustering.py`, `hybrid.py`, `profiles.py`.
- Experimental semantic clustering comparison: `src/app/services/seo/query_pipeline/semantic.py::run_semantic_clustering_experiment`.
- Meaning extraction MVP: `src/app/services/seo/meaning_extraction/types.py`, `category_meaning.py`, `product_projection.py`, `query_meaning.py`.
- Offline category expressive LLM cache: `src/app/services/seo/expressive_llm/*`.
- Category bootstrap/readiness/axes/query meanings/embeddings/atoms: `src/app/services/seo/category_bootstrap.py`.
- Query meaning library and meaning-aware matcher: `src/app/services/seo/query_meaning_matcher/library.py`, `matcher.py`, `embeddings.py`.
- SKU meaning evidence/draft/annotation/judgments: `src/app/services/seo/sku_meaning/evidence.py`, `draft.py`, `annotations.py`.
- Product-facing workflow and query set persistence: `src/app/services/seo/products.py`.
- WB generation service and page: `src/app/services/seo/generation/service.py`, `src/app/routers/seo_generation.py`, `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`.
- ORM/migrations for the above: `src/app/models.py` and SEO migrations under `alembic/versions/`.

Important repository-state caveat: most SEO runtime additions are untracked or dirty in `git status --short`, including many routers, services, migrations, docs, frontend pages, and tests. That does not make them false, but it means the audit must treat the current working tree as the source of truth, not only committed history.

## Major Submodules

- Backend API routers: `src/app/routers/seo_query_import.py`, `seo_query_pipeline_debug.py`, `seo_meaning_extraction_debug.py`, `seo_sku_meaning.py`, `seo_query_meaning_matcher.py`, `seo_category_bootstrap.py`, `seo_products.py`, `seo_generation.py`.
- Backend schemas: `src/app/schemas/seo_*.py`.
- Query pipeline services: `src/app/services/seo/query_pipeline/*`.
- Meaning layers: `src/app/services/seo/meaning_extraction/*`, `src/app/services/seo/query_meaning_matcher/*`, `src/app/services/seo/meaning_atoms/*`.
- SKU analysis: `src/app/services/seo/sku_meaning/*`, `src/app/services/seo/products.py`.
- Generation: `src/app/services/seo/generation/service.py`, `src/app/services/seo/generation/prompts/wb_card_system_v1.md`.
- Provider boundary: `src/app/services/seo/providers/base.py`, `src/app/services/seo/providers/openrouter.py`.
- Frontend SEO pages: `frontend/app/app/project/[projectId]/seo/**`.
- Scripts/spikes: `scripts/run_query_*.py`, `scripts/run_category_expressive_*.py`, `scripts/*meaning*`, `scripts/expressive_llm_eval.py`.

## Maturity Level

Current maturity is mixed:

- Implemented: ingestion, normalization, unified query dataset, pruning/versioning, deterministic query clustering, hybrid annotation, profile diagnostics, category bootstrap, query meaning library, SKU meaning annotation, atoms storage, query selection, generation draft persistence.
- Partially implemented: Atoms v1 production-preview, scoring persistence, explainability persistence, category expressive extraction, semantic clustering, generation validation/relevance scoring.
- Documented but not fully implemented: separate Atoms v1 storage tables and matcher-run persistence from `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md`, production feedback loop, mass generation, WB publish workflow.
- Legacy/placeholder: SKU clustering skeleton in `src/app/services/seo/clustering/*` and models `SeoSkuClusterRun`, `SeoSkuCluster`, `SeoSkuClusterAssignment`; `src/app/models.py` has defaults such as `placeholder`, `todo_rule_based`, `trust_aware_placeholder`, `hdbscan_placeholder`.

## Architectural Boundaries

- Scope key is `(project_id, category_id)` where `category_id` means WB subject/category scope, not `internal_categories.id`. Evidence: `src/app/models.py::SeoProjectCategoryScopedMixin` and `SEO_CATEGORY_SCOPE_COMMENT`.
- Provider boundary is explicit: `src/app/services/seo/providers/base.py::ChatProvider`, `EmbeddingProvider`; OpenRouter adapter lives in `src/app/services/seo/providers/openrouter.py::OpenRouterProvider`.
- Product evidence comes from `products` and WB review tables through service code, not from SEO tables alone. Evidence: `src/app/services/seo/sku_meaning/evidence.py::build_sku_evidence_pack`, `src/app/services/seo/expressive_llm/reviews_source.py::fetch_category_review_scope`.
- Generation requires selected query sets and product evidence. Evidence: `src/app/services/seo/generation/service.py::_load_query_set`, `_build_generation_brief`, `run_seo_generation`.
- Frontend calls backend through `frontend/lib/apiClient.ts` SEO helpers and pages under `frontend/app/app/project/[projectId]/seo/**`.

## Runtime Entry Points

Backend router registration is in `src/app/main.py` via imports/includes for:

- `seo_query_import_router`
- `seo_query_pipeline_debug_router`
- `seo_meaning_extraction_debug_router`
- `seo_sku_meaning_router`
- `seo_query_meaning_matcher_router`
- `seo_category_bootstrap_router`
- `seo_generation_router`
- `seo_products_router`

Main HTTP endpoints are defined in:

- `src/app/routers/seo_query_import.py`: CSV import/corpus/batch delete/category clear.
- `src/app/routers/seo_query_pipeline_debug.py`: query pipeline diagnostics and semantic comparison.
- `src/app/routers/seo_meaning_extraction_debug.py`: meaning extraction debug.
- `src/app/routers/seo_sku_meaning.py`: SKU evidence/draft/annotation/candidates/judgments/eval export.
- `src/app/routers/seo_query_meaning_matcher.py`: query meaning library build/list and matcher preview.
- `src/app/routers/seo_category_bootstrap.py`: category bootstrap run/status.
- `src/app/routers/seo_products.py`: product list/summary/analysis/query selection.
- `src/app/routers/seo_generation.py`: generation run/latest/recalculate SEO V2.

Script entry points include:

- `scripts/import_seo_queries.py`
- `scripts/prepare_seo_query_dataset.py`
- `scripts/run_query_pruning.py`
- `scripts/run_query_clustering.py`
- `scripts/run_query_hybrid_annotation.py`
- `scripts/run_query_profile_extraction.py`
- `scripts/run_query_scoring_prep.py`
- `scripts/run_query_actual_scoring.py`
- `scripts/run_query_semantic_clustering.py`
- `scripts/run_category_expressive_single_category.py`
- `scripts/expressive_llm_eval.py`
- `scripts/sku_query_semantic_retrieval_spike.py`

