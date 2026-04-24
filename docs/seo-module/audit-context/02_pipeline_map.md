# SEO Pipeline Map

## Pipeline A: Query CSV Import

Inputs:

- Uploaded/local CSV file, project id, WB category id.
- Evidence: `src/app/routers/seo_query_import.py::import_seo_query_csv_endpoint`, `src/app/services/seo/query_pipeline/ingestion.py::import_queries_from_csv`.

Stages:

1. CSV read/sniff/header resolution.
   - `ingestion.py::_read_csv`, `normalization.py::resolve_query_column`, `resolve_frequency_column`.
   - WB export headers are handled in code by query/frequency extraction helpers.
2. Text/frequency extraction and normalization.
   - `normalization.py::extract_query_text`, `extract_frequency`, `normalize_query_text`.
3. Batch persistence.
   - `SeoQueryBatch` starts as `status="processing"`, then becomes `status="completed"` in `import_queries_from_csv`.
4. Raw row persistence.
   - `SeoQueryRaw` rows keyed by `batch_id`, `row_number`.
5. Normalized dedupe persistence.
   - `SeoQueryNormalized` rows keyed by `batch_id`, `normalized_query`.
6. Diagnostics assembly.
   - `ImportDiagnostics` from `src/app/services/seo/query_pipeline/diagnostics.py`.

Outputs:

- `seo_query_batches`, `seo_queries_raw`, `seo_queries_normalized`.
- API response schemas in `src/app/schemas/seo_query_import.py`.

Persistence points:

- `src/app/models.py::SeoQueryBatch`
- `src/app/models.py::SeoQueryRaw`
- `src/app/models.py::SeoQueryNormalized`
- Migration: `alembic/versions/20260404_add_seo_query_ingestion_tables.py`.

Failure/retry/idempotency:

- Duplicate prevention is per batch/query via DB unique constraints and in-memory dedupe in ingestion.
- Batch status is updated to completed on success. Audit should inspect failure status handling in `import_queries_from_csv`; the summarized code path clearly sets processing/completed, but full error-state guarantees need review.

## Pipeline B: Unified Dataset -> Pruning

Inputs:

- Completed CSV normalized rows.
- WB search report data from `wb_search_query_terms` and `wb_search_query_daily`.
- Product category relation through `products.project_id`, `products.nm_id`, `products.subject_id`.
- Evidence: `src/app/services/seo/query_pipeline/unified_dataset.py::assemble_unified_query_dataset`.

Stages:

1. Load completed CSV batches.
   - `unified_dataset.py::_completed_csv_batches`, `_latest_completed_csv_batch`, `_load_csv_rows`.
2. Load WB terms/daily sources.
   - `unified_dataset.py::_load_wb_terms_rows`, `_load_wb_daily_rows`.
3. Canonical aggregation.
   - `CanonicalQueryRow`, `CanonicalQuerySourceRef`, `_CanonicalAccumulator`.
4. Heuristic flags and buckets.
   - `unified_dataset.py::_preparation_flags`, `_bucket_for_position`.
5. Pruning/basic annotation.
   - `pruning.py::run_query_pruning_and_basic_annotation`.

Outputs:

- Canonical row diagnostics and pruning annotations.
- Clean set via `pruning.py::get_clean_query_set`.
- Persisted overlay via `pruning.py::get_persisted_pruning_overlay`.

Persistence points:

- `SeoQueryAnnotation`
- `SeoQueryAnnotationVersion`
- Migrations: `20260404_restore_remaining_seo_foundation_tables.py`, `20260414_evolve_seo_query_annotations_for_canonical_pruning.py`.

Idempotency/versioning:

- `pruning.py::_semantic_snapshot_hash` and `_persist_annotations` create new `SeoQueryAnnotationVersion` only when the semantic snapshot changes.
- Overlay tracks stale persisted annotations as `stale_rows`.

Diagnostics:

- `QueryPruningDiagnostics`, `UnifiedQueryDatasetDiagnostics`.
- Debug route: `seo_query_pipeline_debug.py::get_seo_query_pipeline_debug_endpoint`.

## Pipeline C: Query Clustering

Inputs:

- Clean canonical query set from pruning.
- Evidence: `src/app/services/seo/query_pipeline/clustering.py::run_query_clustering`.

Stages:

1. Optionally refresh pruning when `persist=True`.
2. Build lexical deterministic cluster views.
   - `clustering.py::build_cluster_views_for_rows`.
3. Persist cluster rows.
   - `SeoQueryCluster`.
4. Delete/recreate membership rows for current scope.
   - `SeoQueryClusterMembership`.

Outputs:

- Persisted query clusters/memberships.
- `QueryClusteringResult` diagnostics.

Persistence points:

- `SeoQueryCluster`
- `SeoQueryClusterMembership`
- Migrations: `20260404_restore_remaining_seo_foundation_tables.py`, `20260414_add_query_cluster_memberships_and_enrich_query_clusters.py`.

Idempotency:

- Current implementation refreshes memberships by deleting/recreating rows for the scope. Cluster key generation is deterministic (`qcl:v1:<sha1>` as observed in code summary).

Important caveat:

- This is lexical/deterministic query clustering. Separate SKU clustering modules under `src/app/services/seo/clustering/*` are placeholders and not this query clustering path.

## Pipeline D: Hybrid Annotation

Inputs:

- Persisted pruning overlay.
- Persisted query clusters.
- Evidence: `src/app/services/seo/query_pipeline/hybrid.py::run_query_hybrid_annotation`.

Stages:

1. Optionally run clustering first when `persist=True`.
2. Load persisted pruning overlay and clusters.
3. Decide per-query provenance: individual, cluster-inherited, rejected, fallback.
4. Persist hybrid projection in annotation metadata and version history.

Outputs:

- Hybrid projection rows.
- `get_persisted_hybrid_projection` for downstream consumers.

Persistence points:

- `SeoQueryAnnotation.meta["hybrid_annotation"]`
- `SeoQueryAnnotationVersion`

Diagnostics:

- Hybrid rows in `seo_query_pipeline_debug.py`.

Failure behavior:

- Fallback provenance is explicit in output; exact failure semantics should be reviewed in `hybrid.py`.

## Pipeline E: Query Profile Extraction

Inputs:

- Persisted hybrid projection.
- Clean query set.
- Query clusters.
- Evidence: `src/app/services/seo/query_pipeline/profiles.py::run_query_profile_extraction`.

Stages:

1. Optionally refresh hybrid projection.
2. Extract cluster-level markers: product type, use case, attributes, language/expressive proxy.
3. Return `ExtractedClusterProfile` diagnostics.

Outputs:

- Runtime/diagnostic profiles only.

Persistence:

- Not persisted by `profiles.py`; `persist` is explicitly discarded in the code path (`del persist` noted from implementation summary).
- `SeoClusterProfile` and `SeoClusterProfileVersion` models exist in `src/app/models.py`, but direct search only found their class definitions, not runtime writes.

## Pipeline F: Meaning Extraction MVP

Inputs:

- Products table (`products.title`, `description`, `characteristics`, `sizes`, `colors`, `dimensions`, `subject_id`).
- Query profile extraction output.
- Optional offline expressive cache artifacts.

Stages:

1. Category meaning.
   - `category_meaning.py::build_category_meaning`.
   - Deterministic product-side aggregation; expressive part reads file cache via `CategoryExpressiveStore`, no LLM call in hot builder.
2. Product projection.
   - `product_projection.py::build_product_projection`.
   - Validates SKU category scope and extracts deterministic product type/use case/attribute/vibe signals.
3. Query meaning formalization.
   - `query_meaning.py::formalize_query_meaning`.
   - Thin mapping from `ExtractedClusterProfile`; language markers become MVP expressive-vibes proxy.

Outputs:

- Dataclass objects: `CategoryMeaning`, `ProductProjection`, `QueryMeaning`.

Persistence:

- The MVP dataclasses themselves do not persist in these modules.
- Persistent query meaning is handled separately by `query_meaning_matcher/library.py::build_query_meaning_library`.
- Category axes are handled by `category_bootstrap.py`.

## Pipeline G: Offline Category Expressive LLM

Inputs:

- Category reviews from WB review tables through `expressive_llm/reviews_source.py::fetch_category_review_scope`.
- Product titles for context.

Stages:

1. Build compact input.
   - `category_input_builder.py::build_category_expressive_input`.
2. Cache lookup by project/category/model/prompt/input hash.
   - `storage.py::CategoryExpressiveStore`.
3. If cache miss, call provider.
   - `category_extractive_service.py::run_single_category_expressive_extraction`.
4. Parse/validate evidence spans.
   - `category_output_parser.py::parse_and_validate_category_expressive_output`, `validation.py::validate_evidence_spans`.
5. Store artifacts on disk.

Outputs:

- File-based artifacts under `INTERNAL_DATA_DIR/seo_expressive_cache` or `SEO_EXPRESSIVE_CACHE_DIR`.

Runtime boundary:

- `category_extractive_service.py::run_single_category_expressive_extraction` docstring says it must not be used in runtime hot paths.
- `category_meaning.py::_load_llm_expressive_from_cache` only reads cache and catches failures.

## Pipeline H: Category Bootstrap

Inputs:

- Products, reviews, query clusters, query profiles, existing query import state.
- Optional LLM provider.
- Evidence: `src/app/services/seo/category_bootstrap.py::run_category_bootstrap`.

Stages:

1. Create/load `SeoCategoryBootstrapRun`.
2. Run query clustering.
3. Try query profile extraction.
4. Build evidence pack from product/query/review evidence.
5. Build/update category axes.
   - Deterministic or LLM-assisted path through `OpenRouterProvider.generate_chat`.
6. Build query meaning library.
   - `query_meaning_matcher/library.py::build_query_meaning_library`.
7. Build query atoms.
   - `meaning_atoms/storage.py::build_query_atoms_for_category`.
8. Precompute embeddings.
   - `query_meaning_matcher/embeddings.py::ensure_meaning_embedding`, often with `LocalPreviewEmbeddingProvider`.
9. Update readiness.
   - `SeoCategoryMatchingReadiness`.

Outputs:

- Bootstrap run/status.
- Category readiness.
- Category axes.
- Query meanings.
- Query atoms.
- Embeddings.

Persistence points:

- `SeoCategoryBootstrapRun`
- `SeoCategoryMatchingReadiness`
- `SeoCategoryMeaningAxes`
- `SeoQueryMeaning`
- `SeoMeaningAtom`
- `SeoMeaningEmbedding`

Failure/status:

- `run_category_bootstrap` has warnings and can mark status such as completed with warnings according to implementation summary.
- `seo_category_bootstrap.py` exposes background execution via `run_category_bootstrap_background`.

## Pipeline I: SKU Meaning -> Atoms -> Query Selection

Inputs:

- Product row and reviews.
- Category id.
- Existing query meaning library and readiness.
- Evidence: `src/app/services/seo/products.py::run_product_analysis`, `run_query_selection`; `sku_meaning/evidence.py::build_sku_evidence_pack`.

Stages:

1. Build SKU evidence pack.
   - `sku_meaning/evidence.py::build_sku_evidence_pack`.
   - `resolve_category_id` rejects mismatched category scope.
2. Generate SKU meaning draft.
   - `sku_meaning/draft.py::generate_sku_meaning_draft`.
   - Falls back to product-data-only payload in `products.py::run_product_analysis` if draft generation fails.
3. Save annotation.
   - `sku_meaning/annotations.py::save_annotation`.
4. Ensure SKU atoms and optional vision atoms.
   - `meaning_atoms/storage.py::ensure_sku_atoms`.
5. Run meaning-aware matcher.
   - `query_meaning_matcher/matcher.py::run_meaning_aware_matcher`.
6. Persist query set and items.
   - `products.py::run_query_selection` writes `SeoSkuQuerySet` and `SeoSkuQuerySetItem`.
7. User can edit/confirm selection.
   - `products.py::update_query_selection`.

Outputs:

- SKU annotation.
- SKU atoms/vision atoms.
- Draft/confirmed query set.

Persistence points:

- `SeoSkuMeaningAnnotation`
- `SeoMeaningAtom`
- `SeoSkuQuerySet`
- `SeoSkuQuerySetItem`
- `SeoSkuMeaningAuditEvent`

Diagnostics:

- Product summary blocks from `products.py::get_product_seo_summary`.
- Matcher diagnostics from `run_meaning_aware_matcher`.

## Pipeline J: Generation

Inputs:

- Confirmed `SeoSkuQuerySet` unless `allow_draft_query_set=True`.
- Product evidence from `build_sku_evidence_pack`.
- Selected `main_query_text`.
- Brand voice.
- Settings-driven primary/fallback model ids.
- Evidence: `src/app/services/seo/generation/service.py::run_seo_generation`.

Stages:

1. Build generation brief.
   - `_build_generation_brief`.
   - Loads product evidence, query set/groups, selected SEO targets, generation policy.
2. Persist generation run as running.
   - `SeoGenerationRun`.
3. Build chat messages.
   - `_build_messages` loads `src/app/services/seo/generation/prompts/wb_card_system_v1.md`.
4. Attempt generation.
   - Models: primary, primary retry, fallback; truncated by `SEO_GENERATION_MAX_ATTEMPTS`.
5. Parse output.
   - `parse_generated_card`.
6. Normalize report and validate.
   - `normalize_generated_card_report`, `validate_generated_card`.
7. Build SEO relevance reports.
   - `build_seo_relevance_report`, `build_seo_relevance_v2_report`.
8. Select final/best card.
9. Persist content version.
   - `SeoContentVersion(content_kind="llm_draft", status="needs_review")`.
10. Update run response/status/content link.

Outputs:

- `SeoGenerationRunResponse`.
- Latest generation via `get_latest_generation`.
- Recalculated SEO V2 via `recalculate_latest_seo_relevance_v2`.

Persistence points:

- `SeoGenerationRun.request_payload`
- `SeoGenerationRun.response_payload`
- `SeoGenerationRun.error_text`
- `SeoContentVersion.query_snapshot`
- `SeoContentVersion.score_breakdown`

Failure/retry:

- Validation errors feed retry hints.
- Failed generation leaves `SeoGenerationRun.status="failed"` and `error_text`.
- Successful generation creates draft content; no WB publish path is implemented in generation service.

