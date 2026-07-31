# SEO Data Model Map

## Scope Invariant

All SEO scoped models use `(project_id, category_id)`, where `category_id` is the WB subject/category scope. It is explicitly not a foreign key to internal category tables.

Evidence:

- `src/app/models.py::SEO_CATEGORY_SCOPE_COMMENT`
- `src/app/models.py::SeoProjectCategoryScopedMixin`

## Query Ingestion Tables

- `SeoQueryBatch` -> `seo_query_batches`
  - Fields include source metadata, status, row counts, `meta`.
  - Migration: `alembic/versions/20260404_add_seo_query_ingestion_tables.py`.
  - Used by `query_pipeline/ingestion.py::import_queries_from_csv`, `unified_dataset.py`, import router, bootstrap readiness.
- `SeoQueryRaw` -> `seo_queries_raw`
  - Raw CSV row storage.
  - Unique constraint: `(batch_id, row_number)` in migration.
  - Used by ingestion/import API.
- `SeoQueryNormalized` -> `seo_queries_normalized`
  - Normalized/deduped query rows.
  - Unique constraint: `(batch_id, normalized_query)` in migration.
  - Used by pruning and older foundation score relation.

## Query Annotation And Clustering Tables

- `SeoQueryAnnotation` -> `seo_query_annotations`
  - Carries normalized query text, pruning status, query type, intent type, reason codes, metadata.
  - Migration base: `20260404_restore_remaining_seo_foundation_tables.py`.
  - Migration evolution: `20260414_evolve_seo_query_annotations_for_canonical_pruning.py`.
  - Used by `pruning.py`, `hybrid.py`, `sku_meaning/annotations.py` candidate/judgment relation.
- `SeoQueryAnnotationVersion` -> `seo_query_annotation_versions`
  - Version snapshots for annotation changes.
  - Used by `pruning.py` and `hybrid.py`.
- `SeoQueryCluster` -> `seo_query_clusters`
  - Query cluster header.
  - Unique scope/key constraint in migration: `(project_id, category_id, cluster_key)`.
  - Enriched by migration `20260414_add_query_cluster_memberships_and_enrich_query_clusters.py`.
  - Used by `query_pipeline/clustering.py`, `query_meaning_matcher/library.py`.
- `SeoQueryClusterMembership` -> `seo_query_cluster_memberships`
  - Query-to-cluster membership.
  - Created by migration `20260414_add_query_cluster_memberships_and_enrich_query_clusters.py`.
  - Used by `query_pipeline/clustering.py`.

## SKU Clustering And Cluster Profile Tables

- `SeoSkuClusterRun` -> `seo_sku_cluster_runs`
- `SeoSkuCluster` -> `seo_sku_clusters`
- `SeoSkuClusterAssignment` -> `seo_sku_cluster_assignments`
- `SeoClusterProfile` -> `seo_cluster_profiles`
- `SeoClusterProfileVersion` -> `seo_cluster_profile_versions`

Evidence:

- ORM classes in `src/app/models.py`.
- Tables created by `alembic/versions/20260404_restore_remaining_seo_foundation_tables.py`.

Current status:

- Partially implemented/placeholder. Model defaults include `placeholder`, `todo_rule_based`, `trust_aware_placeholder`, and `hdbscan_placeholder`.
- Direct search found `SeoClusterProfile`/`SeoClusterProfileVersion` only in model declarations.
- SKU clustering service code is in `src/app/services/seo/clustering/*`, with key symbol `cluster_skus_placeholder`, used only through exports/tests based on direct search.

## Scoring Tables

- `SeoScoreRun` -> `seo_score_runs`
- `SeoQueryScore` -> `seo_query_scores`
- `SeoScoreExplanation` -> `seo_score_explanations`

Evidence:

- ORM classes in `src/app/models.py`.
- Tables created by `20260404_restore_remaining_seo_foundation_tables.py`.
- Persistence helper: `src/app/services/seo/scoring/service.py::create_score_run`, `persist_query_score`.

Current status:

- Scoring diagnostics are implemented in `src/app/services/seo/scoring/preparation.py::run_query_scoring_preparation` and `actual.py::run_query_actual_scoring`.
- Direct search found `create_score_run`/`persist_query_score` exported in `src/app/services/seo/__init__.py` and `src/app/services/seo/scoring/__init__.py`, but not called by `run_query_actual_scoring`.
- Therefore score persistence appears partially implemented and not wired into the active scoring pipeline.

## Content Generation Tables

- `SeoContentVersion` -> `seo_content_versions`
  - Stores generated title/description, content kind/status, query snapshot, score breakdown.
  - Used by `generation/service.py::run_seo_generation`, `get_latest_generation`, `recalculate_latest_seo_relevance_v2`.
- `SeoGenerationRun` -> `seo_generation_runs`
  - Stores request/response/error/provider/model/content link.
  - Used by `generation/service.py::run_seo_generation`.

Migration:

- `alembic/versions/20260404_restore_remaining_seo_foundation_tables.py`.

Current status:

- Implemented generation draft persistence.
- No publish-to-WB table/path found in generation service.

## Query Meaning And Embedding Tables

- `SeoQueryMeaning` -> `seo_query_meanings`
  - Persistent query meaning library.
  - Migration: `20260421_add_query_meaning_library_and_embeddings.py`.
  - Used by `query_meaning_matcher/library.py`, `matcher.py`, `meaning_atoms/storage.py`.
- `SeoMeaningEmbedding` -> `seo_meaning_embeddings`
  - Generic persisted embeddings for query/category/SKU meaning entities.
  - Migration: `20260421_add_query_meaning_library_and_embeddings.py`.
  - Used by `query_meaning_matcher/embeddings.py::ensure_meaning_embedding`.
- `SeoMeaningAtom` -> `seo_meaning_atoms`
  - Generic atoms table for SKU/query/vision atoms.
  - Migration: `20260422_add_seo_atoms_and_query_sets.py`.
  - Used by `meaning_atoms/storage.py`, `products.py`, `query_meaning_matcher/matcher.py`.

Mismatch with docs:

- `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md` describes separate `seo_sku_atoms`, `seo_query_atoms`, and matcher-run storage.
- Actual migration/code uses generic `seo_meaning_atoms` and persists query set items, but no dedicated matcher-run table is evident.

## Category Bootstrap Tables

- `SeoCategoryBootstrapRun` -> `seo_category_bootstrap_runs`
  - Bootstrap run status/payload/errors.
  - Migration: `20260421_add_category_bootstrap_and_axes.py`.
  - Used by `category_bootstrap.py::run_category_bootstrap`.
- `SeoCategoryMatchingReadiness` -> `seo_category_matching_readiness`
  - Category readiness summary.
  - Migration: `20260421_add_category_bootstrap_and_axes.py`, extended by `20260422_add_seo_atoms_and_query_sets.py` with ready atoms count.
  - Used by `category_bootstrap.py`, `products.py`, `query_meaning_matcher/matcher.py`.
- `SeoCategoryMeaningAxes` -> `seo_category_meaning_axes`
  - Category axes payload/version/provider/model/input hash.
  - Migration: `20260421_add_category_bootstrap_and_axes.py`.
  - Used by `category_bootstrap.py::get_latest_ready_category_axes`, `_upsert_axes`.

## SKU Meaning And Query Selection Tables

- `SeoSkuMeaningAnnotation` -> `seo_sku_meaning_annotations`
  - Persistent SKU meaning payload/status/evidence/draft metadata.
  - Migration: `20260421_add_sku_meaning_annotation_tables.py`.
  - Used by `sku_meaning/annotations.py`, `products.py`, `meaning_atoms/storage.py`.
- `SeoSkuQueryJudgment` -> `seo_sku_query_judgments`
  - Manual query judgments tied to SKU annotation/query/cluster.
  - Migration: `20260421_add_sku_meaning_annotation_tables.py`.
  - Used by `sku_meaning/annotations.py` and `query_meaning_matcher/matcher.py`.
- `SeoSkuMeaningAuditEvent` -> `seo_sku_meaning_audit_events`
  - Audit trail for annotation changes.
  - Migration: `20260421_add_sku_meaning_annotation_tables.py`.
  - Used by `sku_meaning/annotations.py::_add_audit_event`.
- `SeoSkuQuerySet` -> `seo_sku_query_sets`
  - Draft/confirmed selected query set per SKU/category/status.
  - Migration: `20260422_add_seo_atoms_and_query_sets.py`.
  - Used by `products.py` and `generation/service.py`.
- `SeoSkuQuerySetItem` -> `seo_sku_query_set_items`
  - Items in query set with bucket/score/state/reasons.
  - Migration: `20260422_add_seo_atoms_and_query_sets.py`.
  - Used by `products.py` and `generation/service.py`.

Notable caveat:

- Migration unique constraint `uq_seo_sku_query_sets_scope_status` is on `(project_id, category_id, nm_id, status)`. This supports one draft and one confirmed set per scope/status.

## External Product/Review/Search Dependencies

SEO code depends on non-SEO tables/models:

- `products`
  - `src/app/models.py::Product`
  - Fields consumed include `project_id`, `nm_id`, `subject_id`, `title`, `description`, `characteristics`, `sizes`, `colors`, `dimensions`, `pics`, `brand`, `subject_name`, `vendor_code`, `rating`, `feedbacks`.
  - Product fields are added by migrations such as `alembic/versions/e1dcde5e611e_add_brand_to_products.py`, `add_product_details_fields.py`, `add_unique_products_project_nm_id.py`, `add_project_id_to_data_tables.py`.
- WB search report tables
  - Created by `alembic/versions/add_wb_search_report_mvp_001.py`.
  - Used by `unified_dataset.py::_load_wb_terms_rows`, `_load_wb_daily_rows`.
- WB feedback/review tables
  - Created/evolved by `alembic/versions/20260219_add_wb_communications_tables.py` and `add_wb_feedback_snapshots_cols.py`.
  - Used by `expressive_llm/reviews_source.py::fetch_category_review_scope` and `sku_meaning/evidence.py::_fetch_sku_reviews`.

## Model/Migration Gaps To Inspect

- `SeoClusterProfile` and `SeoClusterProfileVersion` tables exist but current profile extraction does not persist them.
- Score persistence tables and service exist, but current actual scoring appears diagnostics-only.
- Atoms v1 docs name separate atom and matcher-run tables; code uses a generic `SeoMeaningAtom` table and query-set persistence.
- Some migrations are untracked in current `git status`; audit should verify actual DB state before relying on them.
- Product/review/search dependencies are mostly accessed via raw SQL/text queries in services, creating possible schema drift risk.

