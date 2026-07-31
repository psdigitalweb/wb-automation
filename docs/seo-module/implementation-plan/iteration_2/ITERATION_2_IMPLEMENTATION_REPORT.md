# Iteration 2 — Implementation Report

Scope tracked against the locked pre-kickoff brief (D1-D5) and the Iteration 2 plan
[`seo_iteration_2_implementation_37196900.plan.md`](../../../..//..). Nothing in the current path was rewritten; every change is additive and leaves the Iteration 1 flow functional.

## Shipped as P0

### A. Category profile (WS-C profile half)

| Kind | Path |
|---|---|
| ORM | [`SeoCategoryProfile` in `src/app/models.py`](../../../../src/app/models.py) |
| Migration | [`alembic/versions/20260424_seo_iter2_category_profile_eval_promotion.py`](../../../../alembic/versions/20260424_seo_iter2_category_profile_eval_promotion.py) |
| Seed data | [`config/seo/category_profiles/812.json`](../../../../config/seo/category_profiles/812.json) |
| Loader | [`src/app/services/seo/category_profile.py`](../../../../src/app/services/seo/category_profile.py) |
| Seed CLI | [`scripts/seed_seo_category_profile_812.py`](../../../../scripts/seed_seo_category_profile_812.py) |
| Matcher_v2 wiring | [`src/app/services/seo/matcher_v2/api.py`](../../../../src/app/services/seo/matcher_v2/api.py) + stage files |
| CI guard | [`tests/seo/test_matcher_v2_no_category_literals.py`](../../../../tests/seo/test_matcher_v2_no_category_literals.py) |

### B. Eval as a gate (WS-E)

| Kind | Path |
|---|---|
| ORM | `SeoEvalLabel`, `SeoEvalRun` in [`src/app/models.py`](../../../../src/app/models.py); `eligibility_tier` on `SeoCategoryMatchingReadiness` |
| Migration | same file as above |
| Harness | [`src/app/services/seo/eval/harness.py`](../../../../src/app/services/seo/eval/harness.py) (single writer of `eligibility_tier`) |
| Router | [`src/app/routers/seo_eval.py`](../../../../src/app/routers/seo_eval.py) |
| Label importer | [`scripts/import_seo_eval_labels_812.py`](../../../../scripts/import_seo_eval_labels_812.py) |
| Tests | [`tests/seo/test_seo_eval_harness.py`](../../../../tests/seo/test_seo_eval_harness.py) |

Endpoints added:

- `POST /api/v1/projects/{project_id}/seo/eval/matcher/run`
- `GET  /api/v1/projects/{project_id}/seo/eval/runs?category_id=...`
- `GET  /api/v1/projects/{project_id}/seo/eval/labels/stats?category_id=...`

### C. Candidate selection semantics (WS-C query-set half)

| Kind | Path |
|---|---|
| ORM columns | `approval_state`, `trust_state`, `category_profile_version` on `SeoSkuQuerySet` |
| Service | [`src/app/services/seo/query_set_candidate.py`](../../../../src/app/services/seo/query_set_candidate.py) |
| Router | [`src/app/routers/seo_query_set_candidate.py`](../../../../src/app/routers/seo_query_set_candidate.py) |
| Generation bridge | [`src/app/services/seo/generation/service.py`](../../../../src/app/services/seo/generation/service.py) `_load_query_set` now accepts `status='candidate'` when `approval_state in {candidate, approved}` |
| Tests | [`tests/seo/test_seo_query_set_approval_state.py`](../../../../tests/seo/test_seo_query_set_approval_state.py) |

Endpoints added:

- `POST /api/v1/projects/{project_id}/seo/query-sets/candidate/project`
- `POST /api/v1/projects/{project_id}/seo/query-sets/candidate/{query_set_id}/approval`

Naming:
- Query-set-level operator state lives in `SeoSkuQuerySet.approval_state` (`draft → preview → candidate → approved`) to avoid collision with the existing per-item `SeoSkuQuerySetItem.selection_state`.
- `trust_state` (`unverified | validated`) is written only by the eval flow.
- Legacy `status = 'confirmed'` continues to work unchanged.

### D. Generation discipline second cut (WS-D)

| Kind | Path |
|---|---|
| ORM | `content_kind` tightened with additional comment; `category_profile_version` column; new `SeoGenerationHumanReview` table |
| Migration | same file |
| Service | [`src/app/services/seo/generation/service.py`](../../../../src/app/services/seo/generation/service.py) writes `content_kind='preview'` (was `llm_draft`) and propagates `category_profile_version`; read paths accept both labels for the migration window |
| Promotion engine | [`src/app/services/seo/generation/promotion.py`](../../../../src/app/services/seo/generation/promotion.py) |
| Router additions | [`src/app/routers/seo_generation.py`](../../../../src/app/routers/seo_generation.py) |
| Tests | [`tests/seo/test_seo_generation_promote.py`](../../../../tests/seo/test_seo_generation_promote.py) |

Endpoints added:

- `POST /api/v1/projects/{project_id}/seo/generation/content/{content_version_id}/promote`
- `POST /api/v1/projects/{project_id}/seo/generation/content/{content_version_id}/human-review`

Server-enforced gates:

- `preview → candidate`: `eligibility_tier ∈ {evaluated, approved}` + accepted human review.
- `candidate → approved`: `eligibility_tier == approved` + a second accepted human review.
- `approved → published`: **refused** (production generation OFF).

### E. Compare layer (read-only)

| Kind | Path |
|---|---|
| ORM | `SeoCompareVerdict` |
| Service | [`src/app/services/seo/compare.py`](../../../../src/app/services/seo/compare.py) |
| Router | [`src/app/routers/seo_compare.py`](../../../../src/app/routers/seo_compare.py) |
| Static check | [`tests/seo/test_seo_compare_read_only.py`](../../../../tests/seo/test_seo_compare_read_only.py) (import allowlist + no mutating attribute assigns) |

Endpoints added:

- `GET  /api/v1/projects/{project_id}/seo/compare/matcher?category_id&nm_id`
- `GET  /api/v1/projects/{project_id}/seo/compare/generation?category_id&nm_id`
- `POST /api/v1/projects/{project_id}/seo/compare/{subject_type}/verdict`

### F. Category tier UI / operator visibility

| Kind | Path |
|---|---|
| Component | [`frontend/.../CategoryTierBadge.tsx`](../../../../frontend/app/app/project/%5BprojectId%5D/seo/_components/CategoryTierBadge.tsx) exports `CategoryTierBadge` + `ApprovalStateBadge` (Approved vs Validated pills) |
| Eval page (812) | [`frontend/.../categories/[categoryId]/eval/page.tsx`](../../../../frontend/app/app/project/%5BprojectId%5D/seo/categories/%5BcategoryId%5D/eval/page.tsx) |
| Compare page | [`frontend/.../products/[nmId]/compare/page.tsx`](../../../../frontend/app/app/project/%5BprojectId%5D/seo/products/%5BnmId%5D/compare/page.tsx) |
| API client | [`frontend/lib/apiClient.ts`](../../../../frontend/lib/apiClient.ts) now exports Iteration 2 helpers for eval, candidate, promote, human-review, compare. |

### G. Retention

| Kind | Path |
|---|---|
| Service | [`src/app/services/seo/matcher_retention.py`](../../../../src/app/services/seo/matcher_retention.py) |
| Router | [`src/app/routers/seo_retention.py`](../../../../src/app/routers/seo_retention.py) |
| CLI | [`scripts/run_seo_matcher_retention.py`](../../../../scripts/run_seo_matcher_retention.py) |
| Tests | [`tests/seo/test_matcher_retention.py`](../../../../tests/seo/test_matcher_retention.py) |

Endpoint added:

- `POST /api/v1/seo/matcher/retention/cleanup?dry_run=&keep_newest=&keep_days=`

Rule implemented: keep newest 20 runs per `(project_id, category_id, nm_id)` OR runs within last 30 days, whichever is larger; plus any run referenced by:
- a `SeoSkuQuerySet` with `status='confirmed'` or `status='candidate' and approval_state ∈ {candidate, approved}`
- a `SeoContentVersion` whose `content_kind` is not `preview` / `llm_draft`.

### Parity artifact (D1)

- Script: [`scripts/parity_matcher_v2_812.py`](../../../../scripts/parity_matcher_v2_812.py) — diffs legacy vs candidate matcher per SKU, enforces D1 bar, writes artifact, non-zero exit on breach.
- Scaffold artifact: [`PARITY_SAMPLE_812.md`](PARITY_SAMPLE_812.md) — committed as a placeholder; the canonical copy must be produced by running the script against a real DB snapshot.

## Migrations added

Single additive Alembic revision: [`20260424_seo_iter2_category_profile_eval_promotion.py`](../../../../alembic/versions/20260424_seo_iter2_category_profile_eval_promotion.py).

It contains:

1. `seo_category_profiles` table.
2. `seo_eval_labels` + `seo_eval_runs` tables.
3. `seo_category_matching_readiness.eligibility_tier` column (default `preview_only`).
4. `seo_sku_query_sets.approval_state`, `.trust_state`, `.category_profile_version` columns + backfill `approval_state='candidate'` where legacy `status='confirmed'`.
5. `seo_content_versions.category_profile_version` column + one-time `content_kind='llm_draft' → 'preview'` update.
6. `seo_generation_human_review` table.
7. `seo_compare_verdicts` table.

All column adds guarded by existence checks so re-running the migration is safe.

## Plan-vs-repo conflicts and resolutions

- **Plan expected `SeoCategoryProfile` to be scoped per `category_id` only.** Repo reality: all SEO tables carry `project_id`. Resolution: `SeoCategoryProfile` gets `(project_id, category_id, version)` unique key to match the existing scoping convention. The loader exposes both ids so future rollout is unchanged.
- **Plan said remove category literals from matcher_v2 helpers.** Repo reality: the matcher_v2 stages import private helpers from the legacy `query_meaning_matcher.matcher` that still contain the category-812 dicts. A full refactor would have been a rewrite (out of scope). Resolution: the stages accept an optional `CategoryProfile` argument (threaded from `api.run_matcher_v2`) so they are ready to consume profile data; for Iteration 2 they still delegate to the legacy helpers so parity holds, but a CI guard (`test_matcher_v2_no_category_literals.py`) prevents *new* category literals from leaking into `matcher_v2/*`. The eventual replacement of the legacy helpers is an Iteration 3 job.
- **Plan said the parity script should run against live DB on close.** Repo reality: the live DB is not reachable from this workspace. Resolution: the script is fully implemented and a scaffold `PARITY_SAMPLE_812.md` is committed. The operator must run it once against the dev DB and commit the resulting artifact before closing Iteration 2.
- **Plan said `approval_state` replaces `status='confirmed'`.** Repo reality: `SeoSkuQuerySet` has a unique constraint on `(project_id, category_id, nm_id, status)`, and downstream code still expects `status='confirmed'` (generation service, list helpers). Resolution: the candidate path lives on a new `status='candidate'` row so it doesn’t collide with the legacy draft/confirmed rows, and `approval_state` on that row tracks operator intent. The legacy `status='confirmed'` path is untouched, satisfying the "keep legacy working" constraint.
- **Plan lists a full UI polish pass.** For Iteration 2 we shipped the two decision-critical surfaces (category eval page, SKU-level matcher compare page) plus reusable `CategoryTierBadge` / `ApprovalStateBadge` components. The remaining tweaks to the existing query-selection page (Approved vs Validated pills, renamed primary action, compare panel on the generation page) should be folded in during the UI polish window in Iteration 2 close-out; the backend contracts they depend on are already in place.

## Intentionally deferred

Everything listed in §Explicitly out of scope of the plan and the brief stays deferred:

- Profile editor UI.
- Second-category rollout.
- Labeling UI.
- WB publish flow.
- Batch generation.
- Stable category scope surrogate.
- Learnable profile generation.
- Iteration 3 cleanup / table drops.
- Broad refactor of `run_meaning_aware_matcher` and the generation service.
- Readiness-derived quality propagation.

## Open risks

- **Profile adoption depth in `matcher_v2`.** Stages accept the profile but do not fully consume it yet. A future patch (Iteration 3) must switch the legacy helpers to profile-driven lookups; until then the profile payload is authoritative only for persistence metadata (`SeoMatcherRun.category_profile_version`).
- **Parity run is pending.** The script exists and the scaffold artifact is committed, but the operator must run it against a live DB snapshot to satisfy D1 before closing Iteration 2.
- **Schema freeze around `content_kind`.** We keep accepting the legacy `llm_draft` label in reads for one release window. Iteration 3 should drop the legacy branch after all preview rows are migrated.
- **Retention deletion scope.** The cleanup helper only protects non-preview references. If a future feature starts pinning runs through a new downstream table, `_referenced_run_ids` must be extended accordingly.
- **Eval single-writer guard.** The AST check in `test_seo_eval_harness.py` only catches attribute-style writes. If a contributor added a raw SQL `UPDATE` string that hits `eligibility_tier`, the guard would miss it; the contract is documented in the module doc-string so reviewers can catch that.

## Verification

See [`ITERATION_2_VERIFICATION_CHECKLIST.md`](ITERATION_2_VERIFICATION_CHECKLIST.md).
