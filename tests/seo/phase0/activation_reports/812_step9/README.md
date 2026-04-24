# Phase 0 Step 9 — matcher_v2 profile wiring (category 812)

This report captures the first runtime regression after `matcher_v2` was wired
to the active `CategoryProfile`.

Summary:
- Active profile before run: `id=1`, `version=v1.812.skeleton.243953b2`
- `matcher_v2` runs created for the 8 labeled SKU (`run_id` 22..29)
- Every new run recorded `category_profile_version=v1.812.skeleton.243953b2`
- Step 9 eval accuracy: `0.2349`
- Step 1 baseline accuracy: `0.1678`
- Step 8 informative snapshot: `0.2349`

Interpretation:
- No negative regression versus the Step 1 baseline (`0.2349 > 0.1678`)
- No drift versus the Step 8 informative snapshot (`0.2349 -> 0.2349`)
- Bucket distribution shifted to a profile-driven runtime, but the resulting
  accuracy remains above the minimum acceptable floor (`0.1378`)
- `matcher_v2` is now profile-wired; Step 10 can use these artifacts as the
  acceptance gate input rather than as a pre-wiring informative snapshot

