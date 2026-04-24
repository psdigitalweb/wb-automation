# 03. Workstreams And Scope

Audience: engineering lead / PM / CTO
Date: 2026-04-23

---

Six workstreams, each with a single owner and explicit parallelization. All workstreams target the candidate flow. None of them change the current flow in a breaking way during iteration 1.

---

## WS-A. Matcher Authority

**Goal:** make `run_matcher_v2` the only authority for bucket/score/explanation on the candidate path, with one decision trace row per run.

**Why it exists:** the audits established there is no canonical decision path today. Soft score is computed before hard gate, experiment code is on the runtime path, reasons are overwritten on every re-run.

**Included changes:**

- Move `experiments/meaning_atoms/v1.py` and `experiments/meaning_atoms/schemas.py` into `services/seo/atoms/v1/` with no code-level rewrite. Freeze the `experiments/` copies as historical.
- New `services/seo/matcher_v2/` package with a staged function: eligibility → bucket cap → soft score → demand ordering.
- New tables `seo_matcher_runs` and `seo_matcher_results`.
- `SeoSkuQuerySet.matcher_run_id` FK column (nullable for legacy rows).
- New endpoint `POST /projects/{p}/seo/matcher/v2/run`.
- Write path: `run_matcher_v2` writes one `SeoMatcherRun` + N `SeoMatcherResult` per call. Never overwrites `SeoMatcherResult` rows; a re-run creates a new run id.
- Soft lexical signals (current `_EXPRESSIVE_GROUPS` / `_AUDIENCE_GROUPS` / `_MATERIAL_CONSTRAINTS`) are not deleted — they are wrapped as `role=soft_signal, evidence_type=deterministic_guard` atoms produced by a `deterministic_atoms_builder` so they flow through the same stages.

**Excluded changes:**

- No replacement of `LocalPreviewEmbeddingProvider` with a real provider (tracked separately, needed for `quality_mode=full`).
- No deletion of current-path matcher.
- No refactor of existing `SeoSkuQuerySetItem`.
- No matcher DSL.

**Dependencies:**

- Atoms namespace promotion must land before `run_matcher_v2` integrates with them.
- Quality mode (WS-B) must land in the same iteration so matcher runs carry it from day one.

**Success criteria:**

- Given the same SKU, `run_matcher_v2` produces a reproducible `SeoMatcherRun` tied to sku_atoms_id + query_atoms_version + policy_version + category_profile_version.
- Every re-run creates a new `SeoMatcherRun` without mutating prior runs.
- Compare endpoint returns current-vs-candidate buckets for any 812 SKU that has both paths run.

**Risks:**

- Atoms code moved out of `experiments/` inherits whatever bugs it already has. Mitigation: do not refactor in the same commit as the move; land the move, then iterate.
- Writing one row per run grows storage. Mitigation: retention policy after 90 days for runs not referenced by an approved `SeoContentVersion`.

**Runs in parallel with current flow:** yes. Additive tables, additive endpoints, additive columns.

---

## WS-B. Degraded Mode Visibility

**Goal:** every decision-carrying row exposes `quality_mode` and `degraded_reasons`; UI shows a single badge; "approved" and "validated" are separate states.

**Why it exists:** today fallback looks like success, confirmed looks like validated, pseudo-semantic looks like semantic.

**Included changes:**

- Add columns on `SeoMatcherRun`, `SeoSkuMeaningAnnotation`, `SeoSkuQuerySet`, `SeoContentVersion`: `quality_mode enum`, `degraded_reasons jsonb`.
- Deterministic compute function `infer_quality_mode(pipeline_state)` called at the end of each major stage.
- `SeoSkuQuerySet`: new columns `selection_state ∈ {draft, approved}` and `trust_state ∈ {unvalidated, eval_validated}`. Keep `status` for one release, derive it.
- New append-only table `seo_quality_events(project, category, nm_id, scope, event_code, detail jsonb, occurred_at)` for support.
- `LocalPreviewEmbeddingProvider` forces `quality_mode ≤ preview` at every call site that uses it — enforced in the provider itself, not by convention.
- UI: add a reusable `QualityBadge` component and surface it on SKU summary, query selection, generation, and compare screens.
- UI: rename the "Confirm" button on query selection to "Approve selection" with an explicit tooltip.
- UI: label the generation relevance score as "internal lint; not a quality gate."

**Excluded changes:**

- Do not delete silent fallbacks. They are needed when caches miss or providers fail. The goal is visibility, not removal.
- Do not wire generation to fail on `degraded` mode. Preview may run in any mode; promotion rules enforce what is allowed.

**Dependencies:**

- None. This workstream can ship first and provides the framework other workstreams depend on.

**Success criteria:**

- Every new matcher run / generation run shows a quality mode in UI.
- Operators can see, for any decision, why it is in preview or degraded.
- No code path sets bucket/score without also setting quality_mode.

**Risks:**

- Many runs will be labeled `preview` until the real embedding provider is wired. This will feel bad. Mitigation: it is correct, and it is the signal the team needs to prioritize the embedding migration.
- Possible over-reporting of `degraded_reasons` generating UI noise. Mitigation: reason set is bounded enum, not free text.

**Runs in parallel with current flow:** yes. Additive columns.

---

## WS-C. Category Profile / Category-Calibrated Truth

**Goal:** all category-specific logic is held in a versioned `SeoCategoryProfile`. Shared engine carries no Russian term dictionaries.

**Why it exists:** the engine is category-812-calibrated and pretends to be general. Every other category today would silently run on mug-flavored lexicons.

**Included changes:**

- New table `seo_category_profiles(project_id, category_id, version, profile_payload jsonb, status, activated_at, created_at)`.
- New YAML seed at `config/seo/category_profiles/812_mugs.yaml` generated from current hardcoded dictionaries in `matcher.py`.
- Loader `services/seo/category_profile.py::load_active_profile(project_id, category_id)`.
- Matcher v2 stages read the profile as a parameter. No module-level term dicts.
- `SeoCategoryMatchingReadiness.eligibility_tier` column: `preview_only | eligible_for_preview | acceptance_passed`.
- `SeoMatcherRun.category_profile_version` column for replay.
- Lint rule / CI check: no Russian literal strings in `services/seo/matcher_v2/*`.

**Excluded changes:**

- Do not create profiles for new categories in this iteration.
- Do not attempt to learn profiles from data.
- Do not build a category-profile editor UI.
- Do not migrate current-path matcher to use the profile. Current path keeps its module-level dicts until deprecated.

**Dependencies:**

- WS-A (matcher v2 is the consumer of the profile).

**Success criteria:**

- Category 812's current matcher behavior is reproducible from the profile + matcher_v2.
- Matcher runs link to a specific `category_profile_version`.
- Adding a new category requires a profile row; there is no code path that will run matcher v2 without one.

**Risks:**

- Seeded profile may differ subtly from hardcoded behavior. Mitigation: compare layer + a regression harness on a frozen 812 SKU panel before any promotion.
- Profile payload schema will change as we learn. Mitigation: strict versioning; old runs stay readable against their version.

**Runs in parallel with current flow:** yes. Only candidate path reads the profile.

---

## WS-D. Generation Discipline / Preview Mode

**Goal:** generation is an explicit research preview. Promotion gated by matcher eval + human review. Internal relevance score demoted to a lint.

**Why it exists:** generation was built before the selection layer proved itself. Today it looks production-ready.

**Included changes:**

- `SeoContentVersion.content_kind` enum tightened: `preview | candidate | approved | published`. Migration path: existing `llm_draft` rows map to `preview` as read-time projection; new rows use the new enum directly.
- New column `SeoContentVersion.mode_used ∈ {current, candidate}` to make side-by-side compare unambiguous.
- New column `SeoContentVersion.publishable boolean` default false.
- `SEO_GENERATION_MAX_ATTEMPTS` capped at 1 and applied only to validator hard errors; remove the retry-against-relevance loop.
- New endpoint `POST /projects/{p}/seo/generation/{content_version_id}/promote` enforcing gates server-side.
- New table `seo_generation_human_review(content_version_id, reviewer_id, rubric_scores jsonb, verdict, reviewed_at)`.
- UI: "Research preview" banner; "Promote" button visible only when gates satisfied; disable the existing frontend `generationEndpointReady=true` hardcoding and tie it to env flag + category tier.
- Relabel existing `build_seo_relevance_report` / `build_seo_relevance_v2_report` output in UI as "internal lint."

**Excluded changes:**

- No batch generation.
- No WB Content API publish path (the `published` state is reserved, no code).
- No rewrite of the generation prompt or validator.
- No cross-category generation.

**Dependencies:**

- WS-A for matcher_run_id linkage.
- WS-B for quality_mode on content versions.
- WS-E for acceptance gate checks.

**Success criteria:**

- Generation cannot promote past preview without matcher eval green for the category.
- Generation cannot promote past candidate without human review rubric green.
- Frontend always shows the preview banner while category is below `acceptance_passed`.

**Risks:**

- Stakeholders will push back: "why disable generation we already have." Mitigation: keep generation running in preview; what is disabled is the *impression* of operational readiness.
- Human review creates a labeling cost. Mitigation: limit to 10-SKU panel per category; reuse the same panel across iterations.

**Runs in parallel with current flow:** yes. Current generation endpoint is unchanged during iteration 1; candidate endpoint and new states land alongside.

---

## WS-E. Eval As A Gate

**Goal:** turn the 191 labels and future labels into a runnable backend acceptance gate that controls category tier and generation promotion.

**Why it exists:** eval today is artifacts in a folder + scripts + human interpretation. It cannot block or permit anything in the system.

**Included changes:**

- New table `seo_eval_labels(label_set_id, project_id, category_id, nm_id, cluster_key, query_text, label, labeled_by, labeled_at)`.
- New table `seo_eval_runs(run_id, project_id, category_id, label_set_id, matcher_run_ids_considered jsonb, metrics jsonb, verdict, ran_at)`.
- One-time importer of `artifacts/meaning_atoms/20260422*` labels into `seo_eval_labels` as label_set_id=1 for category 812.
- New endpoint `POST /projects/{p}/seo/eval/matcher/run` computing accuracy / primary precision / primary recall / bad primary / hard-conflict primaries, writing an `seo_eval_run`, and flipping `SeoCategoryMatchingReadiness.eligibility_tier` when thresholds met.
- UI: eval page per category showing latest metrics, history, and current tier.

**Excluded changes:**

- No learnable label collection yet.
- No labeling UI in this iteration (reuse manual tools or direct DB inserts seeded from existing judgments + human input).
- No cross-category eval orchestration.

**Dependencies:**

- WS-A for `SeoMatcherRun` output being eval-readable.
- WS-C for category profile versioning.

**Success criteria:**

- Running eval on category 812 reproduces within tolerance the numbers reported in `23_atoms_v1_design_and_implementation_plan.md` table.
- Tier flips are observable in UI and in the readiness row.
- Generation promotion endpoint refuses promotion unless the latest eval for the category is green.

**Risks:**

- Label quality. The 191 labels were produced under the experiment's assumptions; some may need cleanup. Mitigation: version the label set (label_set_id=2 after cleanup); keep v1 for regression.
- Metric drift between script and backend implementation. Mitigation: one-shot parity test vs the scripts on ingest.

**Runs in parallel with current flow:** yes. Eval reads candidate matcher runs and optionally current-path query sets for comparison.

---

## WS-F. Dead Schema Freeze

**Goal:** freeze dead schema so nothing new depends on it. Delete later.

**Why it exists:** unused tables and helpers imply capability the system does not have and invite wrong wiring.

**Included changes:**

- Deprecation comment at top of each affected ORM class: `SeoSkuClusterRun`, `SeoSkuCluster`, `SeoSkuClusterAssignment`, `SeoClusterProfile`, `SeoClusterProfileVersion`, `SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation`.
- Runtime import guard: importing `services/seo/clustering/*` or `services/seo/scoring/service.py` from outside `diagnostics/` raises.
- `docs/seo-module/02_roadmap.md` amended with a "Frozen" section listing these entities.
- CI check that no new code references these symbols.

**Excluded changes:**

- Do not drop tables in iteration 1 or 2.
- Do not migrate data.
- Do not delete model files yet.

**Dependencies:**

- None. Can land in iteration 1 independently.

**Success criteria:**

- No new commit can import the frozen symbols from production paths.
- Schema audit query confirms zero writes to the frozen tables for 30 days.

**Risks:**

- Tests that still reference these may break. Mitigation: update tests to import from `diagnostics/` namespace or mark them xfail-frozen.

**Runs in parallel with current flow:** yes. Freezing does not change behavior.

---

## Cross-workstream dependency graph (summary)

```
WS-B (quality mode)           ──┐
WS-F (freeze dead schema)     ──┤── can ship in any order, iteration 1
WS-A (matcher authority)      ──┤
                                │
WS-C (category profile)       ──┤── depends on WS-A
WS-E (eval as gate)           ──┤── depends on WS-A, WS-C
                                │
WS-D (generation discipline)  ──┘── depends on WS-A, WS-B, WS-E
```

Recommended sequence:

- Iteration 1: WS-B, WS-F, WS-A (in that sensible order, can parallelize to some extent).
- Iteration 2: WS-C, WS-E, WS-D.
