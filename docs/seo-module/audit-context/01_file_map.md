# SEO File Map

## Backend Models And Config

- `src/app/models.py`
  - Matters because it defines the SEO persistence model.
  - Key symbols: `SeoProjectCategoryScopedMixin`, `SeoQueryBatch`, `SeoQueryRaw`, `SeoQueryNormalized`, `SeoQueryCluster`, `SeoQueryClusterMembership`, `SeoQueryAnnotation`, `SeoQueryAnnotationVersion`, `SeoSkuClusterRun`, `SeoSkuCluster`, `SeoSkuClusterAssignment`, `SeoClusterProfile`, `SeoClusterProfileVersion`, `SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation`, `SeoContentVersion`, `SeoGenerationRun`, `SeoQueryMeaning`, `SeoMeaningEmbedding`, `SeoMeaningAtom`, `SeoCategoryBootstrapRun`, `SeoCategoryMatchingReadiness`, `SeoCategoryMeaningAxes`, `SeoSkuMeaningAnnotation`, `SeoSkuQueryJudgment`, `SeoSkuQuerySet`, `SeoSkuQuerySetItem`, `SeoSkuMeaningAuditEvent`.
  - Status: implemented schema definitions, with SKU clustering/profile/score entities partly placeholder or unused in current runtime.
- `src/app/settings.py`
  - Matters because OpenRouter and generation model settings are here.
  - Key symbols: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_CHAT_MODEL`, `OPENROUTER_EMBEDDING_MODEL`, `SEO_GENERATION_PROVIDER`, `SEO_GENERATION_PRIMARY_MODEL`, `SEO_GENERATION_FALLBACK_MODEL`, `SEO_GENERATION_TEMPERATURE`, `SEO_GENERATION_TOP_P`, `SEO_GENERATION_MAX_TOKENS`, `SEO_GENERATION_MAX_ATTEMPTS`, `INTERNAL_DATA_DIR`.
- `src/app/main.py`
  - Matters because it wires SEO routers into FastAPI.
  - Key symbols: imports/includes for `seo_*_router`.

## Backend Routers

- `src/app/routers/seo_query_import.py`
  - CSV query import/corpus/batch operations.
  - Key symbols: `import_seo_query_csv_endpoint`, `get_latest_seo_query_import_batch_endpoint`, `get_seo_query_import_corpus_endpoint`, `get_seo_query_import_batch_endpoint`, `delete_seo_query_import_batch_endpoint`, `clear_seo_query_import_category_endpoint`.
- `src/app/routers/seo_query_pipeline_debug.py`
  - Debug view over pruning/clustering/hybrid/profile/scoring/semantic comparison.
  - Key symbol: `get_seo_query_pipeline_debug_endpoint`.
- `src/app/routers/seo_meaning_extraction_debug.py`
  - Debug API for meaning extraction.
  - Key symbol: `get_seo_meaning_extraction_debug_endpoint`.
- `src/app/routers/seo_sku_meaning.py`
  - SKU evidence/draft/annotation/candidate-query/judgment/export API.
  - Key symbols: `get_sku_meaning_product_lookup_endpoint`, `get_sku_meaning_evidence_endpoint`, `post_sku_meaning_draft_endpoint`, `get_sku_meaning_annotation_endpoint`, `put_sku_meaning_annotation_endpoint`, `get_sku_meaning_candidate_queries_endpoint`, `put_sku_meaning_query_judgments_endpoint`, `post_sku_meaning_eval_export_endpoint`.
- `src/app/routers/seo_query_meaning_matcher.py`
  - Query meaning library and matcher preview API.
  - Key symbols: `post_query_meaning_library_build_endpoint`, `get_query_meaning_library_endpoint`, `post_meaning_aware_matcher_preview_endpoint`.
- `src/app/routers/seo_category_bootstrap.py`
  - Category readiness/bootstrap API.
  - Key symbols: `post_category_bootstrap_run_endpoint`, `get_category_bootstrap_status_endpoint`.
- `src/app/routers/seo_products.py`
  - Product-facing SEO workflow API.
  - Key symbols: `get_seo_products_endpoint`, `get_seo_product_summary_endpoint`, `post_seo_product_analysis_run_endpoint`, `get_seo_product_analysis_status_endpoint`, `post_seo_query_selection_run_endpoint`, `get_seo_query_selection_endpoint`, `put_seo_query_selection_endpoint`.
- `src/app/routers/seo_generation.py`
  - Generation API.
  - Key symbols: `post_seo_generation_run_endpoint`, `get_seo_generation_latest_endpoint`, `post_seo_generation_recalculate_seo_v2_endpoint`.

## Schemas

- `src/app/schemas/seo_query_import.py`: query import request/response shapes.
- `src/app/schemas/seo_query_pipeline_debug.py`: debug response shapes for pipeline views.
- `src/app/schemas/seo_meaning_extraction_debug.py`: debug response shapes for meaning extraction.
- `src/app/schemas/seo_sku_meaning.py`: SKU evidence, draft, annotation, query judgments.
- `src/app/schemas/seo_query_meaning_matcher.py`: query meaning library/matcher responses; includes `MEANING_AWARE_MATCHER_VERSION`.
- `src/app/schemas/seo_category_bootstrap.py`: category bootstrap request/status/run responses.
- `src/app/schemas/seo_products.py`: product summary, product analysis, query set selection responses.
- `src/app/schemas/seo_generation.py`: `SeoGenerationRunRequest`, `GeneratedCard`, `GenerationValidationIssue`, `SeoRelevanceReport`, `SeoRelevanceV2Report`, run/latest responses.

## Query Pipeline

- `src/app/services/seo/query_pipeline/normalization.py`
  - Query text normalization and CSV column/frequency extraction.
  - Key symbols: `normalize_query_text`, `resolve_query_column`, `resolve_frequency_column`, `extract_query_text`, `extract_frequency`.
- `src/app/services/seo/query_pipeline/ingestion.py`
  - CSV ingestion into raw/normalized tables.
  - Key symbols: `import_queries_from_csv`, `CsvImportError`.
- `src/app/services/seo/query_pipeline/corpus.py`
  - Corpus assembly/status helper used by import/debug APIs.
- `src/app/services/seo/query_pipeline/unified_dataset.py`
  - Combines CSV and WB search report sources into canonical rows.
  - Key symbols: `CanonicalQuerySourceRef`, `CanonicalQueryRow`, `UnifiedQueryDatasetResult`, `assemble_unified_query_dataset`.
- `src/app/services/seo/query_pipeline/pruning.py`
  - Rule-based pruning/basic annotation with version snapshots.
  - Key symbols: `run_query_pruning_and_basic_annotation`, `get_clean_query_set`, `get_pruning_slice`, `get_persisted_pruning_overlay`.
- `src/app/services/seo/query_pipeline/clustering.py`
  - Deterministic lexical query clustering and persistence.
  - Key symbols: `run_query_clustering`, `get_query_clusters`, `build_cluster_views_for_rows`, `PersistedQueryClusterView`.
- `src/app/services/seo/query_pipeline/hybrid.py`
  - Cluster-level inheritance over individual annotations.
  - Key symbols: `run_query_hybrid_annotation`, `get_persisted_hybrid_projection`, `safe_to_inherit`.
- `src/app/services/seo/query_pipeline/profiles.py`
  - Cluster profile extraction; projection-only in current code.
  - Key symbol: `run_query_profile_extraction`.
- `src/app/services/seo/query_pipeline/semantic.py`
  - Experimental semantic clustering comparison.
  - Key symbol: `run_semantic_clustering_experiment`.
- `src/app/services/seo/query_pipeline/diagnostics.py`
  - Dataclasses for diagnostics/results used across pipeline.
- `src/app/services/seo/query_pipeline/audit.py`
  - Audit/diagnostic helper module; inspect before changing diagnostics.

## Meaning, Matcher, Atoms

- `src/app/services/seo/meaning_extraction/types.py`
  - Canonical dataclasses for MVP meaning objects.
  - Key symbols: `CategoryMeaning`, `ProductProjection`, `QueryMeaning`.
- `src/app/services/seo/meaning_extraction/category_meaning.py`
  - Deterministic category meaning builder plus offline expressive cache reader.
  - Key symbols: `build_category_meaning`, `CategoryMeaningThresholds`.
- `src/app/services/seo/meaning_extraction/product_projection.py`
  - Deterministic SKU projection into category space.
  - Key symbols: `build_product_projection`, `ProductProjectionScopeError`.
- `src/app/services/seo/meaning_extraction/query_meaning.py`
  - Thin mapping from extracted query profiles into `QueryMeaning`.
  - Key symbol: `formalize_query_meaning`.
- `src/app/services/seo/category_bootstrap.py`
  - Category bootstrap orchestration: clustering, profile extraction, axes, query meanings, atoms, embeddings, readiness.
  - Key symbols: `run_category_bootstrap`, `run_category_bootstrap_background`, `get_category_bootstrap_status`, `get_latest_ready_category_axes`, `precompute_category_embeddings`.
- `src/app/services/seo/query_meaning_matcher/library.py`
  - Builds persistent query meaning library.
  - Key symbols: `build_query_meaning_library`, `list_query_meanings`, `QUERY_MEANING_RULES_VERSION`.
- `src/app/services/seo/query_meaning_matcher/matcher.py`
  - SKU/query matcher using meanings, embeddings, atoms, and judgments.
  - Key symbol: `run_meaning_aware_matcher`.
- `src/app/services/seo/query_meaning_matcher/embeddings.py`
  - Embedding persistence and deterministic local preview provider.
  - Key symbols: `LocalPreviewEmbeddingProvider`, `ensure_meaning_embedding`, `cosine_similarity`.
- `src/app/services/seo/query_meaning_matcher/canonical.py`
  - Canonicalization/hash/list helpers.
- `src/app/services/seo/meaning_atoms/storage.py`
  - Persistent atoms extraction/storage and merge helpers.
  - Key symbols: `build_query_atoms_for_category`, `ensure_sku_atoms`, `get_atoms_payload`, `merge_sku_and_vision_atoms`, `count_ready_query_atoms`, `ATOMS_SOURCE_VERSION`.
- `src/app/services/seo/experiments/meaning_atoms/*`
  - Experiment/shadow code for Atoms v1 schemas, matcher, vision, comparison, reports.
  - Key symbols: `v1.py::match_atoms_v1`, `schemas.py::SkuAtoms`, `schemas.py::QueryAtoms`, `vision.py::extract_vision_sku_atoms`.

## SKU Meaning And Product Workflow

- `src/app/services/seo/sku_meaning/evidence.py`
  - Builds SKU evidence pack from product and reviews.
  - Key symbols: `build_sku_evidence_pack`, `resolve_category_id`, `SkuMeaningScopeError`.
- `src/app/services/seo/sku_meaning/draft.py`
  - LLM SKU meaning draft with file cache.
  - Key symbols: `generate_sku_meaning_draft`, `SkuMeaningDraftStore`, `SKU_MEANING_PROMPT_VERSION`.
- `src/app/services/seo/sku_meaning/annotations.py`
  - Annotation/judgment persistence and eval export.
  - Key symbols: `save_annotation`, `get_annotation`, `list_candidate_queries`, `save_query_judgments`, `export_eval_dataset`.
- `src/app/services/seo/products.py`
  - Product SEO workflow: list, summary, analysis, query selection.
  - Key symbols: `list_seo_products`, `get_product_seo_summary`, `run_product_analysis`, `get_product_analysis_status`, `run_query_selection`, `get_query_selection`, `update_query_selection`.

## Generation

- `src/app/services/seo/generation/service.py`
  - WB card generation, parser, validator, relevance scoring, persistence.
  - Key symbols: `GENERATION_PROMPT_VERSION`, `GENERATION_VALIDATOR_VERSION`, `SEO_RELEVANCE_TARGET_SCORE`, `SEO_RELEVANCE_RETRY_SCORE`, `_build_generation_brief`, `parse_generated_card`, `validate_generated_card`, `build_seo_relevance_report`, `build_seo_relevance_v2_report`, `run_seo_generation`, `get_latest_generation`, `recalculate_latest_seo_relevance_v2`.
- `src/app/services/seo/generation/prompts/wb_card_system_v1.md`
  - Runtime system prompt asset used by `_load_system_prompt`.
- `docs/seo-module/24_wb_seo_generation_adaptation.md`
  - Design adaptation from imported `wb-seo-generator`.

## Provider Boundary

- `src/app/services/seo/providers/base.py`
  - Abstract provider interfaces.
  - Key symbols: `ChatMessage`, `ChatResponse`, `EmbeddingResponse`, `ChatProvider`, `EmbeddingProvider`.
- `src/app/services/seo/providers/openrouter.py`
  - OpenRouter implementation.
  - Key symbol: `OpenRouterProvider`.

## Placeholder/Legacy SKU Clustering

- `src/app/services/seo/clustering/representation.py`: `SkuRepresentation`, `build_sku_representation`.
- `src/app/services/seo/clustering/presegmentation.py`: `PreSegment`, `presegment_skus`.
- `src/app/services/seo/clustering/hdbscan_hook.py`: `HdbscanHookResult`, `run_hdbscan_placeholder`.
- `src/app/services/seo/clustering/service.py`: `cluster_skus_placeholder`.
- Evidence for placeholder status: symbols/defaults include `placeholder`, `todo_rule_based`, `trust_aware_placeholder`, `hdbscan_placeholder`; direct usage found only through `src/app/services/seo/__init__.py` export and `tests/test_seo_foundation.py`.

## Scoring

- `src/app/services/seo/scoring/preparation.py`
  - Runtime preparation diagnostics.
  - Key symbol: `run_query_scoring_preparation`.
- `src/app/services/seo/scoring/actual.py`
  - Runtime actual scoring diagnostics.
  - Key symbol: `run_query_actual_scoring`.
- `src/app/services/seo/scoring/service.py`
  - Persistence helper for score runs/scores.
  - Key symbols: `create_score_run`, `persist_query_score`, `ScoreComponents`.
  - Current caveat: direct search found it exported in `src/app/services/seo/scoring/__init__.py` and `src/app/services/seo/__init__.py`, but not used by `run_query_actual_scoring`.

## Frontend

- `frontend/lib/apiClient.ts`
  - Typed client functions for SEO endpoints.
  - Key symbols: `getCategoryBootstrapStatus`, `postCategoryBootstrapRun`, `getSeoProducts`, `getSeoProductSummary`, `postSeoProductAnalysisRun`, `postSeoQuerySelectionRun`, `getSeoQuerySelection`, `putSeoQuerySelection`, `postSeoGenerationRun`, `getSeoGenerationLatest`, `postSeoGenerationRecalculateSeoV2`.
- `frontend/app/app/project/[projectId]/seo/_components/SeoShell.tsx`
  - Shared shell/navigation/status UI.
- `frontend/app/app/project/[projectId]/seo/page.tsx`
  - SEO overview.
- `frontend/app/app/project/[projectId]/seo/categories/page.tsx`
  - Category list/status page.
- `frontend/app/app/project/[projectId]/seo/categories/[categoryId]/page.tsx`
  - Category corpus/import/bootstrap page.
- `frontend/app/app/project/[projectId]/seo/products/page.tsx`
  - Product list page.
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/page.tsx`
  - Product SEO summary/action page.
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/queries/page.tsx`
  - Query selection page.
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`
  - Generation brief/run/draft page.
- `frontend/app/app/project/[projectId]/seo/query-pipeline/debug/page.tsx`
  - Large debug UI for query pipeline.
- `frontend/app/app/project/[projectId]/seo/sku-meaning/page.tsx`
  - SKU meaning diagnostic/annotation tool.
- `frontend/app/app/project/[projectId]/wildberries/seo/query-import/page.tsx`
  - Older/import-focused route path.

## Migrations

- `alembic/versions/20260404_add_seo_query_ingestion_tables.py`
  - Creates `seo_query_batches`, `seo_queries_raw`, `seo_queries_normalized`.
- `alembic/versions/20260404_restore_remaining_seo_foundation_tables.py`
  - Creates foundation tables: query clusters/annotations, SKU clustering/profile tables, score tables, content/generation tables.
- `alembic/versions/20260414_add_query_cluster_memberships_and_enrich_query_clusters.py`
  - Adds query cluster enrichment columns and `seo_query_cluster_memberships`.
- `alembic/versions/20260414_evolve_seo_query_annotations_for_canonical_pruning.py`
  - Evolves annotations for canonical pruning fields.
- `alembic/versions/20260421_add_category_bootstrap_and_axes.py`
  - Creates category bootstrap/readiness/axes tables.
- `alembic/versions/20260421_add_query_meaning_library_and_embeddings.py`
  - Creates `seo_query_meanings` and `seo_meaning_embeddings`.
- `alembic/versions/20260421_add_sku_meaning_annotation_tables.py`
  - Creates SKU annotation/judgment/audit event tables.
- `alembic/versions/20260422_add_seo_atoms_and_query_sets.py`
  - Adds readiness atom-count column and creates `seo_meaning_atoms`, `seo_sku_query_sets`, `seo_sku_query_set_items`.

## Docs And Plans

- `docs/seo-module/00_master_context.md`: top-level constraints.
- `docs/seo-module/01_architecture.md`: architecture narrative.
- `docs/seo-module/01_architecture (not actual).md`: explicitly marked non-actual by filename.
- `docs/seo-module/02_roadmap.md`: staged product roadmap and Atoms v1 decision.
- `docs/seo-module/03_category_meaning_spec.md`, `04_product_projection_spec.md`, `05_query_meaning_spec.md`, `06_meaning_extraction_basis.md`, `07_meaning_extraction_plan.md`, `08_meaning_extraction_execution_report.md`, `08_meaning_extraction_implementation_plan.md`, `09_meaning_extraction_real_data_check.md`: meaning extraction specs/plans/reports.
- `docs/seo-module/10*` through `21*`: expressive LLM plans, datasets, reports, prompts, category run reports.
- `docs/seo-module/22_current_system_state_audit.md`: earlier system-state audit.
- `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md`: Atoms v1 target/shadow plan.
- `docs/seo-module/24_wb_seo_generation_adaptation.md`: adopted generation prompt/rules/model policy.
- `docs/seo-module/wb-seo-generator/*`: imported standalone reference generator docs/prompts/schemas/rules; not current EcomCore runtime architecture.

