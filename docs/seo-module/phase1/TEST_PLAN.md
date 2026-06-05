# Phase 1 — Test Plan

> Статус: **DRAFT**.  
> Scope: validation checks for Phase 1 only. Do not run Phase 1 from this document.

---

## 1. TL;DR

Phase 1 does not require strict eval labels for category B unless they already exist. It validates:

- generic derive dry-run gate;
- profile self-check;
- no active-runtime category literals;
- no orders/conversion scoring;
- matcher_v2 smoke runs for at least 3 SKU;
- qualitative operator review.

Known unrelated failure remains out of scope:

- `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs`.

---

## 2. Phase 0 sanity tests

Run targeted sanity tests:

```powershell
pytest -x tests/seo/phase0/
pytest -x tests/seo/test_matcher_v2_no_category_literals.py
pytest -x tests/seo/test_seo_eval_harness.py
pytest -x tests/seo/test_seo_compare_read_only.py
```

Optional full suite:

```powershell
pytest -x tests/seo/
```

If full suite stops at `tests/seo/test_matcher_retention.py::test_keeps_referenced_runs`, record it as known unrelated. Do not fix it in Phase 1.

---

## 3. Generic derive gate

Required dry-run check:

```powershell
python scripts/derive_category_profile.py --project <project_id> --category <category_id> --dry-run --out tests/seo/phase1/category_<category_id>/derive_dry_run.json
```

Pass conditions:

- no skeleton-only / 812-only / `NotImplementedError`;
- payload `schema_version == "category_profile_v1"`;
- `self_check.status == "passed"`;
- `subject.primary` and related subjects describe category B, not 812.

Fail handling:

- Phase 1 STOP;
- do not persist;
- do not activate;
- do not patch Python under category B;
- open separate generic derive heuristic task.

---

## 4. Anti-literal checks

Before choosing category B, keep Phase 0 active-runtime check:

```powershell
rg -n "термокруж|круж|рюкзак|сумка|тарел|пивн|кофемаш" src/app/services/seo --glob "*.py"
```

After profile dry-run for category B, build a forbidden literal set from the generated/expected profile:

- `subject.primary`;
- all `subject.primary_aliases`;
- every `related_but_different.subject`;
- every `related_but_different.aliases[]`.

Then grep active Python runtime:

```powershell
rg -n "<literal1>|<literal2>|..." src/app/services/seo --glob "*.py"
```

Allowed locations for category literals:

- `config/seo/category_profiles/**`;
- `tests/**`;
- `docs/**`;
- reports/artifacts under `tests/seo/phase1/**`;
- `_legacy` code paths explicitly isolated from active runtime.

Stop condition:

- any category B literal appears in active Python runtime outside allowed locations.

---

## 5. No orders/conversion scoring

Check:

```powershell
rg -n "orders|conversion|Заказали товаров|Конверсия" src/app/services/seo src/app/routers tests/seo --glob "*.py"
```

Pass condition:

- no use in matcher scoring, derive scoring, or label generation.

Allowed context:

- CSV import diagnostics;
- corpus/reporting metadata;
- documentation explaining why these fields are not scoring inputs.

---

## 6. Import/bootstrap artifact checks

Required artifacts after import/bootstrap:

- `tests/seo/phase1/category_<category_id>/query_counts_before_after.json`;
- `tests/seo/phase1/category_<category_id>/import_result.json`;
- `tests/seo/phase1/category_<category_id>/bootstrap_run.json`;
- `tests/seo/phase1/category_<category_id>/bootstrap_status_final.json`;
- `tests/seo/phase1/category_<category_id>/corpus_health.json`.

Pass conditions:

- query count increases or matches expected existing corpus path;
- import diagnostics are present;
- bootstrap final status is ready/succeeded;
- `SeoCategoryMeaningAxes` exists and has non-empty `product_type_axes`.

Rules:

- no `force_refresh=true` without operator approval;
- polling timeout must be explicitly set before running.

---

## 7. Profile self-check validation

Required checks:

- active/inactive profile payload has `schema_version == "category_profile_v1"`;
- `self_check.status == "passed"`;
- hard conflicts cover `related_but_different`;
- bucket cutoffs are monotonic;
- profile subject semantics are category B-specific;
- profile snapshot exists at `config/seo/category_profiles/<project_id>/<category_id>/<profile_version>.json` if profile B is activated, unless operator explicitly waives committed snapshot.

---

## 8. Matcher_v2 smoke checks

For at least 3 SKU:

- matcher run succeeds;
- result rows are non-empty;
- `SeoMatcherRun.metrics.category_profile_active == true`;
- `SeoMatcherRun.metrics.category_profile_version` equals active category B profile version;
- bucket counts are recorded;
- top `primary` / `secondary` examples are included in `matcher_runs_summary.json`;
- rejected examples have explainable reasons.

Do not require production-quality thresholds.

---

## 9. Strict eval policy

Strict eval is optional and only allowed if labels already exist.

Check label coverage first:

```text
GET /api/v1/projects/{project_id}/seo/eval/labels/stats?category_id=<B>
```

If labels do not exist:

- do not create labels in Phase 1;
- do not require eval accuracy;
- rely on qualitative operator review.

If labels exist:

- run eval explicitly with `nm_ids` or `matcher_run_ids`;
- record metrics as supplemental evidence, not as a production-quality claim.

---

## 10. Qualitative operator review

For each of at least 3 SKU, record:

- top primary queries;
- useful secondary queries;
- broad bucket sanity;
- notable rejected queries and reasons;
- whether any category leakage is visible;
- whether buckets are meaningful enough for Phase 1.

Final qualitative verdict:

- `proceed`;
- `fix derive`;
- `block Phase 2`.

