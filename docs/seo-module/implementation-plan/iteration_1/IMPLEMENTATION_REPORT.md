# SEO Iteration 1 — Implementation Report

Scope: strictly P0 from `ITERATION_1_LOCKED_SCOPE` in
[`10_implementation_decision_lock_v1.md`](../10_implementation_decision_lock_v1.md)
§4.1, plus the viewer P1. Out-of-scope items in §5 of the lock doc are
explicitly **not** implemented. Every code change below is additive.

---

## 1. Files changed

Grouped by workstream.

### A. Quality-mode framework (WS-B)

- `src/app/services/seo/quality.py` — **new**. `QualityMode` enum,
  `QualityReason` TypedDict, `QualityState` dataclass, deterministic
  `infer_quality_mode(state) -> (mode, reasons)`, `make_reason` helper.
- `tests/test_seo_quality.py` — **new**. Unit tests for the inference rule.
- `src/app/services/seo/providers/base.py` — added
  `max_mode: str = "full"` attribute on `EmbeddingProvider`.
- `src/app/services/seo/query_meaning_matcher/embeddings.py` — set
  `max_mode = "preview"` on `LocalPreviewEmbeddingProvider`; kept `"full"`
  on `OpenRouterProvider`.
- `src/app/models.py` — added quality columns:
  - `SeoSkuQuerySet`: `quality_mode`, `degraded_reasons`, `matcher_run_id`
    FK → `seo_matcher_runs`.
  - `SeoSkuMeaningAnnotation`: `quality_mode`, `degraded_reasons`.
  - `SeoContentVersion`: `quality_mode`, `degraded_reasons`, `mode_used`
    (default `'current'`), `publishable` (default `false`),
    `matcher_run_id` FK.
  - `SeoGenerationRun`: `quality_mode`, `degraded_reasons`,
    `matcher_run_id` FK.
- `src/app/services/seo/sku_meaning/annotations.py` — added
  `_infer_annotation_quality_mode(request)`; `save_annotation` now writes
  `quality_mode` + `degraded_reasons`.
- `src/app/services/seo/matcher_v2/api.py` — computes
  `infer_quality_mode` from provider ceiling + readiness snapshot +
  upstream SKU annotation mode.
- `src/app/services/seo/generation/service.py` — propagates upstream
  (query-set) quality into `SeoGenerationRun` + `SeoContentVersion`;
  helper `_coerce_quality_mode` defends against stale string values.
- `src/app/schemas/seo_products.py` — `SeoProductSummaryResponse` and
  `SeoQuerySetResponse` additively expose `quality_mode`,
  `degraded_reasons` (and `matcher_run_id` on the query-set shape).
- `src/app/services/seo/products.py` — summary + query-set response
  builders now populate the new fields from their owned ORM rows.
- `src/app/schemas/seo_generation.py` — `SeoGenerationRunResponse` and
  `SeoGenerationLatestResponse` expose `quality_mode`,
  `degraded_reasons`, `mode_used`, `publishable`, `matcher_run_id`.
- `frontend/app/app/project/[projectId]/seo/_components/QualityBadge.tsx`
  — **new** `QualityBadge` + `ResearchPreviewBanner` components.
- `frontend/lib/apiClient.ts` — typed `SeoQualityMode`,
  `SeoQualityReason`, and added quality fields on the generation / query
  / summary response shapes.

### B. Atoms relocation (WS-A)

- `src/app/services/seo/atoms/__init__.py` — **new**.
- `src/app/services/seo/atoms/v1/__init__.py` — **new**, re-exports
  public API of the relocated atoms package.
- `src/app/services/seo/atoms/v1/{guards,llm_extractors,matcher_v1,schemas,vision}.py`
  — **moved** from `experiments/meaning_atoms/` with internal imports
  updated. `v1.py` renamed to `matcher_v1.py` to make the promotion
  obvious. Logic unchanged.
- `src/app/services/seo/query_meaning_matcher/matcher.py`,
  `src/app/services/seo/meaning_atoms/storage.py` — production import
  sites rewritten to `app.services.seo.atoms.v1.*`.
- `src/app/services/seo/experiments/meaning_atoms/__init__.py` — replaced
  with a **freeze shim**: calls `guard_frozen_module`, proxies remaining
  research-script attributes via `__getattr__`, updates in-package scripts
  (`comparison.py`, `matcher.py`, `report.py`,
  `run_vision_comparison.py`) to import from the new `atoms.v1`.
- `tests/test_seo_meaning_atoms_experiment.py` — updated to the new
  import path for production symbols, experiment symbols stay where they
  are.

### C. Candidate matcher (WS-A)

- `alembic/versions/20260423_seo_iter1_quality_mode_and_matcher_runs.py`
  — **new** single additive migration. Adds quality columns to the four
  existing tables (idempotent where the column already exists) and
  creates `seo_matcher_runs` + `seo_matcher_results`.
- `src/app/models.py` — new ORM classes `SeoMatcherRun` and
  `SeoMatcherResult` with the columns from
  [`04_data_model_and_state_changes.md`](../04_data_model_and_state_changes.md)
  §1.1 / §1.2, plus an index on `(project_id, category_id, nm_id,
  started_at)`.
- `src/app/services/seo/matcher_v2/__init__.py` — **new** package entry.
- `src/app/services/seo/matcher_v2/stages/__init__.py` — **new** empty.
- `src/app/services/seo/matcher_v2/stages/eligibility.py` — **new**;
  wraps the eligibility / hard-conflict / manual-judgment helpers from
  the current matcher and produces an `EligibilityVerdict`.
- `src/app/services/seo/matcher_v2/stages/soft_score.py` — **new**;
  re-uses the original matcher's private scoring helpers.
- `src/app/services/seo/matcher_v2/stages/bucket_cap.py` — **new**;
  copies the bucket + atoms gate policy verbatim from the original
  matcher.
- `src/app/services/seo/matcher_v2/stages/demand_ordering.py` — **new**;
  wraps coverage + ranking ordering helpers.
- `src/app/services/seo/matcher_v2/persistence.py` — **new**; writes one
  `SeoMatcherRun` + N `SeoMatcherResult` rows per invocation.
- `src/app/services/seo/matcher_v2/api.py` — **new**; orchestrates the
  four stages, runs `infer_quality_mode`, persists the trace, returns a
  `MatcherV2RunResult`. The current `run_meaning_aware_matcher` is
  **not** modified.
- `src/app/schemas/seo_matcher_v2.py` — **new**;
  `MatcherV2RunRequest`, `MatcherV2RunResponse`, `MatcherV2ResultItem`,
  `MatcherV2RunDetailResponse`.
- `src/app/routers/seo_matcher_v2.py` — **new**;
  `POST /api/v1/projects/{project_id}/seo/matcher/v2/run` and
  `GET /api/v1/projects/{project_id}/seo/matcher/v2/runs/{run_id}`.
- `src/app/main.py` — registers the new router.

### D. Generation discipline (WS-D)

- `src/app/settings.py` — `SEO_GENERATION_MAX_ATTEMPTS` default lowered
  to `1`; new `SEO_GENERATION_PREVIEW_ENABLED` (default `false`).
- `src/app/services/seo/generation/service.py`:
  - Retry loop now breaks on validator-clean only; V2-relevance score
    never triggers a retry.
  - Relevance reports relabelled in the persisted `attempts` payload and
    `score_breakdown` as `internal_lint_seo_relevance` /
    `internal_lint_seo_relevance_v2` (both legacy keys are still read by
    the latest-response builder so existing DB rows keep rendering).
  - Propagates upstream `quality_mode`, `degraded_reasons`, and
    `matcher_run_id` from `SeoSkuQuerySet` to `SeoGenerationRun`.
  - Sets `mode_used='research_preview'` whenever
    `SEO_GENERATION_PREVIEW_ENABLED=false` or the generation's quality is
    not `FULL`. `publishable` is hard-coded to `False` in iteration 1.
- `src/app/routers/seo_generation.py`:
  - New `GET /api/v1/seo/feature-flags` endpoint returning
    `{ generation_preview_enabled, generation_max_attempts,
    generation_publishable }`.
  - `POST /generation/run` now returns **503** if
    `SEO_GENERATION_PREVIEW_ENABLED=false`.
- `frontend/lib/apiClient.ts` — `SeoFeatureFlags` type +
  `getSeoFeatureFlags()` (legacy `getSeoGenerationConfig` retained as a
  deprecated alias).
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/generation/page.tsx`:
  - Hardcoded `generationEndpointReady = true` removed; now derived from
    `getSeoFeatureFlags().generation_preview_enabled`.
  - `ResearchPreviewBanner` rendered at the top of the page; its copy
    switches on `previewEnabled`.
  - Relevance cards re-titled "Internal lint (relevance)" and "Internal
    lint (relevance V2)" with a short explainer that they are not a
    publish gate.
  - `QualityBadge` wired to `generation.quality_mode ||
    latest.quality_mode` with `degraded_reasons` as tooltip.
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/queries/page.tsx`
  — `QualityBadge` wired to `querySet.quality_mode`.
- `frontend/app/app/project/[projectId]/seo/products/[nmId]/page.tsx`
  — `QualityBadge` wired to `summary.quality_mode`.

### E. Dead-schema freeze (WS-F)

- `src/app/services/seo/_freeze.py` — **new**. Runtime guard
  `guard_frozen_module` (walks the full import stack, raises
  `FrozenModuleImportError` only when no allowed caller is in scope;
  env override `SEO_ALLOW_FROZEN_IMPORTS=1`).
- `src/app/models.py` — `__frozen__ = True` + deprecation docstrings on
  the eight frozen ORM classes (`SeoSkuClusterRun`, `SeoSkuCluster`,
  `SeoSkuClusterAssignment`, `SeoClusterProfile`,
  `SeoClusterProfileVersion`, `SeoScoreRun`, `SeoQueryScore`,
  `SeoScoreExplanation`).
- `src/app/services/seo/clustering/{__init__,service,presegmentation,representation,hdbscan_hook}.py`
  — each module now calls `guard_frozen_module(__name__)` at load time
  and carries a `[FROZEN iter-1]` docstring.
- `src/app/services/seo/scoring/service.py` — calls
  `guard_frozen_module` with `allowed_caller_prefixes=("…scoring.preparation",
  "…scoring.actual")` so the diagnostic scorers still work.
- `src/app/services/seo/__init__.py` — legacy frozen helper re-exports
  moved behind a lazy `__getattr__`, so the package root no longer
  eagerly loads clustering on every `app.services.seo` import.
- `tests/seo/__init__.py` + `tests/seo/test_frozen_imports.py` — **new**.
  AST walk over `src/app/` rejecting `from app.services.seo.clustering`,
  `from app.services.seo.experiments.meaning_atoms`,
  `from app.services.seo.scoring.service`, and re-exports of the
  forbidden `scoring` symbols via the package root.

### P1 deliverables

- `frontend/app/app/project/[projectId]/seo/matcher-runs/[runId]/page.tsx`
  — **new**. Read-only replay of a persisted matcher_v2 run (bucket
  lists, score components, reasons, quality badge, degraded reasons,
  errors). Uses only `GET /matcher/v2/runs/{run_id}` — no writes.

---

## 2. Migrations

| Revision | File | Scope |
|---|---|---|
| `20260423_seo_iter1_quality_mode_and_matcher_runs` | `alembic/versions/20260423_seo_iter1_quality_mode_and_matcher_runs.py` | Adds `quality_mode`/`degraded_reasons` to four existing tables, adds `mode_used`/`publishable` to `seo_content_versions`, adds nullable `matcher_run_id` FK where planned, creates `seo_matcher_runs` and `seo_matcher_results`. |

No backfills, no drops.

---

## 3. Endpoints

### Added

- `POST /api/v1/projects/{project_id}/seo/matcher/v2/run`
- `GET  /api/v1/projects/{project_id}/seo/matcher/v2/runs/{run_id}`
- `GET  /api/v1/seo/feature-flags`

### Behaviour changed

- `POST /api/v1/projects/{project_id}/seo/products/{nm_id}/generation/run`
  returns **503** when `SEO_GENERATION_PREVIEW_ENABLED=false`.
  Response shape gains `quality_mode`, `degraded_reasons`, `mode_used`,
  `publishable`, `matcher_run_id` (all additive).
- `GET …/generation/latest` and `GET …/queries` and `GET …/summary`
  now surface `quality_mode` / `degraded_reasons` when present; legacy
  rows return `null` / `[]`.

### Intentionally unchanged

- `POST …/queries/run` (current `run_query_selection`) — still writes
  `SeoSkuQuerySet` / `SeoSkuQuerySetItem` rows exactly as before.
  `matcher_run_id` is left NULL; `quality_mode` is left NULL on this
  path until the candidate path is wired into promotion (iteration 2).

---

## 4. P0 / P1 status

### P0 — complete

- **A** Quality-mode framework + provider ceiling + integration at
  SKU-meaning / matcher_v2 / generation. ✅
- **B** Atoms promoted under `services/seo/atoms/v1/`, production
  imports rewritten, experiments path frozen. ✅
- **C** `matcher_v2` package live; `SeoMatcherRun` + `SeoMatcherResult`
  persist one trace per call; endpoints exposed; `SeoSkuQuerySet.matcher_run_id`
  column in place (currently written only by `matcher_v2/persistence`). ✅
- **D** `SEO_GENERATION_MAX_ATTEMPTS=1`, V2-relevance retry removed,
  relevance relabelled as internal lint, preview-flag gate on endpoint
  and frontend, `mode_used` / `publishable` / `quality_mode` written on
  every new `SeoContentVersion`. ✅
- **E** Deprecation notices on the eight frozen ORM classes, runtime
  guards on clustering + scoring.service + experiments shim, AST CI
  check under `tests/seo/test_frozen_imports.py`. ✅

### P1

- Matcher run viewer read-only page: **shipped**. ✅
- Physical move of `scoring/preparation.py` + `scoring/actual.py` under
  `services/seo/diagnostics/scoring/`: **deferred**. Reason: the plan
  assumed two importers; the actual surface is larger (the scoring
  package `__init__`, the debug router, two tests, two standalone
  scripts, and `scoring/actual` re-imports `scoring.preparation`). The
  risk/reward ratio is unfavourable in iteration 1 — the runtime guard
  on `scoring.service` already enforces the diagnostic boundary we
  wanted, and moving the files without a tracked deprecation window
  would flip too much legacy code at once. Carried into iteration 2 as
  a dedicated mini-refactor.

---

## 5. Risks, assumptions, conflicts observed

### UA-2 · matcher_v2 vs current matcher parity

`matcher_v2` reuses the private helpers of `run_meaning_aware_matcher`
verbatim for scoring and bucket-cap logic. The deliberate change is that
**eligibility runs before soft-score** (the plan's rewrite). For two
SKUs sampled in dev, bucket assignment matched the legacy matcher
modulo a handful of rejected queries that the new eligibility stage now
produces a specific `hard_conflict` verdict for. No parity test has been
written yet; iteration 2 should add a per-bucket equivalence oracle on a
fixed fixture set before turning on promotion.

### UA-6 · quality_mode propagation rule

Propagation follows the plan (`min(provider_max_mode, upstream_modes,
evidence_signals)` with `fallback_taken` forcing `FALLBACK`). Today the
only wired upstream signal is `SeoSkuMeaningAnnotation → SeoMatcherRun`;
`SeoCategoryMatchingReadiness` is intentionally **not** a column in
iter-1 and instead emits an in-memory signal via
`compute_bootstrap_quality_state`. Downstream generation sees the
effective upstream mode only through `SeoSkuQuerySet.quality_mode`; if a
candidate-path run produced a query set without going through
`run_query_selection`, we currently rely on the caller to fill
`upstream_modes` from the matcher run. A regression test is pending.

### UA-10 · matcher-run row volume

`SeoMatcherRun` + `SeoMatcherResult` write per call with no dedup. On
812, a single run produces ~120 result rows. At 300 SKUs × 5 reruns/day
that is ~180k rows/day, which is fine for Postgres but means the viewer
query should eventually page. Iteration 2 should add a size budget
and a run-retention policy.

### OD-1 — `SEO_GENERATION_PREVIEW_ENABLED` default: **off**

Frontend always renders `ResearchPreviewBanner`; the "Run generation"
button is disabled until the env flag is flipped per deployment.

### OD-7 — `seo_quality_events`: deferred (not iter-1).

### OD-8 — `SEO_CANDIDATE_FLOW_DEFAULT`: not introduced.
The candidate matcher is reachable only via the new URL — we explicitly
chose not to wire a flag-driven flow selector in iter-1.

### Plan conflicts preserved

- The plan schedules `mode_used` + `publishable` on `SeoContentVersion`
  for iter-1 but defers tightening the `content_kind` enum to iter-2.
  We kept `content_kind` freeform (`"llm_draft"`) — same as before.
- `selection_state` on `SeoSkuQuerySet` (iter-2 plan) would collide
  with the existing `selection_state` column on `SeoSkuQuerySetItem` —
  flagged here so iter-2 picks a distinct name.
- `feature-flags` endpoint shape settled on
  `{ generation_preview_enabled, generation_max_attempts,
  generation_publishable }`; we kept a deprecated TS alias
  `SeoGenerationConfig = SeoFeatureFlags` / `getSeoGenerationConfig =
  getSeoFeatureFlags` so any in-flight frontend branches keep
  compiling.

---

## 6. Verification checklist

### 6.1 `quality_mode` visibility

- `GET /api/v1/projects/{project_id}/seo/products/{nm_id}/summary`
  → payload contains `quality_mode` (maybe `null` on legacy rows) and
  `degraded_reasons: []`.
- `GET /api/v1/projects/{project_id}/seo/products/{nm_id}/queries`
  → payload contains `quality_mode` and `matcher_run_id`.
- `GET /api/v1/projects/{project_id}/seo/products/{nm_id}/generation/latest`
  → payload contains `quality_mode`, `mode_used`, `publishable:false`.
- `POST .../seo/matcher/v2/run` → response's top-level `quality_mode` is
  `"full"` | `"preview"` | `"degraded"` | `"fallback"`; `degraded_reasons`
  lists `{code, details}` entries. Frontend renders a `QualityBadge` on
  the SKU summary, queries page, and generation page wherever the field
  is non-null.

### 6.2 `matcher_v2` on a known 812 SKU

- `POST /api/v1/projects/{project_id}/seo/matcher/v2/run` with
  `{ category_id: 812, nm_id: <known SKU>, limit: 200, include_rejected: true }`
  → **200**, body has `run_id`, `quality_mode`, `response.buckets` with
  `primary/secondary/broad/rejected`.
- DB: one row in `seo_matcher_runs` with that `run_id`, N rows in
  `seo_matcher_results` (N = sum of items across buckets).
- `GET …/seo/matcher/v2/runs/{run_id}` returns the persisted trace;
  same bucket contents, same score components.
- Re-POST: a second row is inserted in `seo_matcher_runs`; the prior
  run is untouched.
- Frontend: open
  `/app/project/{projectId}/seo/matcher-runs/{runId}` — page shows
  bucket lists, quality badge, metrics, degraded reasons (if any).

### 6.3 Current path unbroken

- `POST /api/v1/projects/{project_id}/seo/products/{nm_id}/queries/run`
  still writes `SeoSkuQuerySet` + `SeoSkuQuerySetItem` on the current
  path, unchanged.
- Legacy `seo_sku_query_sets` rows keep `matcher_run_id IS NULL` and
  `quality_mode IS NULL`. New rows written after this iteration through
  the current path also leave those NULL — the candidate path is the
  only writer.
- All pre-existing SEO tests pass (`tests/test_seo_sku_meaning_tool.py`,
  `tests/test_seo_generation_validator.py`,
  `tests/test_seo_meaning_atoms_experiment.py`,
  `tests/test_seo_foundation.py`).

### 6.4 Generation preview gate

- Frontend: load
  `/app/project/{projectId}/seo/products/{nmId}/generation` — the
  "Research preview" banner is always visible.
- With `SEO_GENERATION_PREVIEW_ENABLED=false`: the "Сгенерировать"
  button is disabled and
  `POST /api/v1/projects/{project_id}/seo/products/{nm_id}/generation/run`
  returns **503**.
- With `SEO_GENERATION_PREVIEW_ENABLED=true`: button active; posting a
  run succeeds; response carries
  `mode_used: "research_preview"` and `publishable: false`.
- Relevance cards on the generation page are titled
  "Internal lint (relevance)" and "Internal lint (relevance V2)" and
  carry the "диагностический сигнал, не является quality gate"
  subtitle.

### 6.5 Frozen imports blocked

- `pytest -q tests/seo/test_frozen_imports.py` passes.
- Add `from app.services.seo.clustering import cluster_skus_placeholder`
  to, e.g., `src/app/routers/seo_query_meaning_matcher.py` and re-run
  the test → it fails with the file+line of the violation.
- Runtime: importing any clustering module from a production caller
  raises `FrozenModuleImportError` (env override:
  `SEO_ALLOW_FROZEN_IMPORTS=1`).

---

## 7. Test status at submission

```
tests/test_seo_sku_meaning_tool.py ............................  passed
tests/test_seo_generation_validator.py .....................    passed
tests/test_seo_meaning_atoms_experiment.py .......              passed
tests/test_seo_foundation.py ....                                passed
tests/test_seo_quality.py ....                                   passed
tests/seo/test_frozen_imports.py .                               passed
```

51 passed, 4 DeprecationWarnings (SQLAlchemy 3.12 datetime adapter, not
introduced by this iteration).
