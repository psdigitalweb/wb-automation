# SEO Dependency Map

## Runtime Dependency Chains

### Query Import And Corpus

```text
seo_query_import.py
  -> query_pipeline/ingestion.py
    -> query_pipeline/normalization.py
    -> models SeoQueryBatch / SeoQueryRaw / SeoQueryNormalized
```

Additional read path:

```text
seo_query_import.py
  -> query_pipeline/corpus.py
  -> category_bootstrap.py status/readiness helpers
```

Evidence:

- `src/app/routers/seo_query_import.py`
- `src/app/services/seo/query_pipeline/ingestion.py`
- `src/app/services/seo/query_pipeline/normalization.py`
- `src/app/models.py::SeoQueryBatch`, `SeoQueryRaw`, `SeoQueryNormalized`

### Canonical Query Pipeline

```text
unified_dataset.py
  -> SeoQueryBatch / SeoQueryNormalized
  -> products
  -> wb_search_query_terms / wb_search_query_daily
pruning.py
  -> unified_dataset.py
  -> SeoQueryAnnotation / SeoQueryAnnotationVersion
clustering.py
  -> pruning.py
  -> SeoQueryCluster / SeoQueryClusterMembership
hybrid.py
  -> clustering.py
  -> pruning overlay
  -> SeoQueryAnnotation.meta / SeoQueryAnnotationVersion
profiles.py
  -> hybrid.py
  -> clustering.py
```

Tight coupling:

- `unified_dataset.py` depends on product/category scoping via raw SQL joins.
- `hybrid.py` persists into `SeoQueryAnnotation.meta`, not a dedicated hybrid table.
- `profiles.py` consumes persisted hybrid state but does not persist profile entities.

### Category Bootstrap

```text
category_bootstrap.py
  -> query_pipeline/clustering.py
  -> query_pipeline/profiles.py
  -> expressive_llm/reviews_source.py
  -> meaning_extraction/category_meaning.py
  -> providers/openrouter.py
  -> query_meaning_matcher/library.py
  -> meaning_atoms/storage.py
  -> query_meaning_matcher/embeddings.py
  -> SeoCategoryBootstrapRun / SeoCategoryMatchingReadiness / SeoCategoryMeaningAxes
  -> SeoQueryMeaning / SeoMeaningEmbedding / SeoMeaningAtom
```

Hidden/cross-module dependencies:

- Category bootstrap uses both deterministic meaning extraction and newer persistent axes/query meaning/atoms infrastructure.
- It can call OpenRouter directly through `OpenRouterProvider` if LLM axes are requested.
- It uses file artifact roots under `settings.INTERNAL_DATA_DIR` or environment overrides.

### SKU Product Analysis

```text
products.py::run_product_analysis
  -> sku_meaning/evidence.py::build_sku_evidence_pack
  -> sku_meaning/draft.py::generate_sku_meaning_draft
  -> sku_meaning/annotations.py::save_annotation
  -> meaning_atoms/storage.py::ensure_sku_atoms
```

```text
products.py::get_product_seo_summary
  -> sku_meaning/evidence.py
  -> SeoSkuMeaningAnnotation
  -> SeoMeaningAtom
```

Cross-module leakage:

- Product workflow directly imports atoms, matcher, SKU annotation services, and evidence services.
- Product status labels are user-facing strings in `products.py`, not a separate i18n/view layer.

### Query Selection

```text
products.py::run_query_selection
  -> query_meaning_matcher/matcher.py::run_meaning_aware_matcher
  -> SeoSkuQuerySet / SeoSkuQuerySetItem
```

Matcher chain:

```text
matcher.py
  -> SeoSkuMeaningAnnotation
  -> SeoQueryMeaning
  -> SeoSkuQueryJudgment
  -> SeoCategoryMatchingReadiness
  -> embeddings.py::LocalPreviewEmbeddingProvider / ensure_meaning_embedding
  -> meaning_atoms/storage.py::get_atoms_payload / merge_sku_and_vision_atoms
  -> experiments/meaning_atoms/v1.py::match_atoms_v1
```

Important factual coupling:

- Production-facing matcher imports the experiment Atoms v1 matcher (`experiments/meaning_atoms/v1.py::match_atoms_v1`). This is a direct runtime dependency on code under an `experiments` package.
- Matcher uses local deterministic embeddings by default in interactive path, not network embeddings, via `LocalPreviewEmbeddingProvider`.

### Generation

```text
seo_generation.py
  -> generation/service.py::run_seo_generation
    -> sku_meaning/evidence.py::build_sku_evidence_pack
    -> SeoSkuQuerySet / SeoSkuQuerySetItem
    -> providers/openrouter.py::OpenRouterProvider
    -> generation/prompts/wb_card_system_v1.md
    -> SeoGenerationRun / SeoContentVersion
```

Frontend chain:

```text
frontend/.../products/[nmId]/generation/page.tsx
  -> frontend/lib/apiClient.ts::getSeoProductSummary
  -> getSeoQuerySelection
  -> getSeoGenerationLatest
  -> postSeoGenerationRun
```

Tight coupling:

- Generation brief expects selected query buckets from query set items.
- Generation uses product evidence but not directly the full product analysis UI summary.
- Frontend readiness uses `summary.product_status_label === "Gotov k podboru"` equivalent Russian string in code; backend emits the label in `products.py`.
- Frontend `briefPreview.generation_policy` hardcodes model IDs while backend uses settings `SEO_GENERATION_PRIMARY_MODEL` and `SEO_GENERATION_FALLBACK_MODEL`.

## External Provider Boundary

Provider interfaces:

- `src/app/services/seo/providers/base.py::ChatProvider`
- `src/app/services/seo/providers/base.py::EmbeddingProvider`

OpenRouter implementation:

- `src/app/services/seo/providers/openrouter.py::OpenRouterProvider`

Settings:

- `src/app/settings.py::OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_CHAT_MODEL`
- `OPENROUTER_EMBEDDING_MODEL`
- `SEO_GENERATION_*`

LLM call sites:

- `expressive_llm/category_extractive_service.py::run_single_category_expressive_extraction`
- `sku_meaning/draft.py::generate_sku_meaning_draft`
- `category_bootstrap.py::run_category_bootstrap`
- `query_meaning_matcher/library.py::build_query_meaning_library` when `use_llm=True`
- `meaning_atoms/storage.py::build_query_atoms_for_category` when `use_llm=True`, `ensure_sku_atoms` for SKU atom extraction with fallback
- `generation/service.py::run_seo_generation`

## Script Dependencies

Pipeline scripts:

- `scripts/run_query_pruning.py` -> `query_pipeline::run_query_pruning_and_basic_annotation`.
- `scripts/run_query_clustering.py` -> `query_pipeline::run_query_clustering`.
- `scripts/run_query_hybrid_annotation.py` -> `query_pipeline::run_query_hybrid_annotation`.
- `scripts/run_query_profile_extraction.py` -> `query_pipeline::run_query_profile_extraction`.
- `scripts/run_query_scoring_prep.py` -> `scoring/preparation.py::run_query_scoring_preparation`.
- `scripts/run_query_actual_scoring.py` -> `scoring/actual.py::run_query_actual_scoring`.
- `scripts/run_query_semantic_clustering.py` -> `query_pipeline/semantic.py::run_semantic_clustering_experiment`.
- `scripts/run_category_expressive_single_category.py` -> `expressive_llm/category_extractive_service.py::run_single_category_expressive_extraction`.

Spikes/benchmarks:

- `scripts/expressive_llm_eval.py`
- `scripts/sku_query_semantic_retrieval_spike.py`
- `scripts/query_llm_meaning_spike.py`
- `scripts/query_llm_model_comparison.py`
- `scripts/buyer_meaning_benchmark.py`

These scripts are useful evidence but should not be mistaken for runtime API paths without import/use confirmation.

## Docs/Plans Dependencies

- `docs/seo-module/00_master_context.md`, `01_architecture.md`, `02_roadmap.md` define high-level intent and invariants.
- `docs/seo-module/23_atoms_v1_design_and_implementation_plan.md` informs Atoms v1 code and experiments.
- `docs/seo-module/24_wb_seo_generation_adaptation.md` directly maps to `generation/service.py`, `settings.py`, `seo_generation.py`, and `generation/prompts/wb_card_system_v1.md`.
- `docs/seo-module/wb-seo-generator/*` is the imported reference for prompt/rules/model policy, but its standalone Excel/CLI architecture is not the runtime architecture.

## Hidden Dependencies And Coupling Inventory

- Raw SQL dependency on product/search/review tables appears in `unified_dataset.py`, `category_meaning.py`, `product_projection.py`, `sku_meaning/evidence.py`, `expressive_llm/reviews_source.py`.
- Runtime matcher imports experiment Atoms v1 code from `src/app/services/seo/experiments/meaning_atoms/v1.py`.
- Category readiness gates matcher and frontend actions through `SeoCategoryMatchingReadiness`.
- Generation is dependent on query selection status and query set items rather than raw imported queries.
- `SeoQueryAnnotation.meta` stores hybrid projection, creating a soft schema inside JSON.
- File caches under `INTERNAL_DATA_DIR` are part of meaning/generation-adjacent behavior but not reflected in DB migrations.

