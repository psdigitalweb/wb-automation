# Category 2841 Report - Phase 1 Operator Review

> Date: 2026-04-25  
> Project: `1`  
> Category: `2841` / `Ланч-боксы`  
> Report scope: Phase 1 Step 10, docs/artifacts only. No runtime code, profile payload, activation, matcher logic, UI, migrations, LLM calls, or WB API calls were changed for this report.

---

## 1. Executive Summary

Phase 1 is successful as a backend feasibility proof for a second category: generic derive produced a valid `category_profile_v1`, self-check passed, the profile was persisted inactive first, activated by an explicit safe action, and `matcher_v2` completed the required 3-SKU smoke run against the active 2841 profile.

This does not prove production-quality automation for category 2841. There are no strict eval labels for this category, and the smoke results exposed a product-quality blocker: two of three SKU produced pathological bucket distributions (`915 primary / 24 secondary / 2 broad / 0 rejected`) while SKU atoms were missing and the active profile remained permissive. See `STEP_9D_2841_MATCHER_QUALITY_FAILURE.md`.

Key verdict: backend portability passed; product-quality blocked. Category 2841 is not production-proven, and Phase 2 blocked until Phase 1Q passes or the operator explicitly accepts a waiver.

---

## 2. Phase 1 Outcome

Decision: `backend portability passed; product-quality blocked pending Phase 1Q`.

What was proved:

- Generic derive for category `2841` succeeded without the old skeleton-only / 812-only path.
- The resulting profile has `schema_version="category_profile_v1"`.
- `self_check.status="passed"`.
- Persist and activation remained separate actions: profile row `id=2` was first saved inactive, then activated through `scripts/activate_category_profile.py --profile-id 2`.
- `matcher_v2` ran successfully for 3 SKU using active profile `id=2`, version `v1.2841.generic.46889ee8`.
- No `ProfileMissingError` occurred during the 3-SKU smoke.
- No legacy fallback was observed.
- Runtime traces were replayable for all 3 smoke runs.
- The exact old alias conflict `query requires ланч, SKU is ланчбокс` was removed.
- Orders/conversion were not used as scoring or label-generation evidence.

What was not proved:

- Production-quality accuracy for category 2841. There are no strict eval labels for 2841; `eval_smoke` was intentionally skipped with the recorded reason that no strict labels were supplied.
- Full product-quality automation. The 3-SKU smoke is a runtime and qualitative sanity gate, not a replacement for operator review.
- Product-quality matcher selectivity. The 3-SKU smoke passed runtime but failed/blocked product-quality because two SKU routed almost the whole 941-query corpus into `primary`; this is documented in `STEP_9D_2841_MATCHER_QUALITY_FAILURE.md`.
- Broad category generalization across 5-7 categories. That is Phase 2.
- Final SEO brief quality or copywriter-ready export. That remains later roadmap scope.

---

## 3. Active Profile State

- Active profile id: `2`
- Version: `v1.2841.generic.46889ee8`
- Project/category: `(project_id=1, category_id=2841)`
- `is_active`: `true`
- `self_check.status`: `passed`
- `subject.primary`: `ланчбокс`
- `subject.primary_aliases`: `ланчбокс`, `ланч`, `бокс`
- `related_but_different`: empty
- `hard_conflicts_count`: `0`
- Snapshot path: `config/seo/category_profiles/1/2841/v1.2841.generic.46889ee8.json`

Activation evidence:

- `tests/seo/phase1/category_2841/post_persist_profile.json` records profile `id=2` as `is_active=false`.
- `tests/seo/phase1/category_2841/post_activation_profile.json` records the same profile `id=2` as `is_active=true`.
- `tests/seo/phase1/category_2841/active_profile_check.json` records exactly one active 2841 profile and keeps active 812 profile `v1.812.skeleton.243953b2` intact.

---

## 4. Derive / Profile Quality Review

The derive run selected `ланчбокс` as the primary subject from product-type axis evidence, not from hardcoded category-specific Python logic. The profile aliases are intentionally compact: `ланчбокс`, `ланч`, `бокс`.

Evidence summary:

- Evidence status: `ready`
- Axes source: `llm_enhanced`
- Axes id: `17`
- Product type axes count: `30`
- Use case axes count: `16`
- Audience axes count: `6`
- Attribute axes count: `32`
- Corpus signals: `queries_sampled=1596`, `distinct_queries=1596`, `top_queries_sampled=200`
- `csv_subject_match_share=1.0`
- Evidence hash: `sha256:46889ee801842d17f377216bfd01e0095160e0928a40d0125e183dd1c217ae8d`

Self-check summary:

- Status: `passed`
- `subject_coverage`: pass, `subject_match_share=1.0000`
- `bucket_cutoffs_monotonic`: pass, `primary=0.6`, `secondary=0.35`, `broad=0.15`
- `hard_conflicts_cover_related`: pass, no related subjects to cover
- `hard_conflicts_syntax`: pass
- `guards_target_known_fields`: pass
- `no_economic_decision_fields`: pass
- `eval_smoke`: skipped because no strict eval labels were supplied

Quality notes:

- `hard_conflicts_count=0` is consistent with `related_but_different=[]`; it is not itself a failure.
- The profile is deliberately minimal. It proves category-agnostic profile generation and runtime consumption, but it does not yet encode richer lunchbox-specific constraints such as compartments, heating, material, set/quantity, thermos bag, or cutlery as hard rules.
- Derive diagnostics explicitly state that weak axes were recorded as diagnostics and not promoted to hard conflicts without explicit constraint evidence.

---

## 5. Matcher Smoke Review

Smoke gate: backend portability passed for runtime feasibility; product-quality blocked.

Common runtime evidence:

- Expected profile version: `v1.2841.generic.46889ee8`
- Profile version seen: `v1.2841.generic.46889ee8`
- Profile id seen: `2`
- Profile active seen: `true`
- SKU count smoked: `3`
- Matcher run ids: `81`, `79`, `80`
- Result rows exist for all runs.
- Replayable traces exist for all runs.
- Legacy fallback seen: `false`
- `ProfileMissingError` count: `0`
- Exact old alias conflict count: `0`
- Fuzzy alias rows remain: `3`; notes clarify that these are not the old exact mass alias conflict.

Per-SKU summary:

| SKU | Run | Primary | Secondary | Broad | Rejected | Qualitative note |
|---|---:|---:|---:|---:|---:|---|
| `10533814` | `81` | 915 | 24 | 2 | 0 | Very permissive distribution; top queries are lunchbox-related. |
| `10533815` | `79` | 3 | 4 | 736 | 198 | Behaves differently: mostly broad/rejected. Needs operator review. |
| `893327503` | `80` | 915 | 24 | 2 | 0 | Very permissive distribution; top queries are lunchbox/school-food related. |

Top query examples from smoke artifacts:

- SKU `10533814`: primary examples include `ланч бокс`, `ланчбокс на работу`, `ланчбокс с подогревом`; broad examples include lunchbox-with-thermo-mug queries.
- SKU `10533815`: primary examples include `ланч бокс в школу милый`, `ланч бокс милый`, `ланчбокс милый`; broad examples include general lunchbox queries; rejected examples include `ланч бокс с термосумкой`, `набор ланч боксов с термосумкой`, `ланч бокс металлический`.
- SKU `893327503`: primary examples include `ланчбокс для еды в школу`, `ланч бокс в школу эстетичный`, `ланч бокс для еды в школу`; broad examples include lunchbox-with-thermo-mug queries.

Interpretation:

- The runtime gate is green: matcher can consume the active 2841 profile and produce bucketed, traceable results.
- The product-quality signal is not green. Two SKUs are extremely primary-heavy (`915/941 primary`) with `0 rejected`; Step 9D identifies this as a quality failure tied to missing SKU atoms, a permissive profile, broad aliases, and thresholds that do not discriminate enough without atoms.
- The 3-SKU smoke passed runtime but failed/blocked product-quality due to pathological bucket distributions. Category 2841 must not be called production-proven from this smoke.

---

## 6. SKU-Level Qualitative Observations

Selected SKU annotations:

- `10533814`
- `10533815`
- `893327503`

The third annotation, SKU `10533814`, was created from local deterministic product evidence/projection through the sanctioned SKU meaning annotation API. Artifact metadata records `source="local_evidence_product_projection"`, `projection_version="v1_mvp"`, `no_llm=true`, and `no_wb_api=true`; in plain terms, no LLM/WB API was used. This was done to close the Step 9 data blocker without external calls or matcher/profile changes.

Annotation state:

- All 3 selected SKUs have `SeoSkuMeaningAnnotation` payloads.
- SKU `10533815` has one `sku_vision` atom and one `sku_meaning` atom.
- SKU `10533814` and `893327503` have zero recorded atoms in the smoke artifact, so their matcher behavior relies more heavily on meaning/profile signals and less on atom-gate evidence.
- The smoke artifact records `atoms_gate_enabled=false` in matcher metrics, with reasons showing `atoms gate skipped: missing SKU or query atoms` on examples.

Qualitative reading:

- `10533814` and `893327503` look broadly lunchbox-aligned, but their very high primary counts suggest the profile is permissive.
- `10533815` is the useful counterexample: it narrows hard into a few primary/secondary candidates while pushing most results to broad/rejected. This difference should be inspected against the SKU's actual product evidence before deciding whether the behavior is correct.

---

## 7. Known Risks / Limitations

- No strict eval labels exist for 2841; Phase 1 cannot make an accuracy claim.
- The profile is minimal and has no hard conflicts. That is acceptable for feasibility, but likely insufficient for mature product-quality automation.
- Lunchbox-specific constraints are not fully materialized into guards/hard conflicts.
- The 3-SKU smoke set is small and partly constrained by available SKU annotations.
- Two of three runs are primary-heavy, which may hide weak selectivity.
- SKU `10533815` behaves differently and needs review rather than silent normalization.
- Some SKU/query atom coverage is missing; atom gate is not the dominant quality proof in this smoke.
- Phase 1 proves generic derive + activation + matcher runtime feasibility, not full automated SEO quality.
- Phase 2 blocked until Phase 1Q passes or the operator explicitly accepts a waiver.

---

## 8. Decisions Needed From Operator

1. Confirm that Phase 1 acceptance is limited to backend portability passed, not product-quality approval.
2. Review SKU `10533815` specifically: should the mostly broad/rejected distribution be considered correct for this SKU, or a signal that derive/profile/atom coverage needs improvement?
3. Decide whether any Phase 2 waiver is acceptable before Phase 1Q passes; absent waiver, Phase 2 remains blocked.
4. Decide whether future 2841 work should enrich constraints for thermos bag, heating, compartments, material, set/quantity, and cutlery before production use.

Recommended decision for this report:

- Do not proceed to Phase 2 as normal onboarding.
- Treat Phase 1 as closed only for backend portability.
- Keep 2841 marked as not production-proven until Phase 1Q product-quality gates pass or the operator explicitly waives the risk.

---

## 9. Recommendation For Next Phase

Move to Phase 1Q with the following framing:

- Treat Phase 1 as closed for backend portability.
- Do not claim full product-quality automation or production readiness for 2841.
- Treat Phase 2 as blocked until Phase 1Q passes or the operator explicitly accepts a waiver.
- Start Phase 1Q with SKU Evidence Audit for `535441190`, then close the 2841 matcher-quality blocker described in `STEP_9D_2841_MATCHER_QUALITY_FAILURE.md`.
- Consider a follow-up derive-quality task if multiple categories show minimal profiles with no useful constraints or weak atom coverage.

---

## 10. Appendix: Artifact Paths And Run IDs

Profile / derive artifacts:

- `tests/seo/phase1/category_2841/derive_dry_run.json`
- `tests/seo/phase1/category_2841/derive_diagnostics.json`
- `tests/seo/phase1/category_2841/profile_self_check.json`
- `tests/seo/phase1/category_2841/post_persist_profile.json`
- `tests/seo/phase1/category_2841/post_activation_profile.json`
- `tests/seo/phase1/category_2841/active_profile_check.json`
- `config/seo/category_profiles/1/2841/v1.2841.generic.46889ee8.json`

Matcher / SKU artifacts:

- `tests/seo/phase1/category_2841/sku_meaning_status.json`
- `tests/seo/phase1/category_2841/matcher_smoke_summary.json`
- `tests/seo/phase1/category_2841/matcher_smoke_2841.json`
- `tests/seo/phase1/category_2841/matcher_runs_summary.json`
- `tests/seo/phase1/category_2841/operator_review_notes.md`

Run ids:

- 2841 smoke run for SKU `10533814`: `81`
- 2841 smoke run for SKU `10533815`: `79`
- 2841 smoke run for SKU `893327503`: `80`
- 812 sanity run for SKU `291861306`: `82`

Profile ids / versions:

- 2841 active profile: `id=2`, `version=v1.2841.generic.46889ee8`
- 812 active profile retained: `id=1`, `version=v1.812.skeleton.243953b2`
