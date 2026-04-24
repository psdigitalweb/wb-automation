# Key Snippets

Short excerpts only. Use these as starting points for code inspection.

## Category Scope Is WB Subject Scope

File: `src/app/models.py`

```python
class SeoProjectCategoryScopedMixin:
    """Adds project_id plus WB category scope, never internal_categories.id."""
```

Why it matters:

- Every scoped SEO entity uses this invariant. Passing internal category ids would corrupt/miss data.

## SKU Clustering Is Placeholder

File: `src/app/models.py`

```python
presegmentation_strategy = Column(String(64), nullable=False, server_default="todo_rule_based")
representation_strategy = Column(String(64), nullable=False, server_default="trust_aware_placeholder")
clustering_backend = Column(String(64), nullable=False, server_default="hdbscan_placeholder")
```

Related file: `src/app/services/seo/clustering/service.py::cluster_skus_placeholder`.

Why it matters:

- SKU clustering tables exist, but runtime should not be audited as finished SKU clustering.

## Query Ingestion Entry

File: `src/app/services/seo/query_pipeline/ingestion.py`

```python
def import_queries_from_csv(session, csv_path, project_id, category_id, ...):
```

Related symbols:

- `SeoQueryBatch`
- `SeoQueryRaw`
- `SeoQueryNormalized`
- `ImportDiagnostics`

Why it matters:

- This is the first persistence point for imported query data.

## Normalization Boundary

File: `src/app/services/seo/query_pipeline/normalization.py`

```python
def normalize_query_text(value):
```

Observed behavior from implementation:

- Strip/casefold.
- Replace `yo`/Russian `yo` equivalent by normalized form.
- Remove punctuation.
- Collapse whitespace.

Why it matters:

- This normalized string becomes a key across ingestion, pruning, query sets, and generation selection.

## Pruning Versioning

File: `src/app/services/seo/query_pipeline/pruning.py`

```python
def run_query_pruning_and_basic_annotation(...):
```

Related symbols:

- `_semantic_snapshot_hash`
- `_persist_annotations`
- `SeoQueryAnnotation`
- `SeoQueryAnnotationVersion`

Why it matters:

- This is the clearest implemented traceability/versioning layer.

## Query Clustering Persists Memberships

File: `src/app/services/seo/query_pipeline/clustering.py`

```python
def run_query_clustering(...):
```

Related symbols:

- `build_cluster_views_for_rows`
- `get_query_clusters`
- `SeoQueryCluster`
- `SeoQueryClusterMembership`

Why it matters:

- This is the implemented clustering path. It is lexical/deterministic.

## Profile Extraction Does Not Persist Profiles

File: `src/app/services/seo/query_pipeline/profiles.py`

```python
def run_query_profile_extraction(...):
```

Implementation note from inspected code:

- `persist` is discarded and profiles are returned in diagnostics.

Related models:

- `src/app/models.py::SeoClusterProfile`
- `src/app/models.py::SeoClusterProfileVersion`

Why it matters:

- Model existence does not mean profile persistence is wired.

## Category Expressive LLM Is Offline/Cache-First

File: `src/app/services/seo/expressive_llm/category_extractive_service.py`

```python
def run_single_category_expressive_extraction(...):
    """Run a single-category offline extraction (cache-first).

    This function MUST NOT be used in runtime hot paths.
    """
```

File: `src/app/services/seo/expressive_llm/storage.py`

```python
class CategoryExpressiveStore:
    """File-based cache for category expressive artifacts."""
```

Why it matters:

- Expressive category meaning can influence runtime via cached artifacts, not DB rows.

## Product Projection Scope Guard

File: `src/app/services/seo/meaning_extraction/product_projection.py`

```python
if subject_id is not None and int(subject_id) != int(category_id):
    raise ProductProjectionScopeError(...)
```

Related symbol:

- `sku_meaning/evidence.py::resolve_category_id`.

Why it matters:

- SKU/category mismatch is guarded in product meaning paths.

## Query Meaning Library Version

File: `src/app/services/seo/query_meaning_matcher/library.py`

```python
QUERY_MEANING_RULES_VERSION = "query_meaning_rules_v1_visual_motifs"
```

Related symbol:

- `build_query_meaning_library`

Why it matters:

- Persistent query meanings are versioned by rules/version/input hash rather than only by cluster id.

## Local Preview Embeddings

File: `src/app/services/seo/query_meaning_matcher/embeddings.py`

```python
class LocalPreviewEmbeddingProvider(EmbeddingProvider):
    embedding_model = "local_preview_embedding_v4_visual_motifs"
```

Why it matters:

- Interactive matcher can run without hundreds of network embedding calls; this also means scores are not necessarily production embedding scores.

## Runtime Matcher Uses Experiment Atoms V1

File: `src/app/services/seo/query_meaning_matcher/matcher.py`

Related imports/symbols:

- `meaning_atoms/storage.py::get_atoms_payload`
- `meaning_atoms/storage.py::merge_sku_and_vision_atoms`
- `experiments/meaning_atoms/v1.py::match_atoms_v1`

Why it matters:

- Experiment code is on the runtime path.

## Atoms Persistent Storage

File: `src/app/services/seo/meaning_atoms/storage.py`

```python
ATOMS_SOURCE_VERSION = "production_atoms_v1_visual_motifs"
QUERY_ATOMS_SOURCE_VERSION = "query_atoms_from_meaning_v0"
SKU_ATOMS_SOURCE_VERSION = "sku_atoms_from_meaning_v0"
VISION_ATOMS_SOURCE_VERSION = "sku_vision_atoms_v0"
```

Related symbols:

- `build_query_atoms_for_category`
- `ensure_sku_atoms`
- `get_atoms_payload`
- `SeoMeaningAtom`

Why it matters:

- Actual storage uses generic `seo_meaning_atoms`, not the separate atom tables described in the Atoms v1 plan.

## Product Query Selection Persistence

File: `src/app/services/seo/products.py`

```python
def run_query_selection(...):
    matcher = run_meaning_aware_matcher(...)
    ...
    query_set.matcher_version = MEANING_AWARE_MATCHER_VERSION
    query_set.atoms_version = matcher.diagnostics.atoms_version
```

Related models:

- `SeoSkuQuerySet`
- `SeoSkuQuerySetItem`

Why it matters:

- This is the bridge from matcher output to generation-ready selected queries.

## Generation Requires Confirmed Query Set

File: `src/app/services/seo/generation/service.py`

```python
elif not allow_draft:
    stmt = stmt.where(SeoSkuQuerySet.status == "confirmed")
...
raise SeoGenerationError("Confirmed query set is required before generation")
```

Related symbol:

- `_build_generation_brief`

Why it matters:

- Generation is gated by query selection status unless explicitly allowed.

## Generation Model Policy

File: `src/app/settings.py`

```python
SEO_GENERATION_PRIMARY_MODEL = os.getenv("SEO_GENERATION_PRIMARY_MODEL", "anthropic/claude-haiku-4.5")
SEO_GENERATION_FALLBACK_MODEL = os.getenv("SEO_GENERATION_FALLBACK_MODEL", "anthropic/claude-sonnet-4.5")
SEO_GENERATION_MAX_ATTEMPTS = _get_env_int("SEO_GENERATION_MAX_ATTEMPTS", 3)
```

File: `src/app/services/seo/generation/service.py`

```python
GENERATION_PROMPT_VERSION = "wb_card_system_v1"
GENERATION_VALIDATOR_VERSION = "wb_card_validator_v1"
```

Why it matters:

- Imported WB generator model policy is adapted as settings-driven backend behavior.

## Generation Persistence

File: `src/app/services/seo/generation/service.py`

```python
content_version = SeoContentVersion(
    content_kind="llm_draft",
    ...
    status="needs_review",
)
```

Related symbols:

- `SeoGenerationRun`
- `SeoContentVersion`
- `get_latest_generation`

Why it matters:

- Generation writes reviewable drafts; no publish-to-WB path is in this service.

## OpenRouter Boundary

File: `src/app/services/seo/providers/base.py`

```python
class ChatProvider(ABC):
    @abstractmethod
    def generate_chat(...):
```

File: `src/app/services/seo/providers/openrouter.py`

```python
class OpenRouterProvider(ChatProvider, EmbeddingProvider):
```

Why it matters:

- LLM/provider access is abstracted, but most concrete runtime paths still use `OpenRouterProvider`.

