# 01. Target Operating Model

Audience: CTO / architect / lead engineer
Date: 2026-04-23

---

## 1. One-paragraph statement

The SEO module is a staged pipeline whose only authoritative decisions are produced by one staged matcher function and recorded in one `SeoMatcherRun` row per SKU/category. Every downstream consumer (query selection UI, generation brief, eval harness) reads from that row. Every decision carries an explicit `quality_mode`. Every category-specific rule is held in a versioned `SeoCategoryProfile`. Generation is a research preview per category, promoted only after matcher eval and human review pass.

The current flow is not removed. It runs in parallel with the candidate flow until parallel validation is complete.

## 2. Single authority for decision-making

**Authoritative decision path:**

```
build_sku_atoms + build_query_atoms (evidence)
    -> atoms_merge_policy (merge sku + vision atoms)
    -> run_matcher_v2(sku_atoms, query_atoms, category_profile, demand_signals, policy)
        stage 1: eligibility       (hard requirements, exclusions, product type)
        stage 2: bucket cap        (primary / secondary / broad / rejected bucket ceiling)
        stage 3: soft score        (atom-level soft signals inside the eligible bucket)
        stage 4: demand ordering   (ranking_value inside eligible bucket, never creates eligibility)
    -> writes: one SeoMatcherRun + N SeoMatcherResult rows
    -> SeoSkuQuerySet becomes a derived view over the latest SeoMatcherRun
```

**The only thing that may set a bucket or a score is `run_matcher_v2`.** Generation relevance reports, query selection UI, and eval harness are readers, not producers.

`scoring/preparation.py` and `scoring/actual.py` become offline diagnostics under `diagnostics/` and are not imported by runtime code.

`SeoMatcherRun` is a trace/snapshot row, not a super-entity. Its only jobs:

- Snapshot the inputs needed to replay the decision (sku_atoms_id, query_atoms_version, policy_version, category_profile_version, readiness snapshot, embedding model, provider used).
- Carry `quality_mode` and `degraded_reasons`.
- Give downstream readers a stable id.

It does not store meanings themselves. It references them.

## 3. Quality-mode visibility

Every decision-carrying row gets two new columns:

- `quality_mode ∈ {full, preview, degraded, fallback}`
- `degraded_reasons: list[structured_reason]`

Rules for computing `quality_mode` at run time (deterministic function of the pipeline state, not a human flag):

- `full` — real LLM outputs in evidence, real embedding provider, cache hits on current prompt version, reviews present, vision present if applicable.
- `preview` — any deterministic proxy in the path (most importantly `LocalPreviewEmbeddingProvider`), or any cache artifact from an older prompt version.
- `degraded` — one or more evidence sources missing but the run still produced meaningful output (cold expressive cache, zero reviews, vision not available).
- `fallback` — the product-data-only fallback path was taken (LLM SKU draft failed, atoms extraction fell back, etc.).

Rows carrying `quality_mode`:

- `SeoMatcherRun`
- `SeoSkuMeaningAnnotation`
- `SeoSkuQuerySet`
- `SeoContentVersion`

Rows do not propagate quality from upstream silently. Each layer computes its own and includes the worst upstream mode in its `degraded_reasons`.

**UI contract:** exactly one badge per decision, one enum, one color for each state. Operators see the badge everywhere. Debug panel shows the reasons list.

## 4. Category-specific logic representation

All category-specific rules live in `SeoCategoryProfile` (project_id, category_id, version, payload, status, activated_at). The payload includes:

- product-type canonical names and synonyms
- material / audience / expressive / occasion / recipient term groups
- hard-conflict rules (e.g., `термокружка` vs regular mug, volume mismatch thresholds, set/single, `без рисунка`)
- bucket cutoffs and genericness penalty weights
- title rules (main-query position, category-specific forbidden phrases)
- brand voices available for that category
- review-scope parameters (min_rating, max_reviews) specific to the category

The shared engine carries none of these lists in code. Matcher stages and generation brief receive the profile as a parameter.

Category tier (new column on `SeoCategoryMatchingReadiness`):

- `preview_only` — seeded profile, no labels yet, not promotable.
- `eligible_for_preview` — ≥ 50 labels, reduced acceptance gate passed, generation allowed in shadow.
- `acceptance_passed` — full acceptance gate met, generation may progress to candidate.

Category 812 is the only calibrated profile on day one. Every other category starts at `preview_only`.

## 5. Generation operating mode

Generation is a research preview for one category. Four states of `SeoContentVersion.content_kind`:

1. `preview` — default output of any generation run. Not publishable. Not shown outside the single-SKU page.
2. `candidate` — manually promoted after human rubric review. Requires category tier ≥ `eligible_for_preview`.
3. `approved` — operator sign-off. Requires category tier `acceptance_passed`.
4. `published` — reserved. No code path yet.

**Promotion rules (enforced in the backend, not by operator discipline):**

- `preview → candidate` requires:
  - matcher acceptance gate green for the category, AND
  - a stored `seo_generation_human_review` with rubric ≥ 8/10 on relevance and ≥ 8/10 on fidelity, zero unsupported hard claims.
- `candidate → approved` requires:
  - category tier `acceptance_passed`, AND
  - explicit operator sign-off.

Generation is never retried against its own internal relevance score. `SEO_GENERATION_MAX_ATTEMPTS = 1` soft retry is allowed only on validator hard errors (malformed sections). The internal `build_seo_relevance_report` / V2 stays as a diagnostic lint, never as a promotion gate.

## 6. Eval as a gate

Eval becomes a runnable backend endpoint, not a script + spreadsheet.

```
POST /projects/{p}/seo/eval/matcher/run
  body: { category_id, label_set_id }
  returns: { accuracy, primary_precision, primary_recall, bad_primary_count,
             hard_conflict_primary_count, per_error_type_breakdown,
             matcher_run_ids_considered, category_profile_version }
  side-effect: writes eval_run record; if thresholds met,
               flips SeoCategoryMatchingReadiness.eligibility_tier
```

Acceptance gate thresholds (from `23_atoms_v1_design_and_implementation_plan.md`):

- accuracy ≥ 70%
- primary precision ≥ 70%
- primary recall ≥ 65%
- bad primary reduced ≥ 70% vs previous matcher version
- zero hard-conflict class systematically promoted to Primary

Reduced gate for `preview_only → eligible_for_preview`:

- accuracy ≥ 50%
- zero hard-conflict class systematically in Primary

Eval consumes labels from a typed table (`seo_eval_labels`), not from `artifacts/meaning_atoms/*`. Existing 191 labels are imported once as the seed label set for category 812.

## 7. Current flow vs candidate flow vs compare layer

Three clearly separated paths, one promotion decision.

### Current path (kept running)

- `query_meaning_matcher/matcher.py::run_meaning_aware_matcher` with soft-score-first ordering and post-hoc atoms gate.
- `products.py::run_query_selection` writing `SeoSkuQuerySet` + `SeoSkuQuerySetItem`.
- `generation/service.py::run_seo_generation` behind existing flags.
- No `quality_mode`, no `matcher_run_id` tie-in.

This keeps working for category 812 during validation. No breaking changes in iteration 1.

### Candidate path (built alongside)

- New `run_matcher_v2` in `services/seo/matcher_v2/` (staged, eligibility-first, reads `SeoCategoryProfile`, writes `SeoMatcherRun` + `SeoMatcherResult`).
- New `services/seo/atoms/v1/` (promoted from `experiments/meaning_atoms/v1.py`, authoritative schema).
- `SeoSkuQuerySet.matcher_run_id` FK populated when the candidate path is selected.
- Generation wrapper `generate_seo_card_v2` that uses `SeoMatcherRun` as input and emits `SeoContentVersion(content_kind="preview", mode_used="candidate", quality_mode=...)`.

Candidate path is reached via:

- new API endpoints: `POST /seo/matcher/v2/run`, `POST /seo/generation/v2/run`
- or via the existing endpoints with `?flow=candidate` / env flag `SEO_CANDIDATE_FLOW_DEFAULT`.

### Compare layer (new UI + one diagnostic endpoint)

- `GET /seo/compare/matcher?project&category&nm_id` — returns current-vs-candidate bucket diff on the same SKU.
- `GET /seo/compare/generation?project&category&nm_id` — returns two content versions side by side with diff highlighting.
- UI: a compare panel in the SKU page and in the generation page. Metrics strip at top showing eval deltas.

### Promotion decision

After two iterations and enough compare-layer evidence:

- If the candidate eval gate is green and human review confirms parity-or-better, `SEO_CANDIDATE_FLOW_DEFAULT` is flipped and current-path endpoints start forwarding to the candidate path. Old current-path code stays in the repo for one release as a rollback lever, then is removed.
- If the candidate does not meet the gate, the candidate stays behind its flag and a new iteration is scoped.

## 8. Boundaries that must not blur

- Current-path code does not read candidate-path persistence (`SeoMatcherRun`, `SeoCategoryProfile`, candidate `content_kind`).
- Candidate-path code does not write into current-path persistence fields that would corrupt its semantics (e.g., does not overwrite `SeoSkuQuerySetItem.reasons_payload` silently — it writes `SeoMatcherResult` and keeps the old rows as they were).
- Compare layer is read-only. It never writes decisions.
- Eval endpoint writes only to eval tables and to the readiness tier column. It never writes buckets.

## 9. What moves, what stays, what freezes

**Stays unchanged in this plan:**

- Query CSV ingestion, normalization, unified dataset.
- Pruning, clustering, hybrid annotation, profile extraction (diagnostics).
- Category bootstrap orchestration (inputs are the same; outputs now include `category_profile_version` reference).
- Provider boundary, embeddings infrastructure (the default provider on the candidate path must be documented).

**Moves to candidate flow:**

- Matcher decision logic (staged).
- Atoms code (from `experiments/` to `services/seo/atoms/v1/`).
- Generation lifecycle (four-state `content_kind`, promotion rules, gates).
- Category-specific rules (to `SeoCategoryProfile`).

**Frozen (deprecation notice + import guard, not deleted yet):**

- `services/seo/clustering/*` (SKU clustering placeholders).
- `SeoSkuClusterRun`, `SeoSkuCluster`, `SeoSkuClusterAssignment`.
- `SeoClusterProfile`, `SeoClusterProfileVersion`.
- `SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation`.
- `scoring/service.py::create_score_run`, `persist_query_score`.

**Deferred to a later iteration (not in this package):**

- Stable category scope migration.
- Multi-category rollout.
- Learnable category profile.
- Batch generation / WB Content API publish.
- Deletion of frozen schema (drop in iteration N+2 or later).

## 10. Module-as-system summary

- Inputs: product data, WB reviews, WB search reports, imported query CSVs.
- Evidence layer: atoms (SKU / vision / query / deterministic guards) tied to a `SeoCategoryProfile` version.
- Decision layer: one staged matcher function producing one `SeoMatcherRun` per SKU/category per trigger.
- Output layer: query selection view + generation preview, both reading the matcher run.
- Gates layer: eval endpoint flips category tiers; generation promotion is gated by tier + human review.
- Visibility layer: `quality_mode` everywhere; compare layer shows current vs candidate; no silent fallbacks, no confirmed-equals-quality, no category-generality claim.
