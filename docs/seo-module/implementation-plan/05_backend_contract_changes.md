# 05. Backend Contract Changes

Audience: backend lead
Date: 2026-04-23

Goal: make ownership unambiguous. Every decision has one producer and many readers.

---

## 1. Canonical matcher entrypoint

Single authoritative function on the candidate path:

```
services/seo/matcher_v2/api.py::run_matcher_v2(
    session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    category_profile: SeoCategoryProfile,
    embedding_provider: EmbeddingProvider,
    limit: int = 120,
    include_rejected: bool = True,
) -> SeoMatcherRun
```

Rules:

- This is the only production function allowed to assign a bucket, a score, a score component, or an eligibility verdict.
- It reads: `SeoSkuMeaningAnnotation`, SKU atoms, vision atoms, query atoms, `SeoQueryMeaning`, category profile, cluster memberships for demand signal.
- It writes: one `SeoMatcherRun` row + N `SeoMatcherResult` rows. That is all.
- It never writes `SeoSkuQuerySet` or `SeoSkuQuerySetItem`. A separate thin service reads the latest `SeoMatcherRun` and projects it into the query-set view if the caller wants a selection-friendly payload.
- It computes `quality_mode` via `services/seo/quality.py::infer_quality_mode(...)` and stores it on the run.

## 2. Canonical output contract

Shape (Pydantic model in `schemas/seo_matcher_v2.py`):

```
SeoMatcherRunResult:
  run_id: int
  project_id, category_id, nm_id: int
  matcher_version: str
  policy_version: str
  category_profile_version: int
  quality_mode: Literal["full","preview","degraded","fallback"]
  degraded_reasons: list[QualityReason]
  embedding_model: str
  readiness_snapshot: dict
  buckets: {
    primary: list[SeoMatcherResultItem]
    secondary: list[SeoMatcherResultItem]
    broad: list[SeoMatcherResultItem]
    rejected: list[SeoMatcherResultItem]
  }
  metrics: {
    scored_total: int
    eligible_total: int
    ineligible_total: int
    atoms_gate_enabled: bool
  }
```

Per-item:

```
SeoMatcherResultItem:
  query_display: str
  cluster_id: int | None
  cluster_key: str
  query_meaning_id: int
  bucket: Literal["primary","secondary","broad","rejected"]
  eligibility_verdict: Literal["eligible","ineligible_hard_conflict","ineligible_missing_required","ineligible_exclusion"]
  score: float
  score_components: dict[str, float]
  matched_atoms: list[str]
  missing_atoms: list[str]
  conflict_atoms: list[str]
  reasons: list[str]
  ranking_value_used: float | None
```

All consumers (UI, generation, eval) read this contract. They do not re-derive buckets.

## 3. Who may compute bucket / score / explanation

**Allowed:**

- `services/seo/matcher_v2/api.py::run_matcher_v2` and its internal stages (`eligibility.py`, `bucket_cap.py`, `soft_score.py`, `demand_ordering.py`).

**Not allowed:**

- `products.py::run_query_selection` — becomes a thin wrapper that calls `run_matcher_v2`, projects the result into `SeoSkuQuerySet` + `SeoSkuQuerySetItem`, and does nothing else decision-related.
- `generation/service.py` — reads `SeoMatcherRun.buckets` via a new helper; does not call the old matcher; does not re-score.
- `seo_query_meaning_matcher` router endpoint `/matcher/preview` — becomes a thin call-forward to `run_matcher_v2` behind the candidate-flow flag; does not re-derive.
- `scoring/preparation.py`, `scoring/actual.py` — moved under `diagnostics/scoring/`; not imported by runtime routers.
- `experiments/meaning_atoms/*` — frozen; not imported by production code. The matcher inputs come from `services/seo/atoms/v1/` instead.

**Explicitly frozen (cannot compute bucket/score anywhere, under any flag):**

- `services/seo/clustering/*`
- `scoring/service.py::create_score_run`, `scoring/service.py::persist_query_score`

## 4. Quality mode propagation contract

Single source of truth: `services/seo/quality.py::infer_quality_mode(state: QualityState) -> (QualityMode, list[QualityReason])`.

Call sites that *must* invoke it and persist the result:

- `category_bootstrap.py::run_category_bootstrap` — on `SeoCategoryMatchingReadiness`.
- `sku_meaning/draft.py::generate_sku_meaning_draft` — on `SeoSkuMeaningAnnotation`.
- `matcher_v2/api.py::run_matcher_v2` — on `SeoMatcherRun`.
- `generation/service.py::run_seo_generation` — on `SeoContentVersion`.

Propagation rule: each layer computes its own mode but must include `upstream_mode_min` as a `degraded_reason` when an upstream row was worse than its own computed mode. Example: if SKU annotation was `fallback` and the matcher inputs look OK, the matcher run is `degraded` (not `full`) with reason `upstream_sku_annotation_mode=fallback`.

`LocalPreviewEmbeddingProvider` forces the mode ceiling to `preview` at the provider level — not by documentation, by a method on the provider that returns `max_mode = preview`.

## 5. Eval enforcement

Single endpoint:

```
POST /projects/{project_id}/seo/eval/matcher/run
body: { category_id: int, label_set_id: int }
```

Behavior:

- Loads labels.
- Either uses the latest available `SeoMatcherRun` per labeled SKU or triggers a fresh run per SKU (parameterized).
- Computes metrics.
- Writes `seo_eval_runs`.
- If thresholds are met, flips `SeoCategoryMatchingReadiness.eligibility_tier`. Tier downgrade is allowed if a rerun falls below thresholds.
- Returns metrics + old_tier + new_tier.

Other services never set `eligibility_tier` directly. The eval endpoint is the only writer of that column.

## 6. Generation state checks

Single endpoint for promotion:

```
POST /projects/{project_id}/seo/generation/{content_version_id}/promote
body: { target_state: "candidate" | "approved" }
```

Server-side gate logic (sole authority for `content_kind` transitions):

- `preview → candidate`:
  - category `eligibility_tier >= eligible_for_preview`.
  - latest `seo_eval_runs` for the category is `preview_gate_pass` or `acceptance_gate_pass`.
  - `seo_generation_human_review.verdict in {accept_with_edits, accept}` with rubric scores ≥ thresholds.
  - content version's `quality_mode != fallback`.
- `candidate → approved`:
  - category `eligibility_tier == acceptance_passed`.
  - explicit operator sign-off in request body.
- `approved → published`: rejected. Returns 400 with "published state not enabled."

Generation `run_seo_generation` itself:

- Always writes `content_kind = "preview"`.
- Never writes `candidate`, `approved`, or `published` directly.
- Always sets `publishable = false`.
- Applies `SEO_GENERATION_MAX_ATTEMPTS = 1` for validator errors only. Does not retry against its own relevance score.

## 7. Public service boundary changes

### 7.1 `products.py`

- `run_product_analysis` — unchanged public signature; internally records `quality_mode` on the SKU annotation.
- `run_query_selection` — becomes a projection over `run_matcher_v2`. Behavior flagged by `flow ∈ {current, candidate}`. Current still calls the old matcher; candidate calls `run_matcher_v2`.
- `get_product_seo_summary` — adds `quality_mode` and `matcher_run_id` in the response payload.
- `update_query_selection` — updates `selection_state` (Approved / Draft) explicitly. Never touches `trust_state` (that is eval's job).

### 7.2 `generation/service.py`

- `run_seo_generation` — consumes `SeoMatcherRun` via helper `load_latest_matcher_run_for_sku`, not by recomputing the brief from raw meanings.
- `_build_generation_brief` — now receives a `SeoMatcherRunResult` dataclass instead of walking query sets manually.
- `build_seo_relevance_report` / `build_seo_relevance_v2_report` — relabeled in schemas: `kind = "internal_lint"`, `is_quality_gate = False`. No behavior change.
- Remove retry-on-relevance. The loop in `run_seo_generation` that raises retry hints from low relevance score is deleted.

### 7.3 `query_meaning_matcher/matcher.py`

- Stays as the *current-path* matcher during iteration 1.
- Marked for deprecation in iteration 2. Sunset once candidate path is default.

### 7.4 New services

- `services/seo/matcher_v2/api.py` — entrypoint, stage orchestrator.
- `services/seo/matcher_v2/stages/eligibility.py`, `bucket_cap.py`, `soft_score.py`, `demand_ordering.py`.
- `services/seo/category_profile.py` — loader.
- `services/seo/atoms/v1/` — schemas, matcher helpers, guards, llm_extractors, vision (promoted from `experiments/`).
- `services/seo/quality.py` — `infer_quality_mode` + enum.
- `services/seo/eval/harness.py` — metric computation.

### 7.5 Routers

- New router `routers/seo_matcher_v2.py` with:
  - `POST /matcher/v2/run`
  - `GET /matcher/v2/runs/{run_id}`
- New router `routers/seo_eval.py` with:
  - `POST /eval/matcher/run`
  - `GET /eval/matcher/runs/{run_id}`
- New router endpoints on `seo_generation.py`:
  - `POST /generation/{id}/promote`
  - `POST /generation/{id}/human-review`
- New router `routers/seo_compare.py` with:
  - `GET /compare/matcher`
  - `GET /compare/generation`

### 7.6 Deprecated / moved

- `services/seo/scoring/service.py::create_score_run`, `persist_query_score` — moved to `diagnostics/scoring/` with import guard for production routers.
- `services/seo/clustering/*` — import guard at module load; raises if imported from a production router.
- `services/seo/experiments/meaning_atoms/*` — frozen; no new imports accepted; CI check added.
- `seo_meaning_extraction_debug` router — kept as diagnostics, untouched.

## 8. Contract rules stated openly

- "`SeoMatcherRun` is the matcher. Anything else that looks like a matcher result is a projection."
- "`quality_mode` is a mandatory property of every decision row. Services that omit it must be fixed, not tolerated."
- "No category-specific term list is allowed in production `services/` modules. It lives in `SeoCategoryProfile`."
- "Generation's relevance report is an internal lint. It is never a promotion gate."
- "`eligibility_tier` is written only by the eval endpoint. `content_kind` transitions are written only by the promote endpoint."

## 9. Readers and writers summary table

| Field / row                                   | Writer                                         | Readers                                           |
|-----------------------------------------------|------------------------------------------------|---------------------------------------------------|
| `SeoMatcherRun` / `SeoMatcherResult`          | `run_matcher_v2` only                          | query selection projection, generation, eval, compare, UI |
| `SeoSkuQuerySet.selection_state`              | `update_query_selection`                       | generation gate, UI                                |
| `SeoSkuQuerySet.trust_state`                  | eval endpoint                                  | generation gate, UI                                |
| `SeoSkuQuerySetItem` (candidate path)         | projection from `SeoMatcherRun`                | UI, generation brief                               |
| `SeoContentVersion.content_kind`              | `POST /generation/{id}/promote`                | UI, downstream exports                             |
| `SeoContentVersion.quality_mode`              | `run_seo_generation` at write                  | UI, promotion gate                                 |
| `SeoCategoryMatchingReadiness.eligibility_tier` | eval endpoint only                            | matcher_v2, generation gate, UI                    |
| `SeoCategoryProfile` (active version)         | profile admin tooling / seed import            | matcher_v2, generation brief, UI                   |
| `seo_eval_labels`                             | import tool + manual labeling endpoint         | eval endpoint                                       |
| `seo_eval_runs`                               | eval endpoint                                  | UI, promotion gate                                  |
| `seo_generation_human_review`                 | `POST /generation/{id}/human-review`           | promotion gate, UI                                  |
| `seo_quality_events` (if included)            | any service emitting events                    | support diagnostics                                 |

## 10. What is deprecated

Deprecated in iteration 1 (still compiles, still runs, marked frozen, import-guarded):

- `services/seo/clustering/*`
- `services/seo/scoring/service.py::create_score_run`, `services/seo/scoring/service.py::persist_query_score`

Deprecated in iteration 2 (when candidate path is default):

- `services/seo/query_meaning_matcher/matcher.py::run_meaning_aware_matcher`
- `SeoSkuQuerySet.status` column
- Direct reads of `SeoQueryAnnotation.meta["hybrid_annotation"]` from decision paths

To be deleted in a later iteration (not in this plan):

- Frozen clustering/score model classes and tables.
- The deprecated current-path matcher.
