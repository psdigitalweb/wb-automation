# 04. Data Model And State Changes

Audience: architect / backend lead
Date: 2026-04-23

No SQL. Entity- and field-level planning only.

---

## 1. New entities (introduced in this plan)

### 1.1 `seo_matcher_runs`

**Why it exists:** to give every decision one replayable trace row. Removes the audit finding that `SeoSkuQuerySetItem.reasons_payload` is overwritten on re-run and cannot be historized.

**Fields:**

- `id` — primary key.
- `project_id`, `category_id`, `nm_id` — scope.
- `matcher_version` — pinned version string of `run_matcher_v2`.
- `policy_version` — version of hard-conflict policy.
- `category_profile_version` — FK / reference to `seo_category_profiles.version`.
- `sku_atoms_id` — FK / reference to the `SeoMeaningAtom` row used for SKU atoms.
- `vision_atoms_id` — optional reference.
- `query_atoms_version` — version string for the query-atom materialization used.
- `embedding_model` — string identifier of the embedding provider used.
- `readiness_snapshot jsonb` — category readiness at time of run.
- `quality_mode enum` — `full | preview | degraded | fallback`.
- `degraded_reasons jsonb` — structured reason list.
- `started_at`, `completed_at`, `error jsonb`.

**Not stored here:** meanings themselves, profile payloads themselves, atoms payloads themselves. This row references them by id/version.

### 1.2 `seo_matcher_results`

**Why it exists:** per-query bucket + score + explanation tied to a specific matcher run. Replaces the overwrite behavior of `SeoSkuQuerySetItem`.

**Fields:**

- `id`, `run_id` — FK to `seo_matcher_runs`.
- `cluster_key`, `query_meaning_id`, `query_display`.
- `bucket enum` — `primary | secondary | broad | rejected`.
- `eligibility_verdict enum` — `eligible | ineligible_hard_conflict | ineligible_missing_required | ineligible_exclusion`.
- `score` — final score inside the bucket.
- `score_components jsonb` — named contributions (product_type, expressive, use_case, attribute, audience, occasion, specificity_bonus, frequency, genericness_penalty, conflict_penalty, semantic_similarity).
- `matched_atoms`, `missing_atoms`, `conflict_atoms` — atom key lists.
- `reasons jsonb` — human-readable reason strings tied to this result.
- `ranking_value_used` — demand signal value used.

### 1.3 `seo_category_profiles`

**Why it exists:** to hold all category-specific rules and term dictionaries versioned per category. Removes the audit finding that the matcher is 812-calibrated but pretends general.

**Fields:**

- `id`, `project_id`, `category_id`, `version` — composite uniqueness on (project_id, category_id, version).
- `status enum` — `draft | active | archived`.
- `profile_payload jsonb` — the full category configuration (term groups, conflict rules, bucket cutoffs, title rules, brand voices).
- `source` — `seed_yaml | ui_edit | import`.
- `activated_at`, `deactivated_at`, `created_at`, `created_by`.

Only one `active` row per (project_id, category_id).

### 1.4 `seo_eval_labels`

**Why it exists:** to turn eval from folder artifacts into first-class backend data.

**Fields:**

- `id`, `label_set_id`, `project_id`, `category_id`.
- `nm_id`, `cluster_key`, `query_text`.
- `label enum` — `primary | secondary | broad | rejected | hard_conflict | ambiguous`.
- `labeled_by`, `labeled_at`, `source` — `import_artifact | manual`.
- Uniqueness on (label_set_id, nm_id, cluster_key, query_text).

### 1.5 `seo_eval_runs`

**Why it exists:** to record every eval execution against a label set and a matcher version.

**Fields:**

- `id`, `project_id`, `category_id`, `label_set_id`.
- `matcher_version`, `policy_version`, `category_profile_version`.
- `metrics jsonb` — accuracy, primary_precision, primary_recall, bad_primary_count, hard_conflict_primary_count, per_error_type.
- `matcher_run_ids jsonb` — the runs evaluated.
- `verdict enum` — `preview_gate_pass | preview_gate_fail | acceptance_gate_pass | acceptance_gate_fail | diagnostic_only`.
- `ran_at`, `ran_by`.

### 1.6 `seo_generation_human_review`

**Why it exists:** to hold the human half of the generation promotion gate.

**Fields:**

- `id`, `content_version_id` — FK.
- `reviewer_id`.
- `rubric_scores jsonb` — `{ relevance: int, fidelity: int, unsupported_claims: bool }`.
- `verdict enum` — `reject | accept_with_edits | accept`.
- `notes text`.
- `reviewed_at`.

### 1.7 `seo_quality_events` (append-only, optional)

**Why it exists:** to give support a timeline of "cache miss, LLM unavailable, atoms fell back" without polluting decision rows.

**Fields:**

- `id`, `project_id`, `category_id`, `nm_id nullable`.
- `scope enum` — `bootstrap | atoms | matcher | generation | expressive_cache`.
- `event_code` — bounded enum such as `embedding_preview_used`, `llm_cache_hit_older_prompt`, `sku_draft_fallback`, `atoms_extraction_fallback`, `reviews_zero`, `vision_absent`.
- `detail jsonb`.
- `occurred_at`.

---

## 2. Changes to existing entities

### 2.1 `SeoSkuQuerySet`

- Add `matcher_run_id` (FK, nullable for legacy rows).
- Add `quality_mode enum`, `degraded_reasons jsonb`.
- Add `selection_state enum ∈ {draft, approved}`.
- Add `trust_state enum ∈ {unvalidated, eval_validated}`.
- Keep `status` as a derived read-time column for one release; remove next iteration.
- Keep existing uniqueness constraint `(project_id, category_id, nm_id, status)` until selection_state/trust_state are fully wired, then replace with `(project_id, category_id, nm_id, selection_state)`.

### 2.2 `SeoSkuQuerySetItem`

- Gains `matcher_run_id` passthrough for indexing; no behavior change in iteration 1.
- In iteration 2, reads come from `seo_matcher_results` and `SeoSkuQuerySetItem` is treated as a derived view refreshed from the latest approved run.

### 2.3 `SeoSkuMeaningAnnotation`

- Add `quality_mode enum`, `degraded_reasons jsonb`.
- Existing `status` column stays.
- Fallback-path annotations carry `quality_mode = fallback` and are labeled in UI.

### 2.4 `SeoContentVersion`

- `content_kind` enum tightened: from freeform to `preview | candidate | approved | published`.
- Add `mode_used enum ∈ {current, candidate}`.
- Add `publishable boolean` default false.
- Add `matcher_run_id` nullable FK.
- Add `quality_mode enum`, `degraded_reasons jsonb`.
- Add `category_profile_version` at write time for replay.

### 2.5 `SeoCategoryMatchingReadiness`

- Add `eligibility_tier enum ∈ {preview_only, eligible_for_preview, acceptance_passed}` default `preview_only`.
- Add `last_eval_run_id` nullable FK.
- Keep existing `status` column (`building | ready | ready_with_fallback | failed | not_started`) for runtime readiness; do not repurpose it.

### 2.6 `SeoGenerationRun`

- Add `matcher_run_id` nullable FK.
- Add `quality_mode enum`.
- No enum change on status; kept for runtime tracking.

---

## 3. Entities that become derived / secondary

- `SeoSkuQuerySetItem` — derived from `seo_matcher_results` once candidate path is default. During validation, both coexist; candidate reads `seo_matcher_results`.
- `SeoQueryAnnotation.meta["hybrid_annotation"]` — stays as-is but no candidate-path reader uses it for decisions. Candidate consumes typed atoms instead.

---

## 4. Entities that are frozen

Deprecation notice + import guard in iteration 1. No data changes. Drop in iteration N+2.

- `SeoSkuClusterRun`, `SeoSkuCluster`, `SeoSkuClusterAssignment`
- `SeoClusterProfile`, `SeoClusterProfileVersion`
- `SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation`
- Helpers: `scoring/service.py::create_score_run`, `scoring/service.py::persist_query_score`
- Service folder: `services/seo/clustering/*`

---

## 5. Entities deferred (not in this plan)

- Stable `category_scope_id` / surrogate for WB subject id — acknowledged risk, not addressed here.
- A "meanings unified" super-entity — explicitly rejected.
- A learnable/auto-profile builder — out of scope.
- A batch generation run entity — out of scope.
- Publish/WB content sync entity — out of scope.

---

## 6. State model changes

### 6.1 Query selection state decomposition

Current: one `status` column, values `draft | confirmed`.

Candidate:

- `selection_state ∈ {draft, approved}` — human intent about which queries to use.
- `trust_state ∈ {unvalidated, eval_validated}` — whether the matcher run backing this selection has an eval verdict.

These axes are independent. A selection can be `approved + unvalidated` (operator approved it but matcher has not been eval-gated) or `draft + eval_validated` (matcher eval green but operator has not confirmed the edits).

**Decision this enables:** generation promotion can require `approved + eval_validated` instead of conflating them under `confirmed`.

### 6.2 Quality mode enum

Defined once, used everywhere:

- `full` — production-grade inputs, no proxies.
- `preview` — at least one deterministic proxy in the path (embedding preview, stale prompt version).
- `degraded` — evidence sources missing (zero reviews, cache cold, vision absent) but run succeeded.
- `fallback` — product-data-only fallback path was taken (LLM draft failed or atoms extraction fell back).

Computed deterministically by `infer_quality_mode(pipeline_state)`. Stored on every decision-carrying row. Never set by humans.

### 6.3 Category eligibility tier

New column on `SeoCategoryMatchingReadiness`:

- `preview_only` — seeded profile, no labels, not promotable.
- `eligible_for_preview` — ≥ 50 labels, reduced gate passed, generation preview allowed.
- `acceptance_passed` — full gate met, generation may move to candidate.

**Decision this enables:** generation endpoints server-side reject promotion requests for categories not at the required tier.

### 6.4 Generation content-kind lifecycle

Enum tightened to: `preview | candidate | approved | published`.

- `preview` is the default on any generation run.
- `candidate` requires matcher eval green + generation human review green. Enforced by `POST /seo/generation/{id}/promote`.
- `approved` requires category tier `acceptance_passed` + explicit operator sign-off.
- `published` is reserved. No code path in this plan.

### 6.5 Eligibility verdict (on matcher results)

New enum on `seo_matcher_results.eligibility_verdict`:

- `eligible`
- `ineligible_hard_conflict`
- `ineligible_missing_required`
- `ineligible_exclusion`

**Decision this enables:** compare layer can show, per query, not just the bucket movement but the rule that caused it.

---

## 7. Migration strategy (high-level)

### Iteration 1

1. Add new columns with non-breaking defaults. No backfill.
2. Create the five new tables (`seo_matcher_runs`, `seo_matcher_results`, `seo_category_profiles`, `seo_quality_events` if included, `seo_eval_labels` seeded empty).
3. Import existing 191 labels into `seo_eval_labels` as `label_set_id=1` for category 812.
4. Seed one active `seo_category_profiles` row for category 812 from the current hardcoded dictionaries.
5. No data migration of `SeoSkuQuerySet`, `SeoSkuQuerySetItem`, `SeoContentVersion`. Legacy rows stay as-is.

### Iteration 2

1. Add `seo_eval_runs`, `seo_generation_human_review`.
2. Wire candidate path writes; start accumulating `SeoMatcherRun` rows for every candidate request.
3. Backfill `content_kind` on existing `SeoContentVersion` rows: everything becomes `preview` (safe default; no publishable rows exist today).

### Later iterations (out of this plan)

1. Drop frozen tables after 30 days of confirmed zero writes.
2. Replace `SeoSkuQuerySet.status` with `selection_state` + `trust_state` only.
3. Drop derived-view behavior of `SeoSkuQuerySetItem` once candidate path is default.
4. Reconsider `SeoQueryAnnotation.meta["hybrid_annotation"]` JSON-as-schema pattern.

---

## 8. What must be introduced now vs later

**Now (iteration 1):**

- `seo_matcher_runs`, `seo_matcher_results`, `seo_category_profiles`, `seo_eval_labels`, `seo_quality_events` (optional but recommended).
- New columns on `SeoSkuQuerySet`, `SeoSkuMeaningAnnotation`, `SeoContentVersion`, `SeoCategoryMatchingReadiness`, `SeoGenerationRun`.

**Later (iteration 2):**

- `seo_eval_runs`, `seo_generation_human_review`.
- `content_kind` enum tightening.
- `selection_state` / `trust_state` read/write switch.

**Deferred (beyond this plan):**

- Dropping frozen tables.
- Replacing WB subject id with a stable surrogate.
- Any publish / batch / cross-category entity.
