# Phase 0 Retro — Backend Unification

> Status: Phase 0 closed on 2026-04-24.

## What Changed

- `SeoCategoryProfile` is now the runtime source of category rules for active `matcher_v2`.
- Category 812 has an active profile: `profile_id=1`, `version=v1.812.skeleton.243953b2`, `schema_version=category_profile_v1`, `self_check.status=passed`.
- `seo_category_profile_derive_runs` exists for derive/activation observability.
- `atoms/v1/guards.py` is profile-driven.
- `query_meaning_matcher/matcher.py` is a literal-free facade; legacy code is isolated under `query_meaning_matcher/_legacy/`.
- `matcher_v2` records `category_profile_version` and `category_profile_active` in run metrics.
- `matcher_v2` no longer silently falls back to legacy behavior when a profile is missing.

## What Passed

- Step 1 baseline accuracy: `0.1678`.
- Step 10 current accuracy: `0.2349`.
- Drift vs Step 1: `+0.0671`.
- Minimum acceptable accuracy: `0.1378`.
- Step 10 verdict: `pass`.
- `del category_profile`: `0`.
- Active matcher literals: `0`.
- Fresh Step 10 matcher run ids: `63`, `64`, `65`, `66`, `67`, `68`, `69`, `70`.
- Step 10 eval run id: `75`.
- Phase 0 suite: `75 passed, 1 skipped`.
- Targeted matcher/eval suite: `20 passed`.

Important caveat: eval verdict remains `preview_only` by product thresholds. Phase 0 proves regression safety versus the baseline, not production-quality matching.

## Known Issue

- Optional full SEO suite still fails on unrelated retention coverage: `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs`.
- This was explicitly not fixed in Phase 0 Step 10/11.

## Artifact Paths

- Step 1 baseline: `tests/seo/phase0/baselines/812_pre_phase0/`
- Step 8 activation: `tests/seo/phase0/activation_reports/812_step8/`
- Step 9 wiring: `tests/seo/phase0/activation_reports/812_step9/`
- Step 10 acceptance: `tests/seo/phase0/activation_reports/812_step10/`

## Step Commits

- Step 1: `4d3b02a` — baseline snapshot
- Step 2: `e8a39a2` — global vocabulary
- Step 3: `0b6241a` — derive foundation, validator, snapshot, CLI, migration
- Step 4: `740f413` — runtime wrapper and rules helpers
- Step 5: `8ec4946` — profile-driven guards
- Step 6: `0bc5a37` — profile-driven query matcher and legacy isolation
- Step 7: `59fee82` — admin API and CLI/profile activation tooling
- Step 8: `e1644c4` — active 812 profile
- Step 9: `f4aa78a` — matcher_v2 profile wiring
- Step 10: `b299422` — 812 regression gate

## Phase 1 Next

Phase 1 should validate the profile-driven backend on a second category. It should start from the completed Phase 0 state, ingest one enriched CSV, derive and activate a profile, run `matcher_v2` for at least three SKU, and record a qualitative category report. Do not add category literals to Python code and do not use CSV orders/conversion in scoring.
