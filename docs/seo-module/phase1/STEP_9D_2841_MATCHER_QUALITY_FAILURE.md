# Phase 1 Step 9D - 2841 Matcher Quality Failure Analysis

Date: 2026-04-25

Scope: audit/report only. No code, profile, activation, DB, UI, migration, LLM, WB API, or new matcher-run changes are part of this report.

## 1. Executive finding

Runtime smoke passed, but product-quality smoke failed.

The 2841 matcher is currently not discriminating enough for product use. Two of three SKU route almost the entire 941-query corpus into `primary`:

- SKU `10533814`: `915 primary / 24 secondary / 2 broad / 0 rejected`
- SKU `893327503`: `915 primary / 24 secondary / 2 broad / 0 rejected`

This is caused by the combination of:

- missing SKU atoms for those two SKU, which disables the atoms gate;
- a very permissive active profile for 2841;
- broad product-type aliases (`ланч`, `бокс`) that make most query/SKU pairs product-type compatible;
- scoring thresholds/weights that allow semantic similarity plus generic product-token overlap to cross the `primary` cutoff for nearly the whole category corpus.

The old exact alias-conflict failure is not back: exact count for `query requires ланч, SKU is ланчбокс` is `0`. The current failure is the opposite direction: after compatibility, the matcher accepts too much.

## 2. Evidence from bucket distributions

Artifact: `tests/seo/phase1/category_2841/matcher_smoke_summary.json`.

The full 3-SKU smoke closed structurally:

- `sku_count_available = 3`
- `profile_version_seen = v1.2841.generic.46889ee8`
- `profile_active_seen = true`
- `profile_missing_errors = 0`
- `legacy_fallback_seen = false`
- replayable traces exist for all three runs

But the bucket distribution is pathological:

| SKU | run_id | primary | secondary | broad | rejected | atoms gate |
|---|---:|---:|---:|---:|---:|---|
| `10533814` | `81` | 915 | 24 | 2 | 0 | disabled |
| `10533815` | `79` | 3 | 4 | 736 | 198 | enabled |
| `893327503` | `80` | 915 | 24 | 2 | 0 | disabled |

The over-primary pattern is almost identical for `10533814` and `893327503`. That symmetry is important: it points away from individual product nuance and toward a shared fallback path when SKU atoms are absent.

The persisted `metrics.buckets` inside matcher runs are capped display counts (`primary: 100` for over-primary runs), while `SeoMatcherResult` rows and artifact `bucket_counts` show the true persisted distribution (`primary: 915`). The quality failure is in persisted result rows, not just UI slicing.

## 3. Evidence from SKU annotations / atoms

Artifact: `tests/seo/phase1/category_2841/sku_meaning_status.json`.

Current 2841 annotations:

| SKU | annotation id | product_type | SKU atoms | vision atoms | source |
|---|---:|---|---:|---:|---|
| `10533814` | `26` | `ланчбокс` | 0 | 0 | local deterministic product projection |
| `10533815` | `25` | `ланчбокс` | 1 | 1 | product SEO analysis |
| `893327503` | `7` | `ланч` | 0 | 0 | SKU meaning preview annotation |

Matcher evidence:

- `10533814` run `81`: `metrics.atoms_gate_enabled = false`, reasons include `atoms gate skipped: missing SKU or query atoms`.
- `893327503` run `80`: `metrics.atoms_gate_enabled = false`, reasons include `atoms gate skipped: missing SKU or query atoms`.
- `10533815` run `79`: `metrics.atoms_gate_enabled = true`, and many candidates are capped to `broad` or `rejected` by missing hard requirements.

This proves the main behavioral split: only the SKU with atoms (`10533815`) gets structured hard-requirement gating. The two SKU without atoms rely almost entirely on soft score and profile rules.

## 4. Evidence from scoring components

Artifacts/code inspected:

- `tests/seo/phase1/category_2841/matcher_smoke_2841.json`
- `src/app/services/seo/matcher_v2/stages/soft_score.py`
- `src/app/services/seo/matcher_v2/stages/bucket_cap.py`
- `src/app/services/seo/query_meaning_matcher/profile_matcher.py`
- `src/app/services/seo/query_meaning_matcher/runtime_helpers.py`
- `src/app/services/seo/category_profile_rules.py`

For over-primary SKU `10533814`, top-primary examples show the same additive pattern:

- query `ланч бокс`: score `0.7404`, semantic similarity `0.8818`
- components: `0.34 * semantic_similarity` plus `product_score=0.16`, `attribute_score=0.08`, `audience_score=0.06`, `specificity_bonus=0.08`, `frequency_boost=0.0606`
- reasons: product type compatible via alias `ланч`; attribute/audience matched on `бокс, ланч`; no hard constraints; atoms gate skipped

For over-primary SKU `893327503`, the same mechanism is even stronger:

- query `ланчбокс для еды в школу`: score `0.8461`, semantic similarity `0.8142`
- components: `product_score=0.22`, `use_case_score=0.10`, `attribute_score=0.08`, `audience_score=0.06`, `specificity_bonus=0.08`, frequency boost
- reasons: product type matched `ланч`; use-case/attribute/audience overlap; no hard constraints; atoms gate skipped

For constrained SKU `10533815`, the same soft score often starts high, but atoms gate caps it:

- query `ланч бокс`: soft components would score above primary, but final score is `0.45` and bucket is `broad`
- reason path includes `atoms bucket: broad` and missing/weak hard-requirement signals
- rejected examples include missing hard requirements such as volume, transparency, use case, motif, or material conflict

Code-level mechanism:

- `compute_soft_score()` adds `0.34 * semantic_similarity` to product/overlap/specificity/frequency components.
- `decide_bucket()` accepts `primary` when `score >= profile.scoring.bucket_cutoffs.primary` (`0.60`) and any overlap exists or semantic similarity is at least `0.72`.
- `_apply_atoms_gate()` returns the original bucket unchanged when `sku_atoms is None or not query_atoms_payload`, with reason `atoms gate skipped: missing SKU or query atoms`.

So when SKU atoms are absent, there is no second-stage cap to demote "generic category-compatible" matches.

## 5. Root cause hypotheses ranked by likelihood

1. Most likely: SKU atoms availability is the main direct trigger.

Evidence: the only SKU with atoms (`10533815`) has discriminating output (`3 primary / 4 secondary / 736 broad / 198 rejected`), while both SKU without atoms have nearly identical over-primary output (`915 primary / 24 secondary / 2 broad / 0 rejected`). The runtime helper explicitly skips atoms gate when SKU atoms are absent.

2. Very likely: active profile `v1.2841.generic.46889ee8` is too weak/permissive for product-quality matching.

Evidence from profile snapshot:

- `related_but_different = []`
- `hard_conflicts = []`
- `constraints.derive_from_query_tokens = []`
- `constraints.derive_from_sku_meaning = []`
- `query_guards.required_atoms = []`
- `query_guards.excluded_atoms = []`
- `sku_guards.characteristic_mappings = []`
- `sku_guards.functional_token_mappings = []`
- `negative_token_prefixes = []`

The profile self-check passed structural checks, but it did not prove product-quality discrimination. The report even records `eval_smoke = skip` because 2841 has no strict labels.

3. Very likely: alias compatibility is now broad enough to inflate relevance.

Evidence: `primary_aliases` and `product_type_aliases` include `ланч`, `бокс`, and `ланчбокс`. Product-type detection also sets `ланчбокс` when queries contain any of these markers. The Step 9B fix correctly removed the bad exact conflict, but these aliases also make generic category terms contribute `product_score`, `attribute_score`, and `audience_score` for most queries.

This does not mean the fix is wrong; it means compatibility alone cannot serve as product-quality relevance.

4. Likely: thresholds/weights are unsuitable for 2841 without atoms.

Evidence: with `primary=0.60`, a generic query with high semantic similarity and broad alias overlap can pass primary. For `10533814`, `ланч бокс` reaches `0.7404`; for `893327503`, many school/food queries reach `0.84+`. The scoring defaults were inherited from the generic profile contract and not calibrated on 2841 product-quality behavior.

5. Possible but not proven: query meaning / embeddings are too homogeneous.

Evidence: the corpus is one tight category, and semantic similarity is high for broad category terms. But this report did not rerun embeddings or inspect all vector distributions, so this remains secondary.

## 6. What is proven vs not proven

Proven:

- Runtime smoke passed: active profile was loaded, no `ProfileMissingError`, no legacy fallback, result rows and replayable traces exist.
- Product-quality smoke failed: two SKU classify 915/941 queries as primary.
- The pathological SKU both lack SKU atoms, and their runs have `atoms_gate_enabled=false`.
- The non-pathological SKU has SKU and vision atoms, and its run has `atoms_gate_enabled=true`.
- The active 2841 profile is structurally valid but semantically permissive: no constraints, no hard conflicts, no required/excluded guards, no negative prefixes.
- The exact old alias conflict message count is `0`.
- Alias compatibility is broad enough that `ланч`/`бокс` produce positive product/attribute/audience signals for most category queries.

Not proven:

- That adding atoms alone will fully fix 2841 quality for all SKU.
- That profile changes alone will be enough without SKU atom coverage.
- That the Step 9B alias compatibility fix should be reverted. Current evidence says it solved the mass false reject and exposed missing discrimination.
- That strict numeric thresholds should be changed globally. Any threshold change must be profile/category-aware and regression-checked against 812.
- That Phase 2 can proceed safely without either a quality fix or an explicit downgrade of the Phase 1 goal.

## 7. Recommended fix sequence

1. Add a quality precondition for Step 9 acceptance: matcher smoke is not closed by "3 successful runs" alone. It must also fail if a SKU has pathological concentration, for example `primary_share > 0.70` or `rejected_share == 0` on a non-trivial corpus, unless explicitly waived by operator.

2. Ensure SKU atoms exist before product-quality smoke.

The minimum immediate correction is to generate or materialize SKU atoms for `10533814` and `893327503` through an approved existing path, then rerun smoke. If that path requires LLM, it needs explicit operator approval. If no sanctioned non-LLM atom path exists, escalate before coding.

3. Harden profile derive for 2841 before Phase 2 readiness.

The current profile is too sparse. Candidate improvements should come through derive/profile workflow, not matcher logic:

- promote strong query requirements such as volume, thermal/heating, compartments, color/transparency, set/quantity, school/kids/work use cases into constraints/guards where evidence supports them;
- consider whether `ланч` and `бокс` should be treated as weaker aliases than `ланчбокс` for scoring, not just compatibility;
- add negative/related handling for neighboring products only if evidence supports real product-type conflicts.

4. Calibrate bucket behavior category-locally after atoms/profile evidence is improved.

Do not tune global matcher thresholds first. Re-run 812 sanity and 2841 smoke after any profile/derive change. If 2841 remains over-primary with atoms and stronger guards, then evaluate category-profile `bucket_cutoffs` or weights as a profile-versioned change.

5. Keep Step 9B exact alias compatibility behavior.

The exact conflict is gone and should stay gone. The issue is insufficient downstream discrimination, not the existence of alias compatibility.

## 8. Gate decision

- Runtime smoke: passed.
- Product-quality smoke: failed.
- Phase 2 readiness: blocked until quality fix or explicit downgrade of Phase 1 goal.

Step 9 should be treated as technically closed but quality-blocked. Phase 1 Step 10 report may document this as `fix derive` / `block Phase 2`, unless the operator explicitly downgrades Phase 1 to runtime portability only.
