# 02. Parallel Validation Strategy

Audience: CTO / product / lead engineer
Date: 2026-04-23

---

## 1. Why parallel, not replace

The audits already established that current matcher and current generation reach users through the UI. Rip-and-replace would cut the only working feedback channel. Parallel validation lets the candidate operating model grow in daylight, against the same SKUs, with measurable deltas, before any promotion.

The guiding rule: **no promotion without measured evidence of parity-or-better.**

## 2. What runs in parallel

The validation methodology has four layers running at the same time:

1. **Current path** — untouched in iteration 1. Keeps serving category 812.
2. **Candidate path** — new staged matcher + atoms v1 (promoted) + category profile + generation preview lifecycle. Reachable by explicit endpoint or flag.
3. **Compare layer** — read-only diagnostics surface. Computes per-SKU bucket deltas and per-card generation deltas. Does not write decisions.
4. **Eval harness** — ingests labels, runs both paths against them, produces acceptance metrics per path.

## 3. What may run in shadow mode

Safe to run in shadow (no user-visible change):

- `run_matcher_v2` invoked automatically whenever the current matcher runs for a SKU. Writes `SeoMatcherRun` in the background. Does not affect query selection UI.
- `SeoCategoryProfile` loaded in the background to compute a candidate eligibility verdict next to the current one.
- Candidate atoms extraction (post-promotion from `experiments/` namespace) running alongside current atoms.
- Candidate generation run triggered only on operator request; output stored with `content_kind="preview"` and `mode_used="candidate"`.

Not safe to run in shadow (must stay isolated):

- Any change to `SeoSkuQuerySet.status` semantics — staged only on the candidate path.
- Any change to `SeoContentVersion.status` — new `content_kind` values only on candidate.
- Anything that would mutate the current-path's reasons_payload or override current-path's bucket decisions.

## 4. Isolation boundaries

Strict isolation rules between paths:

- Candidate persistence lives on new tables (`SeoMatcherRun`, `SeoMatcherResult`, `SeoCategoryProfile`, `seo_eval_labels`, `seo_eval_runs`, `seo_generation_human_review`).
- New columns on existing tables (`quality_mode`, `degraded_reasons`, `matcher_run_id`, `eligibility_tier`, `selection_state`, `trust_state`, `content_kind` expanded enum) default to `unknown` / `null` / `legacy` for rows created by the current path.
- Candidate-path writes never overwrite current-path rows. If candidate wants to record an opinion about an existing SKU, it creates a new candidate-flagged record.
- Current path does not read new columns. Readers on current-path endpoints ignore them.
- The compare layer is the only place both paths are read together.

## 5. Versioning

Every candidate artifact carries a version tuple and is pinned:

- `matcher_version` — bumped on any change to `run_matcher_v2` stage ordering or stage contents.
- `policy_version` — bumped on any change to hard-conflict rules or bucket caps not coming from the profile.
- `category_profile_version` — auto-incremented on profile payload change; prior versions remain queryable.
- `atoms_schema_version` — pinned in `services/seo/atoms/v1/` and recorded on atoms rows.
- `generation_prompt_version` — already exists (`GENERATION_PROMPT_VERSION`); keep, and also record on `SeoContentVersion`.
- `eval_label_set_version` — a label set is immutable; new labels make a new set.

All of these are written into `SeoMatcherRun` on every run, and into `SeoContentVersion` on every generation. This is what makes replay and compare possible.

## 6. Comparing current vs candidate results

Two comparison surfaces:

### 6.1 Matcher compare

Endpoint: `GET /projects/{p}/seo/compare/matcher?category&nm_id`

Returns:

```json
{
  "sku": {"project_id": 1, "category_id": 812, "nm_id": 292541341},
  "current": {
    "query_set_id": 1234,
    "buckets": {"primary": [...], "secondary": [...], "broad": [...], "rejected": [...]},
    "matcher_version": "meaning_aware_v1",
    "quality_mode": "unknown"
  },
  "candidate": {
    "matcher_run_id": 987,
    "buckets": {...},
    "matcher_version": "matcher_v2",
    "policy_version": "policy_v1",
    "category_profile_version": 3,
    "quality_mode": "preview"
  },
  "delta": {
    "moved_to_primary": [...],
    "moved_out_of_primary": [...],
    "newly_rejected_on_conflict": [...],
    "agreement_rate": 0.71
  }
}
```

UI: a compare panel on the SKU page. Two columns with bucket assignments, a third column with the movement reason per changed query. Operators can mark a candidate decision as "better" / "worse" / "same" — this is the human verdict signal.

### 6.2 Generation compare

Endpoint: `GET /projects/{p}/seo/compare/generation?category&nm_id`

Returns the two latest `SeoContentVersion` rows (current-flow draft and candidate-flow preview) plus a side-by-side diff view of title, characteristics, description.

UI: a compare view on the generation page with:

- title diff (word-level),
- characteristics diff (field-level),
- description diff (paragraph-level),
- matched/missing/conflict atom panels for both,
- `quality_mode` badge for both,
- a human rubric form (relevance / fidelity / unsupported-claims checkbox).

The rubric form writes `seo_generation_human_review`. This is the human half of the promotion gate.

## 7. What must be visible in UI

Non-negotiable UI additions (minimum viable):

- `quality_mode` badge on every SKU summary card, query-selection panel, generation panel.
- Category tier badge on the category page header.
- `matcher_run_id` link on the query-selection page (opens a read-only trace view).
- Compare panel on SKU page (matcher) and generation page (generation).
- Separation of `selection_state` (Approved / Draft) and `trust_state` (Validated by eval / Unvalidated).
- A prominent "Research preview" banner on the generation page when `mode_used != operational`.
- A clear "internal lint score" label next to the current relevance score so operators stop treating it as a quality signal.

## 8. Human verdict and eval metrics combined

Promotion decision uses both signals. Neither alone is enough.

Per category, the candidate path is promotion-eligible only when:

- Eval harness reports acceptance gate green on the latest labels (thresholds in `01_target_operating_model.md §6`).
- Compare layer reports agreement_rate trending toward parity-or-better on a fixed SKU panel.
- Human verdicts on matcher compare show candidate ≥ current on ≥ 70% of compared SKUs.
- Human rubric on generation compare shows candidate ≥ 8/10 relevance and ≥ 8/10 fidelity on ≥ 10 SKUs, with zero unsupported hard claims.

Leadership signs off on promotion once both categories of signal are green for category 812.

## 9. Promotion criteria (summary table)

| Transition | Required signals |
|---|---|
| Candidate matcher becomes default for category 812 | Eval gate green for 812 + human verdicts favor candidate ≥ 70% + no blocking rollback event in 7 days |
| Category tier `preview_only → eligible_for_preview` | Reduced eval gate green + ≥ 50 labels collected |
| Category tier `eligible_for_preview → acceptance_passed` | Full eval gate green |
| Generation `preview → candidate` | Category tier ≥ `eligible_for_preview` + human rubric green on ≥ 10 SKUs |
| Generation `candidate → approved` | Category tier `acceptance_passed` + explicit operator sign-off |
| Generation `approved → published` | Not enabled in this plan |

## 10. Rollback criteria

Candidate flow is disabled (flag flipped off) when any of the following occurs:

- Eval metrics regress on a rerun against the frozen label set.
- Human verdicts flip from favor-candidate to favor-current on a fresh panel.
- Candidate produces a hard-conflict Primary that current path correctly rejected, on any SKU.
- `quality_mode` = `fallback` rate for candidate exceeds current path's equivalent metric.
- Any data-integrity incident traced to the candidate path (wrong category scope, unexpected write, migration breakage).

Rollback is a single config flip (`SEO_CANDIDATE_FLOW_DEFAULT=false`). It does not require a schema migration because the candidate path is additive.

## 11. How to avoid supporting two systems forever

Hard stop rules:

- If the candidate path has not been promoted by the end of iteration 2, leadership is presented with one of three options (promote / extend / reject). No silent drift.
- If the candidate path is promoted, the current path is archived under `legacy/` with a one-release sunset window. Next iteration after promotion deletes it.
- If the candidate path is rejected, the candidate tables stay but are marked frozen and deleted in iteration N+2. Findings feed the current path.
- Compare layer endpoints and UI panels are explicitly scoped as temporary (deprecate when one path is default).

Every artifact created for validation has an owner and an expiry condition. This is tracked in `03_workstreams_and_scope.md`.
