# Phase 1Q - Product Quality Recovery Plan

> Status: recovery plan between Phase 1 and Phase 2.  
> Date: 2026-04-25.  
> Scope: product-quality repair after Phase 1 backend portability proof.  
> Rule: Phase 2 must not start as "scale the pipeline" until Phase 1Q gates pass or the operator explicitly downgrades product-quality goals.

---

## 1. CEO Summary

Phase 1 proved that the backend can onboard and activate a second category. It did not prove that the product produces useful SEO decisions.

The failure is product-level: the system can run, but it may still produce dry SKU meaning, miss buyer perception from reviews, skip AI vision, and over-accept too many queries as `primary`.

Phase 1Q is the recovery phase. Its goal is to make the pipeline answer the business question:

> For this specific SKU, which existing demand signals are meaningfully relevant, and why?

Phase 1Q must prove this on category `812` and category `2841` before Phase 2 onboarding.

---

## 2. Why Phase 1Q Exists

Phase 1 found two hard product-quality risks:

1. **Matcher quality failure on 2841**
   - Two of three 2841 SKU produced pathological distributions: `915 primary / 24 secondary / 2 broad / 0 rejected`.
   - The direct trigger was missing SKU atoms plus a permissive category profile.
   - Runtime traces existed, but product selectivity failed.

2. **SKU meaning is too dry**
   - For SKU `535441190`, current analysis reads mostly seller card data.
   - SKU reviews are not entering the current evidence pack for that SKU.
   - Category expressive prior is empty in current SKU meaning input.
   - AI vision status is `error`, so visual evidence is absent.
   - Legacy baseline preserved richer style/emotional context than the current recompute.

This means Phase 1 should be reclassified as:

`backend portability passed; product-quality pending/failed`

---

## 3. Non-Goals

Phase 1Q does not:

- onboard 5-7 new categories;
- build production UI;
- export briefs;
- use orders/conversion for scoring or labels;
- introduce category-specific Python literals;
- rewrite matcher architecture;
- change `category_profile_v1` schema unless escalated;
- auto-activate profile changes;
- treat LLM output as production without trace/evidence.

---

## 4. Success Criteria

Phase 1Q is successful only if all of these are true:

1. SKU meaning uses buyer perception evidence where available.
2. Review-backed expressive signals are visible in traceable artifacts.
3. AI vision can produce ready visual atoms for at least one SKU with available images.
4. SKU atoms exist before product-quality matcher smoke.
5. Matcher smoke fails on pathological bucket distributions, not only on runtime errors.
6. Category `2841` no longer passes with "almost everything primary" for atom-covered SKU.
7. SKU `535441190` shows stable, evidence-backed style/emotional context.
8. Operator can see what evidence caused each major meaning: seller text, characteristics, reviews, category prior, or vision.

---

## 5. Step 1 - Reclassify Phase 1 Outcome

Goal: stop accidental Phase 2 scaling from a misleading "Phase 1 passed" interpretation.

Work:

- Update `CATEGORY_2841_REPORT.md` verdict from `proceed` to `backend portability passed; product-quality blocked`.
- Link `STEP_9D_2841_MATCHER_QUALITY_FAILURE.md`.
- Update `CONTEXT_PRIMER.md` current state.
- Mark Phase 2 as blocked by Phase 1Q.

Artifacts:

- updated `docs/seo-module/phase1/CATEGORY_2841_REPORT.md`;
- updated `docs/seo-module/CONTEXT_PRIMER.md`;
- short `PHASE_1Q_STATUS.md`.

Tests:

- docs-only path validation.

Exit:

- no document claims 2841 is production-proven.

---

## 6. Step 2 - SKU Evidence Audit

Goal: prove exactly why SKU reviews and category expressive allocations are not entering current SKU meaning.

Target SKU:

- `project_id=1`
- `category_id=812`
- `nm_id=535441190`

Work:

- Read `products`, `wb_feedback_snapshots`, `seo_sku_meaning_annotations`, `seo_meaning_atoms`.
- Run `build_sku_evidence_pack` read-only.
- Compare:
  - current evidence pack;
  - current annotation;
  - old baseline `tests/seo/phase0/baselines/812_pre_phase0/sku_atoms_535441190.json`;
  - cached prompt/response for all three annotation evidence hashes.
- Answer:
  - are SKU reviews missing from source tables or from reader logic?
  - why is `category_prior.expressive.vibes=[]`?
  - why is `product_projection.expressive.vibes=[]` despite expressive text in description?
  - which old signals were lost on recompute?

Artifacts:

- `tests/seo/phase1q/sku_535441190/evidence_audit.json`
- `tests/seo/phase1q/sku_535441190/evidence_diff_vs_baseline.json`
- `docs/seo-module/phase1/PHASE_1Q_EVIDENCE_AUDIT.md`

Tests:

- read-only DB checks;
- JSON artifact validation.

Exit:

- proven root cause for missing reviews/category expressive signals.

---

## 7. Step 3 - Review-Backed Expressive Intent Layer

Goal: add an explicit evidence-backed expressive layer instead of relying on general `SkuMeaningPayload`.

Work:

- Design a minimal `SeoExpressiveIntent` payload as an internal artifact, not a schema migration first:
  - `style_labels`
  - `vibe_labels`
  - `emotion_labels`
  - `occasion_labels`
  - `gift_positioning`
  - `negative_style_fit`
  - `evidence_spans`
  - `source_breakdown`
- Input sources:
  - product title;
  - product description;
  - product characteristics;
  - SKU reviews if available;
  - category expressive prior if available.
- Run read-only prompt experiment on `535441190`:
  - model A: current default;
  - model B: stronger model if approved;
  - no DB writes.
- The prompt must require evidence spans for every expressive label.

Artifacts:

- `outputs/seo_model_compare/expressive_prompt_experiment_535441190.json`
- `docs/seo-module/phase1/PHASE_1Q_EXPRESSIVE_PROMPT_REVIEW.md`

Tests:

- parser tests for evidence span shape;
- no hallucinated labels without evidence spans;
- deterministic fixture test using `535441190` extracted evidence.

Exit:

- `535441190` returns stable evidence-backed labels such as `милый`, `яркий`, `уют`, `позитив`, `радость`, and gift/occasion labels when supported by evidence.

---

## 8. Step 4 - Fix SKU Review Ingestion Into Meaning

Goal: make buyer perception available to SKU analysis.

Work:

- If reviews exist but are not fetched, fix `_fetch_sku_reviews`.
- If reviews do not exist for the SKU, add a clear diagnostic:
  - `reviews_available=false`;
  - `review_source_missing=true`;
  - not silent empty array.
- Ensure current SKU meaning prompt receives bounded review snippets when present.
- Add source trace so UI/operator can tell whether expressive labels came from reviews or seller copy.

Rules:

- Do not log PII.
- Do not send full unbounded reviews to LLM.
- Keep review limit and truncation explicit.

Artifacts:

- updated evidence audit for `535441190`;
- fixture with at least one SKU that has reviews;
- `review_source_status.json`.

Tests:

- unit test: reviews present in DB appear in evidence pack;
- unit test: missing reviews produce diagnostic, not silent success;
- regression: existing SKU meaning fallback still works.

Exit:

- SKU meaning input can use reviews when available and explains when not.

---

## 9. Step 5 - Fix Category Expressive Allocation Usage

Goal: ensure category-level buyer perception is available as prior, without overpowering SKU-specific evidence.

Work:

- Trace `build_category_meaning(...).expressive`.
- Verify whether `SeoCategoryMeaningAxes` contains expressive axes for 812 and 2841.
- Verify whether `expressive_llm` cache is read by current category meaning.
- If category expressive exists but returns empty, fix loader/selection logic.
- If no expressive exists, add a controlled build step or diagnostic.

Rules:

- Category prior is soft context, not SKU truth.
- SKU evidence wins over category prior.
- Category prior must not homogenize all SKU.

Artifacts:

- `tests/seo/phase1q/category_812/category_expressive_trace.json`
- `tests/seo/phase1q/category_2841/category_expressive_trace.json`

Tests:

- category expressive trace test;
- no orders/conversion involvement.

Exit:

- category expressive prior is either populated and traceable, or explicitly marked unavailable with a reason.

---

## 10. Step 6 - AI Vision Recovery

Goal: make vision reliable enough for product-quality smoke and stop confusing UI states.

Current issue:

- SKU `535441190` has `sku_vision` atom row with `status=error`.
- UI shows `Фото не учтены`, while annotation-level `quality_mode=full`.
- Vision is not contributing to "Что видно на фото".

Work:

- Audit `image_urls_from_evidence` for real product image URL extraction.
- Audit `extract_vision_sku_atoms` failure mode:
  - no image URLs;
  - provider error;
  - timeout;
  - invalid JSON;
  - empty atoms;
  - cache read/write mismatch.
- Add diagnostic payload for vision failures:
  - `vision_status`;
  - `vision_error_type`;
  - `image_urls_count`;
  - `provider_model`;
  - `prompt_version`;
  - `cache_hit`.
- Rerun vision for `535441190` in a sanctioned controlled path.
- Ensure visual atoms can include:
  - motif/design;
  - color;
  - packaging;
  - style archetypes;
  - supported/negative visual query intents.

Rules:

- Vision hypotheses stay soft.
- Vision must not infer material, volume, microwave, dishwasher, or thermos properties unless visible/textual.
- No silent `FULL QUALITY` if vision failed.

Artifacts:

- `tests/seo/phase1q/sku_535441190/vision_diagnostics.json`
- `tests/seo/phase1q/sku_535441190/vision_atoms.json`
- before/after UI summary snapshot JSON.

Tests:

- unit test: image URL extraction from product `pics`;
- parser test for vision response variants;
- failure test: provider error records diagnostic and does not mark vision ready;
- integration smoke on `535441190` if image URLs exist.

Exit:

- one controlled SKU with images has `sku_vision.status=ready`, or a documented external blocker explains why not.
- UI quality labels distinguish text quality from vision quality.

---

## 11. Step 7 - SKU Atom Coverage Gate

Goal: matcher product-quality smoke must not run with missing SKU atoms unless explicitly waived.

Work:

- Add preflight for matcher smoke:
  - active category profile exists;
  - SKU meaning annotation exists;
  - SKU atoms exist;
  - query atoms coverage is adequate;
  - vision status recorded.
- For 2841 SKU `10533814` and `893327503`, materialize sanctioned SKU atoms before rerun.
- If atom generation requires LLM, operator approval is required before calls.

Artifacts:

- `tests/seo/phase1q/category_2841/sku_atom_coverage.json`

Tests:

- preflight fails when SKU atoms are missing;
- preflight can be explicitly waived only with reason in artifact.

Exit:

- product-quality matcher smoke no longer silently skips atoms gate.

---

## 12. Step 8 - Matcher Quality Gate

Goal: block pathological "runtime passed, product failed" outcomes.

Work:

- Add product-quality smoke criteria:
  - fail if `primary_share > 0.70` on a non-trivial corpus unless operator waives;
  - fail if `rejected_share == 0` and corpus size is large;
  - require bucket distribution explanation per SKU;
  - require top examples for each bucket.
- Re-run 2841 smoke only after Step 7 passes.
- Keep 812 sanity run.

Artifacts:

- `tests/seo/phase1q/category_2841/matcher_quality_gate.json`
- `tests/seo/phase1q/category_2841/matcher_smoke_after_atoms.json`

Tests:

- quality-gate unit tests on synthetic distributions;
- no regression for existing runtime smoke.

Exit:

- 2841 smoke either passes product-quality gate or remains explicitly blocked.

---

## 13. Step 9 - Operator Review Pack

Goal: give the operator a practical review surface, not raw traces only.

Work:

- Produce per-SKU table:
  - meaning facts;
  - expressive labels;
  - review-backed labels;
  - vision labels;
  - bucket counts;
  - top primary/secondary/broad/rejected queries;
  - reasons and evidence source.
- Include `535441190` as known expressive regression case.
- Include 2841 smoke SKU as matcher quality case.

Artifacts:

- `outputs/seo_phase1q/operator_review_pack.xlsx`
- `docs/seo-module/phase1/PHASE_1Q_OPERATOR_REVIEW.md`

Tests:

- workbook renders;
- all referenced artifact paths exist.

Exit:

- operator can approve/block with evidence, not screenshots only.

---

## 14. Step 10 - Final Gate Decision

Goal: decide whether Phase 2 can start.

Possible outcomes:

- `proceed_to_phase2`: product-quality gates pass.
- `proceed_with_waiver`: operator accepts explicit limitations.
- `block_phase2`: recovery did not fix core quality.

Required final report:

- what was fixed;
- what remains risky;
- whether reviews are entering SKU meaning;
- whether category expressive prior is usable;
- whether AI vision works or remains blocked;
- whether matcher quality gate passes for 2841;
- whether `535441190` expressive regression is fixed.

Artifacts:

- `docs/seo-module/phase1/PHASE_1Q_FINAL_REPORT.md`
- updated `CONTEXT_PRIMER.md`
- updated `ROADMAP.md` if Phase 2 remains blocked.

---

## 15. Highest-Risk Decisions

1. If reviews are unavailable in source tables, Phase 1Q must not fake buyer perception.
2. If AI vision provider fails, UI must say vision unavailable and downgrade quality, not pretend full quality.
3. If 2841 remains over-primary after atoms, the issue is matcher/profile calibration, not only missing atoms.
4. If expressive-only prompt works, do not stuff all output into generic `SkuMeaningPayload`; introduce a clear internal `SeoExpressiveIntent` layer first.
5. If prompt/model changes improve one SKU but reduce traceability, do not promote them.

---

## 16. Recommended Chat Split

Use one implementation chat per major block:

1. `SEO Phase 1Q - Step 1-2 Evidence Audit`
2. `SEO Phase 1Q - Step 3-5 Expressive Reviews`
3. `SEO Phase 1Q - Step 6 AI Vision Recovery`
4. `SEO Phase 1Q - Step 7-8 Matcher Quality Gate`
5. `SEO Phase 1Q - Step 9-10 Operator Review And Final Gate`

Blocker patches inside a step can stay in the same chat.

