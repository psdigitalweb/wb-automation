# 08. Top-Level Backlog

Audience: PM / engineering lead
Date: 2026-04-23

Top-level epics and tasks only. No low-level subtasks. All tasks are sized to "a short spec can be written against this in one sitting." Priority: P0 (must ship in the iteration it belongs to), P1 (strongly expected), P2 (nice to have, may slip).

---

## Epic E1 — Quality Mode Framework (WS-B)

### T-1.1 — Define and ship `quality_mode` + `degraded_reasons` schema

- Workstream: WS-B
- Description: Add columns on `SeoMatcherRun` (new), `SeoSkuQuerySet`, `SeoSkuMeaningAnnotation`, `SeoContentVersion`, `SeoGenerationRun`. Define enums and reason taxonomy.
- Why: unlocks every other workstream's visibility.
- Dependencies: —
- Output: DB migration + ORM updates + shared enum module.
- Risk: low.
- Priority: P0 (iteration 1).

### T-1.2 — Implement `infer_quality_mode` and integrate into pipeline layers

- Workstream: WS-B
- Description: One deterministic function called from bootstrap, SKU draft, matcher, generation. Encodes propagation rule for upstream_mode_min.
- Why: removes silent fallbacks.
- Dependencies: T-1.1.
- Output: `services/seo/quality.py` + 4 integration commits.
- Risk: medium — correctness of the propagation rule matters.
- Priority: P0 (iteration 1).

### T-1.3 — Enforce `LocalPreviewEmbeddingProvider` mode ceiling

- Workstream: WS-B
- Description: Provider-level max_mode attribute; matcher honors it.
- Why: closes the preview-looking-like-semantic gap.
- Dependencies: T-1.2.
- Output: provider interface change + matcher consumer change.
- Risk: low.
- Priority: P0 (iteration 1).

### T-1.4 — `QualityBadge` component + wiring across UI

- Workstream: WS-B
- Description: Reusable component + 4 initial placements (SKU summary, query selection, generation, product list).
- Why: operator visibility.
- Dependencies: T-1.1.
- Output: one React component + 4 integration screens.
- Risk: low.
- Priority: P0 (iteration 1).

---

## Epic E2 — Matcher Authority (WS-A)

### T-2.1 — Promote atoms out of `experiments/`

- Workstream: WS-A
- Description: Move `experiments/meaning_atoms/v1.py` + `schemas.py` + related helpers to `services/seo/atoms/v1/`. Keep old location import-guarded as frozen.
- Why: removes the audit finding that experimental code runs production matcher logic.
- Dependencies: —
- Output: new package + CI import guard.
- Risk: medium — existing imports across the codebase must be redirected.
- Priority: P0 (iteration 1).

### T-2.2 — Implement `run_matcher_v2` staged function

- Workstream: WS-A
- Description: Eligibility → bucket cap → soft score → demand ordering. Reads atoms + query atoms + profile (stub in iteration 1) + demand signals. Writes `SeoMatcherRun` + `SeoMatcherResult`.
- Why: single authority for matcher decisions.
- Dependencies: T-2.1, T-3.1 (tables).
- Output: `services/seo/matcher_v2/*` + unit tests + one endpoint.
- Risk: medium — must reproduce current behavior on 812 within tolerance.
- Priority: P0 (iteration 1).

### T-2.3 — Matcher tables and endpoint

- Workstream: WS-A
- Description: Create `seo_matcher_runs`, `seo_matcher_results`. Add `SeoSkuQuerySet.matcher_run_id` FK. Expose `POST /matcher/v2/run`, `GET /matcher/v2/runs/{run_id}`.
- Why: replayable trace; candidate path API surface.
- Dependencies: T-1.1.
- Output: migrations + router.
- Risk: low.
- Priority: P0 (iteration 1).

### T-2.4 — Matcher run viewer page

- Workstream: WS-A
- Description: Read-only page rendering a `SeoMatcherRun` with all metadata and bucket lists. "Replay this run" button.
- Why: explainability and nondeterminism detection.
- Dependencies: T-2.3.
- Output: one page + one frontend route.
- Risk: low.
- Priority: P1 (iteration 1).

---

## Epic E3 — Category Profile (WS-C)

### T-3.1 — Create `seo_category_profiles` table + loader

- Workstream: WS-C
- Description: Table + `load_active_profile()` + version bump semantics.
- Why: category-specific logic externalized.
- Dependencies: —
- Output: migration + service module + tests.
- Risk: low.
- Priority: P0 (iteration 2).

### T-3.2 — Seed 812 profile from current dictionaries

- Workstream: WS-C
- Description: Extract `_EXPRESSIVE_GROUPS`, `_AUDIENCE_GROUPS`, `_MATERIAL_CONSTRAINTS`, category-812 conflict rules, bucket cutoffs into `config/seo/category_profiles/812_mugs.yaml`. One-time importer.
- Why: make 812 reproducible from the profile.
- Dependencies: T-3.1.
- Output: YAML + importer script + ingested DB row.
- Risk: medium — subtle parity bugs are likely.
- Priority: P0 (iteration 2).

### T-3.3 — Refactor matcher_v2 stages to consume profile

- Workstream: WS-C
- Description: Remove module-level dicts inside `services/seo/matcher_v2/*`. All category data comes from the profile parameter.
- Why: enforces the boundary.
- Dependencies: T-2.2, T-3.2.
- Output: refactor + lint rule + CI check.
- Risk: medium.
- Priority: P0 (iteration 2).

### T-3.4 — `CategoryTierBadge` + category profile panel

- Workstream: WS-C
- Description: UI component + category page panel showing active profile version and payload.
- Why: operator visibility of tier and profile.
- Dependencies: T-3.1, T-4.1.
- Output: UI component + page additions.
- Risk: low.
- Priority: P1 (iteration 2).

---

## Epic E4 — Eval as a Gate (WS-E)

### T-4.1 — `seo_eval_labels` / `seo_eval_runs` tables and 191-label import

- Workstream: WS-E
- Description: Create tables. Import `artifacts/meaning_atoms/20260422*` labels as `label_set_id=1` for 812.
- Why: eval becomes first-class.
- Dependencies: —
- Output: migration + importer.
- Risk: low.
- Priority: P0 (iteration 2).

### T-4.2 — Eval harness + `POST /seo/eval/matcher/run`

- Workstream: WS-E
- Description: Compute accuracy / primary precision / recall / bad_primary / hard_conflict_primary. Write `seo_eval_runs`. Flip `eligibility_tier` when thresholds met.
- Why: gate enforcement.
- Dependencies: T-2.3, T-3.3, T-4.1.
- Output: service + router + tests.
- Risk: medium — parity with experiment scripts must hold.
- Priority: P0 (iteration 2).

### T-4.3 — Eval page UI

- Workstream: WS-E
- Description: Category eval page with current tier, metrics, history, run-eval button, thresholds info.
- Why: operator access to gate runs.
- Dependencies: T-4.2.
- Output: one frontend page.
- Risk: low.
- Priority: P1 (iteration 2).

### T-4.4 — Add `eligibility_tier` to readiness and restrict writers

- Workstream: WS-E
- Description: Column, default `preview_only`. Only eval endpoint writes. Other writers blocked in code.
- Why: single-writer invariant.
- Dependencies: T-4.1.
- Output: migration + enforcement.
- Risk: low.
- Priority: P0 (iteration 2).

---

## Epic E5 — Generation Discipline (WS-D)

### T-5.1 — Cap generation retry and relabel relevance as lint

- Workstream: WS-D
- Description: `SEO_GENERATION_MAX_ATTEMPTS=1` for validator errors only. Remove retry-against-relevance. UI relabels relevance as "internal lint."
- Why: removes false signal.
- Dependencies: —
- Output: service tweak + UI relabel.
- Risk: low.
- Priority: P0 (iteration 1).

### T-5.2 — Preview banner + flag-gated generation readiness

- Workstream: WS-D
- Description: Remove hardcoded `generationEndpointReady=true`. Derive readiness from env flag + tier + selection_state. Always show "Research preview" banner when applicable.
- Why: no premature impression of readiness.
- Dependencies: T-1.4, T-3.4 (tier badge; can stub initially).
- Output: frontend + env flag.
- Risk: low.
- Priority: P0 (iteration 1).

### T-5.3 — `SeoContentVersion` lifecycle columns

- Workstream: WS-D
- Description: Add `mode_used`, `publishable`, `matcher_run_id`, `quality_mode`, `degraded_reasons`, `category_profile_version`. Tighten `content_kind` to 4-state enum.
- Why: enforces lifecycle.
- Dependencies: T-1.1.
- Output: migration + ORM.
- Risk: low.
- Priority: P0 (iteration 2).

### T-5.4 — `seo_generation_human_review` + `POST /generation/{id}/promote`

- Workstream: WS-D
- Description: Table, endpoint with server-enforced gates, UI form for human rubric, "Promote to candidate" button.
- Why: promotion path with measured evidence.
- Dependencies: T-4.4, T-5.3.
- Output: migration + endpoint + UI.
- Risk: medium — gate logic must be airtight.
- Priority: P0 (iteration 2).

---

## Epic E6 — Dead Schema Freeze (WS-F)

### T-6.1 — Deprecation notices on frozen ORM classes

- Workstream: WS-F
- Description: Comments + `__frozen__ = True` flag (or similar) on the class.
- Why: signal intent.
- Dependencies: —
- Output: 8-ish ORM class edits.
- Risk: none.
- Priority: P0 (iteration 1).

### T-6.2 — Import guards for frozen service modules

- Workstream: WS-F
- Description: Module-level check blocking imports from non-diagnostics namespaces.
- Why: prevent re-entanglement.
- Dependencies: T-6.1.
- Output: guard code + CI check.
- Risk: low.
- Priority: P0 (iteration 1).

### T-6.3 — Move `scoring/preparation.py`, `scoring/actual.py` under `diagnostics/`

- Workstream: WS-F
- Description: Physical relocation; update the two known importers (`bootstrap_orchestrator`, `scoring/service`) to explicitly note diagnostic nature.
- Why: keep diagnostics diagnostic.
- Dependencies: T-6.2.
- Output: refactor + import updates.
- Risk: low.
- Priority: P1 (iteration 1).

---

## Epic E7 — Parallel Validation Surface

### T-7.1 — Selection state decomposition in `SeoSkuQuerySet`

- Workstream: WS-B (extension)
- Description: Add `selection_state`, `trust_state`. Keep `status` derived for one release. Rename UI "Confirm" to "Approve selection."
- Why: separates approved from validated.
- Dependencies: T-1.1.
- Output: migration + API + UI.
- Risk: medium — touches core status semantics.
- Priority: P0 (iteration 2).

### T-7.2 — Compare endpoints

- Workstream: compare
- Description: `GET /compare/matcher`, `GET /compare/generation`. Read-only, no writes.
- Why: diff view for validation.
- Dependencies: T-2.3, T-5.3.
- Output: router.
- Risk: low.
- Priority: P0 (iteration 2).

### T-7.3 — Matcher compare panel UI

- Workstream: compare
- Description: Two-column view on SKU page + full-page compare. Human verdict form.
- Why: side-by-side evidence.
- Dependencies: T-7.2.
- Output: UI page + component + verdict write endpoint.
- Risk: medium — layout matters a lot for usefulness.
- Priority: P0 (iteration 2).

### T-7.4 — Generation compare UI

- Workstream: compare
- Description: Two-column generated-card view with diff highlighting.
- Why: evidence for generation promotion.
- Dependencies: T-7.2, T-5.4.
- Output: UI page + diff components.
- Risk: medium — diff UX is tricky.
- Priority: P1 (iteration 2).

### T-7.5 — `seo_quality_events` table + emitters

- Workstream: WS-B (extension)
- Description: Append-only event log. Emit from 4-5 key sites (cache miss, fallback taken, preview embedding used, vision absent, reviews zero).
- Why: support timeline.
- Dependencies: T-1.2.
- Output: migration + emitters.
- Risk: low.
- Priority: P2 (iteration 1 or 2).

---

## Epic E8 — Cleanup / Promotion Decision (iteration 3, conditional)

### T-8.1 — Leadership decision memo based on compare data

- Workstream: cross-cutting
- Description: Collate metrics + human verdicts + eval runs into a decision memo. Promote / Extend / Reject.
- Why: prevent silent drift.
- Dependencies: iteration 2 complete.
- Output: doc.
- Risk: low.
- Priority: P0 (iteration 3).

### T-8.2 — Sunset of current-path matcher (if promoted)

- Workstream: cross-cutting
- Description: Flip flag, forward endpoints, archive legacy code.
- Why: avoid supporting two systems.
- Dependencies: T-8.1 = promote.
- Output: code archival + flag flip.
- Risk: medium.
- Priority: P0 (iteration 3).

### T-8.3 — Drop frozen tables

- Workstream: WS-F (extension)
- Description: Drop clustering and scoring tables after 30-day zero-writes audit.
- Why: remove noise.
- Dependencies: T-6.2, 30-day audit.
- Output: migration.
- Risk: low.
- Priority: P1 (iteration 3).

### T-8.4 — Replace `SeoSkuQuerySet.status` with the two-axis model only

- Workstream: WS-B (extension)
- Description: Drop `status`, update all readers.
- Why: single source of truth for selection.
- Dependencies: T-7.1 + one release of parity.
- Output: migration + code updates.
- Risk: medium.
- Priority: P1 (iteration 3).

---

## Priority summary

| Priority | Iteration 1 | Iteration 2 | Iteration 3 (conditional) |
|---|---|---|---|
| P0 | T-1.1, T-1.2, T-1.3, T-1.4, T-2.1, T-2.2, T-2.3, T-5.1, T-5.2, T-6.1, T-6.2 | T-3.1, T-3.2, T-3.3, T-4.1, T-4.2, T-4.4, T-5.3, T-5.4, T-7.1, T-7.2, T-7.3 | T-8.1, T-8.2 |
| P1 | T-2.4, T-6.3 | T-3.4, T-4.3, T-7.4 | T-8.3, T-8.4 |
| P2 | T-7.5 | — | — |

## Scheduling guidance

- Iteration 1 P0 tasks cluster into three parallelizable lanes: WS-B lane (T-1.*), WS-A lane (T-2.*), generation/housekeeping lane (T-5.1, T-5.2, T-6.*).
- Iteration 2 P0 tasks have a dependency chain: WS-C → WS-E → WS-D promote. Compare layer (T-7.2+) parallels the chain.
- Keep P2 items unscheduled; pull them in only if slack appears.
