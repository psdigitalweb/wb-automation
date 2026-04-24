# 07. Iteration Plan

Audience: PM / engineering lead
Date: 2026-04-23

Two firm iterations plus an optional cleanup iteration. Each iteration has a concrete "what we can prove at the end" clause. No vague milestones.

---

## Iteration 1 — Visibility, authority, discipline. Parallel path bootstrapped.

Target duration: ≈ 2 weeks. Scope is additive. No breaking change to the current path.

### Goals

1. Every decision carries a `quality_mode`.
2. The candidate matcher authority exists, with a replayable trace row.
3. Dead schema is frozen so nothing new depends on it.
4. Generation is gated behind an explicit preview flag with a banner.
5. Atoms code is promoted out of `experiments/`.

### Included work

- **WS-B — quality mode + degraded reasons**
  - Add columns `quality_mode` and `degraded_reasons` on `SeoMatcherRun` (new), `SeoSkuQuerySet`, `SeoSkuMeaningAnnotation`, `SeoContentVersion`, `SeoGenerationRun`.
  - Implement `services/seo/quality.py::infer_quality_mode(...)` and call it from each layer.
  - Enforce `LocalPreviewEmbeddingProvider.max_mode = preview` at provider level.
  - UI: add `QualityBadge` component, wire to SKU summary, query selection, and generation pages.
- **WS-F — freeze dead schema**
  - Deprecation notices on `SeoSkuClusterRun` / `SeoSkuCluster` / `SeoSkuClusterAssignment`, `SeoClusterProfile` / `SeoClusterProfileVersion`, `SeoScoreRun` / `SeoQueryScore` / `SeoScoreExplanation`.
  - Runtime import guards on `services/seo/clustering/*` and `scoring/service.py::*`.
  - CI check preventing re-imports from production paths.
- **WS-A — matcher authority (first cut)**
  - Promote `experiments/meaning_atoms/v1.py` + `schemas.py` + related code into `services/seo/atoms/v1/` without rewrites.
  - Create `services/seo/matcher_v2/` package; implement staged function in skeleton form (eligibility → bucket cap → soft score → demand ordering) mirroring current behavior but reorganized.
  - Create tables `seo_matcher_runs` and `seo_matcher_results`; write on candidate-path runs.
  - Add `SeoSkuQuerySet.matcher_run_id` FK (nullable).
  - Add candidate endpoints `POST /matcher/v2/run` and `GET /matcher/v2/runs/{run_id}`.
  - Matcher run viewer page (read-only) in UI.
- **WS-D — generation discipline (first cut)**
  - Cap `SEO_GENERATION_MAX_ATTEMPTS = 1`, restrict retry to validator hard errors.
  - Introduce env flag `SEO_GENERATION_PREVIEW_ENABLED`.
  - Add "Research preview" banner to generation page; remove hardcoded `generationEndpointReady=true`.
  - Relabel relevance report as "internal lint" in UI.
  - Add `SeoContentVersion.mode_used`, `publishable` columns (default safe values).

### Explicitly excluded

- No `SeoCategoryProfile` extraction yet.
- No eval endpoint yet.
- No generation promotion endpoint or `seo_generation_human_review` table yet.
- No migration of `SeoSkuQuerySet.status` to the two-axis model.
- No deletion of frozen tables.

### Ordering rationale

- WS-B and WS-F are cheap and independent. Ship them first so the team is reading from a cleaner base while WS-A lands.
- WS-A depends on atoms being out of `experiments/` but is independent from profile extraction.
- WS-D first-cut changes are small and can sit on top of any of the above.

### Success criteria (measurable)

- For any SKU that has been re-analyzed in iteration 1, the SEO summary endpoint returns a `quality_mode` and at least one `degraded_reason` or `full` mode.
- `POST /matcher/v2/run` on a known 812 SKU produces a `SeoMatcherRun` with the same bucket distribution (within tolerance) as the current path on the same SKU.
- Replaying the same run via the matcher run viewer yields identical buckets.
- No new commit can import `services/seo/clustering/*` or `scoring/service.py::persist_query_score` from a production path (CI enforces).
- Generation page shows the preview banner for category 812 and does not show a promotion button.

### What this iteration proves

- We can record, not just compute, our decisions.
- We know, for every output, how good its inputs were.
- We have a second matcher running in shadow on the candidate path.
- Nothing in the system implies "ready for production" when it isn't.

---

## Iteration 2 — Category profile, eval as a gate, generation lifecycle, compare layer.

Target duration: ≈ 2 weeks. Scope completes the candidate operating model.

### Goals

1. All category-specific rules live in a versioned `SeoCategoryProfile`.
2. Eval is a runnable backend gate.
3. Generation lifecycle has four states with server-enforced promotion.
4. Compare layer shows current vs candidate side by side.
5. Category tier gates generation preview per category.

### Included work

- **WS-C — category profile**
  - Create table `seo_category_profiles`.
  - Seed active profile for (project=1, category=812) from current hardcoded dictionaries.
  - Build `services/seo/category_profile.py::load_active_profile`.
  - Refactor matcher_v2 stages to read from the profile. Remove module-level dicts in matcher_v2.
  - Add lint / CI rule: no Russian literal in `services/seo/matcher_v2/*`.
  - UI: "Active category profile" panel on the category page.
- **WS-E — eval as a gate**
  - Create tables `seo_eval_labels` and `seo_eval_runs`.
  - Import existing 191 labels into `seo_eval_labels` as `label_set_id=1` for 812.
  - Implement `services/seo/eval/harness.py`.
  - Expose `POST /seo/eval/matcher/run` and `GET /seo/eval/matcher/runs/{run_id}`.
  - Add `SeoCategoryMatchingReadiness.eligibility_tier` and make the eval endpoint the only writer.
  - UI: new eval page, history table, run eval button.
  - UI: `CategoryTierBadge` on category and SKU pages.
- **WS-D — generation discipline (second cut)**
  - Tighten `SeoContentVersion.content_kind` enum to `preview | candidate | approved | published`.
  - Create `seo_generation_human_review` table.
  - Endpoint `POST /generation/{id}/promote` with server-enforced gates.
  - UI: "Promote to candidate" button; "Human review" form; four-state kind badges on history.
- **WS-B (extension) — selection_state + trust_state**
  - Add `SeoSkuQuerySet.selection_state` and `trust_state`. Keep `status` derived for one release.
  - UI: two independent badges on SKU summary and query selection.
  - Rename "Confirm" to "Approve selection."
- **Compare layer**
  - `GET /compare/matcher` and `GET /compare/generation` endpoints.
  - Matcher compare panel on SKU page and full-page compare view.
  - Generation compare view.
  - Operator human verdict capture for matcher compare.

### Explicitly excluded

- No second-category rollout.
- No batch generation.
- No WB Content API integration.
- No labeling UI (manual or DB-seed in this iteration).
- No deletion of frozen schema (still deferred).

### Ordering rationale

- WS-C must land before matcher_v2 stops carrying term dictionaries in code. Otherwise matcher_v2 is not reproducible by profile version.
- WS-E depends on WS-C because eval metrics are evaluated per profile version.
- WS-D second cut depends on WS-E because promotion gates reference eval verdicts.
- Compare layer is last because it assumes candidate-path data exists.

### Success criteria (measurable)

- Matcher v2 on category 812 reads all term groups, conflict rules, and bucket cutoffs from `SeoCategoryProfile` v1. Adding a new category profile row does not require code change.
- `POST /seo/eval/matcher/run` for category 812 with `label_set_id=1` reproduces numbers consistent with `23_atoms_v1_design_and_implementation_plan.md §Experiment Evidence` within tolerance.
- Flipping `eligibility_tier` happens only when thresholds are met and is never set by any other endpoint.
- `POST /generation/{id}/promote` refuses to promote content versions that do not satisfy the tier + human review conditions. Verified by automated test.
- Compare panel renders on a known SKU with at least one current query set and one candidate `SeoMatcherRun` and shows a meaningful delta.

### What this iteration proves

- The engine is honestly category-configurable. No hidden lexicons.
- Eval can gate work, not just describe it.
- Generation has a lifecycle it cannot bypass.
- Current vs candidate is a decision the team can make on evidence, not on impressions.

---

## Optional Iteration 3 — Cleanup and decision.

Triggered after iteration 2 compare data is sufficient.

### Goals (conditional)

1. Leadership promotion decision (promote / extend / reject) for category 812.
2. If promoted: current path sunset and deletion.
3. If extended: scoped improvements to candidate.
4. If rejected: candidate flow rollback.
5. Delete frozen tables (`SeoSkuClusterRun`, `SeoClusterProfile`, `SeoScoreRun`, etc.) if 30 days of zero writes confirmed.
6. Replace `SeoSkuQuerySet.status` entirely with the two-axis model.

### Included (if promoted)

- Flip `SEO_CANDIDATE_FLOW_DEFAULT=true`.
- Forward current-path endpoints to candidate behavior.
- Archive `query_meaning_matcher/matcher.py::run_meaning_aware_matcher` under `legacy/`.
- Drop frozen tables (with a pre-flight audit).
- Remove compare endpoints once no longer useful; document sunset date.

### Included (if extended)

- Scoped improvements named by the eval and compare deltas (e.g., specific conflict rules that tripped, term groups that need widening).
- Repeat iteration 2's gates.

### Included (if rejected)

- Disable `SEO_CANDIDATE_FLOW_DEFAULT`.
- Archive candidate tables as frozen.
- Document findings back into current-path improvements.
- Avoid supporting two systems past iteration 3.

### Success criteria

- A single documented decision made on measured evidence.
- The system has one default path again (either the previous one or the new one).
- Frozen schema count has dropped.

---

## Rolling metrics to track at every iteration close

- Percentage of SKU decisions with `quality_mode = full` (target trending up).
- Percentage of decisions with `quality_mode = fallback` (target trending down).
- Matcher_v2 acceptance-gate metrics for category 812.
- Compare agreement rate and human verdict balance.
- Number of frozen symbols still referenced (target 0).
- Number of generation promotions blocked by gate vs allowed.
- Time from "analysis started" to "selection approved + eval validated" per SKU.

These are the numbers leadership uses to decide promotion.
