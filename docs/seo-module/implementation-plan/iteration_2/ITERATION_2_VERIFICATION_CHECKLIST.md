# Iteration 2 — Verification Checklist

Each item below is a concrete way to verify the corresponding piece of Iteration 2
P0 against the current codebase. Steps are written so they can be run in the
existing dev/staging environment without any rewrite or broadening of scope.

Assumed env variables unless stated otherwise:

```
export PROJECT_ID=1
export CATEGORY_ID=812
export NM_ID=<any SKU with a fresh SeoSkuMeaningAnnotation for category 812>
```

Database URL, API host, and auth tokens follow the usual dev conventions.

---

## 0. Apply the additive migration

```bash
alembic upgrade head
```

Expected: the revision
`20260424_seo_iter2_category_profile_eval_promotion` applies cleanly and
subsequent `alembic current` reports its id. No existing row types change.

---

## 1. Category profile active for 812

1. Seed the 812 profile (idempotent):

   ```bash
   python scripts/seed_seo_category_profile_812.py --project-id "$PROJECT_ID"
   ```

2. Run the active-profile query via the loader:

   ```python
   from app.db import SessionLocal
   from app.services.seo.category_profile import load_active_profile
   with SessionLocal() as s:
       p = load_active_profile(s, project_id=1, category_id=812)
       print(p.version, len(p.term_groups), p.source_note)
   ```

   Expected: a non-null profile with `version >= 1`, `is_active=True`, and
   `term_groups` covering `expressive`, `audience`, `material_constraints`.

3. Run a candidate matcher and confirm the run persists the version:

   ```bash
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/query-sets/candidate/project" \
     -H "content-type: application/json" \
     -d '{"category_id": 812, "nm_id": '"$NM_ID"'}'
   ```

   Then:

   ```sql
   select category_profile_version from seo_matcher_runs
     where project_id=1 and category_id=812 and nm_id=:nm_id
     order by id desc limit 1;
   ```

   Expected: the column equals the profile version reported by the loader.

4. Matcher_v2 CI guard:

   ```bash
   pytest tests/seo/test_matcher_v2_no_category_literals.py -q
   ```

   Expected: green. (This is the guard that prevents new category literals from
   appearing in `matcher_v2/*`.)

---

## 2. Eval for 812

1. Import the seed labels once (idempotent):

   ```bash
   python scripts/import_seo_eval_labels_812.py --project-id "$PROJECT_ID"
   ```

   Expected: 191 `seo_eval_labels` rows for `category_id=812`, `label_set_id=1`.

2. Trigger eval:

   ```bash
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/eval/matcher/run" \
     -H "content-type: application/json" \
     -d '{"category_id": 812, "label_set_id": 1}'
   ```

   Expected 200 response with `metrics.accuracy`, `metrics.bad_primary_rate`,
   `metrics.hard_conflict_primary_count`, `verdict` and a persisted
   `seo_eval_runs` row.

3. Inspect history:

   ```bash
   curl -s "$API/api/v1/projects/$PROJECT_ID/seo/eval/runs?category_id=812"
   ```

4. Label coverage stats:

   ```bash
   curl -s "$API/api/v1/projects/$PROJECT_ID/seo/eval/labels/stats?category_id=812"
   ```

---

## 3. `eligibility_tier` writes only through eval

1. Run the test:

   ```bash
   pytest tests/seo/test_seo_eval_harness.py -q
   ```

   The suite contains:
   - A static AST walk over `src/app/` that asserts only
     `app.services.seo.eval.harness` assigns to
     `SeoCategoryMatchingReadiness.eligibility_tier`.
   - A runtime check that the single-writer helper refuses an unauthorized
     caller.

2. Manual DB sanity:

   ```sql
   select eligibility_tier, last_evaluated_at from seo_category_matching_readiness
     where project_id=1 and category_id=812;
   ```

   Expected: after a successful eval run, `eligibility_tier` reflects the
   verdict (`evaluated`, `approved`, or `preview_only`).

---

## 4. Candidate selection uses projected query set, not trace mutation

1. Project a fresh candidate query set:

   ```bash
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/query-sets/candidate/project" \
     -H "content-type: application/json" \
     -d '{"category_id": 812, "nm_id": '"$NM_ID"'}'
   ```

   Expected response: `{"query_set_id": ..., "status": "candidate",
   "approval_state": "draft", ...}`.

2. Confirm the candidate row is separate from the legacy row:

   ```sql
   select id, status, approval_state, trust_state, category_profile_version
     from seo_sku_query_sets
     where project_id=1 and category_id=812 and nm_id=:nm_id
     order by id desc;
   ```

   Expected: at most one `status='candidate'` row per `(project, category, nm)`,
   coexisting with any legacy `draft/confirmed` row.

3. Confirm the matcher trace is unchanged:

   ```sql
   select count(*) from information_schema.columns
     where table_name='seo_matcher_results'
       and column_name in ('approval_state','selection_state','trust_state');
   ```

   Expected: `0`. `SeoMatcherResult` must not own any operator-editable
   column.

4. Run transition tests:

   ```bash
   pytest tests/seo/test_seo_query_set_approval_state.py -q
   ```

---

## 5. Generation promotion gates

1. Test coverage:

   ```bash
   pytest tests/seo/test_seo_generation_promote.py -q
   ```

2. Manual happy path:

   ```bash
   # 1. Create a preview generation (existing flow)
   curl -s -X POST "$API/api/v1/projects/$PROJECT_ID/seo/generation/run" ...

   # 2. Record a human review accept
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/generation/content/$CV/human-review" \
     -H "content-type: application/json" \
     -d '{"reviewer": "qa-bot", "verdict": "accept"}'

   # 3. Promote preview -> candidate (requires evaluated/approved tier)
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/generation/content/$CV/promote" \
     -H "content-type: application/json" \
     -d '{"target_kind": "candidate"}'
   ```

   Expected: without an `evaluated`+ tier or without an accepted human review,
   the promote endpoint returns `409` with a reason. With both satisfied the
   content flips to `content_kind='candidate'`.

3. Manual refusal:

   ```bash
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/generation/content/$CV/promote" \
     -H "content-type: application/json" \
     -d '{"target_kind": "published"}'
   ```

   Expected: `409` with reason `production_generation_off`. Iteration 2 never
   lets anything become `published`.

---

## 6. Compare layer is read-only

1. Static check:

   ```bash
   pytest tests/seo/test_seo_compare_read_only.py -q
   ```

   This test walks `src/app/routers/seo_compare.py` and
   `src/app/services/seo/compare.py` with AST and asserts:
   - No import of mutating service functions (e.g. `run_matcher_v2`,
     `promote_content_version`, `update_eligibility_tier`).
   - No attribute-style writes to `SeoMatcherRun`, `SeoMatcherResult`,
     `SeoContentVersion`, or `SeoSkuQuerySet` fields (except for the explicit
     `SeoCompareVerdict` append).

2. Smoke the GETs:

   ```bash
   curl -s "$API/api/v1/projects/$PROJECT_ID/seo/compare/matcher?category_id=812&nm_id=$NM_ID" | jq '.diff.bucket_change_ratio'
   curl -s "$API/api/v1/projects/$PROJECT_ID/seo/compare/generation?category_id=812&nm_id=$NM_ID" | jq '.candidate'
   ```

3. Verdict capture writes only the append-only table:

   ```bash
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/compare/matcher/verdict" \
     -H "content-type: application/json" \
     -d '{"subject_id": '"$MATCHER_RUN_ID"', "verdict": "accept"}'
   ```

   Then:

   ```sql
   select count(*) from seo_compare_verdicts;
   ```

   should increase by one; `seo_matcher_runs` / `seo_matcher_results` row counts
   stay identical.

---

## 7. Production generation stays OFF

1. Confirm the feature flag in the current env:

   ```bash
   python -c "from app.config import settings; print(settings.SEO_GENERATION_PREVIEW_ENABLED)"
   ```

   Expected in production: `False`. In dev/staging it may be `True`, but only
   for category 812 operationally.

2. Confirm the lifecycle refusal:

   ```bash
   curl -s -X POST \
     "$API/api/v1/projects/$PROJECT_ID/seo/generation/content/$CV/promote" \
     -H "content-type: application/json" \
     -d '{"target_kind": "published"}'
   ```

   Expected: `409`. No `published` row exists:

   ```sql
   select count(*) from seo_content_versions where content_kind='published';
   ```

   Expected: `0`.

3. Confirm there is no publish endpoint:

   ```bash
   grep -R "content_api/wb" src/ || echo "no WB publish path — ok"
   ```

---

## 8. Retention cleanup rule

1. Test coverage:

   ```bash
   pytest tests/seo/test_matcher_retention.py -q
   ```

2. Dry-run in dev:

   ```bash
   python scripts/run_seo_matcher_retention.py --dry-run
   ```

   Expected output: a count of runs that would be retained / deleted, and a
   confirmation that no run referenced by a non-preview
   `SeoSkuQuerySet`/`SeoContentVersion` is in the delete set.

3. Live call:

   ```bash
   curl -s -X POST "$API/api/v1/seo/matcher/retention/cleanup?dry_run=false&keep_newest=20&keep_days=30"
   ```

4. Invariants to spot-check afterwards:

   ```sql
   -- For any sku, newest 20 runs stay
   select count(*) from seo_matcher_runs
    where project_id=1 and category_id=812 and nm_id=:nm_id;

   -- Any run referenced by a non-preview content version still exists
   select r.id from seo_matcher_runs r
     join seo_sku_query_sets q on q.matcher_run_id = r.id
     join seo_content_versions c on c.query_set_id = q.id
    where c.content_kind <> 'preview';
   ```

---

## 9. D1 parity artifact

1. Run the parity script against a dev DB:

   ```bash
   python scripts/parity_matcher_v2_812.py \
     --project-id 1 --category-id 812 \
     --out docs/seo-module/implementation-plan/iteration_2/PARITY_SAMPLE_812.md
   ```

   Expected: the script exits non-zero if any SKU exceeds 10% bucket changes or
   produces a `primary <-> rejected` flip without an explicit `--allow-flip`
   override. The artifact is written either way so the operator can review.

2. Commit the refreshed `PARITY_SAMPLE_812.md` before closing Iteration 2.

---

## 10. Global sanity

Run the scoped test set:

```bash
pytest tests/seo -q
```

Expected: green. This covers the new Iteration 2 guards plus all Iteration 1
tests, confirming the current path still works.
