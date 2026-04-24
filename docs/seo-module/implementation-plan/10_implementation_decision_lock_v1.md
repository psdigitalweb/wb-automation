# Implementation Decision Lock v1 — SEO Module (Draft)

Status: draft, grounded in the existing implementation planning package (`docs/seo-module/implementation-plan/00-09`), the prior audits under `docs/seo-module/audit-context/`, and the strategic clarifications already on record. Not final. Requires leadership confirmation before iteration 1 kickoff.

Principle of this document: under-lock rather than over-lock. Anything not clearly grounded in the existing package is either an `OPEN_DECISION` or an `UNVERIFIED_ASSUMPTION`.

---

## 1. `CONFIRMED_DECISIONS`

Decisions clearly supported by the existing package. Locked unless leadership explicitly reverses them.

### CD-1. No full rewrite; changes land additively alongside the current flow

- **Decision:** Iteration 1 does not replace the current matcher, current query selection, or current generation. All candidate-side changes are additive.
- **Source:** `00_executive_decision_memo.md` §"What is explicitly NOT being done now" and §"Implementation strategy"; `01_target_operating_model.md` §9 "What moves, what stays, what freezes"; accepted strategic constraint ("do NOT recommend a full replatform").
- **Consequence:** Engineering work in iteration 1 is dominated by additive columns, new tables, and new modules that coexist with existing services. No destructive migrations in iteration 1.

### CD-2. Matcher decisions gain a single replayable trace: `SeoMatcherRun` + `SeoMatcherResult`

- **Decision:** The candidate matcher writes one `SeoMatcherRun` plus N `SeoMatcherResult` rows per run. These are the only replayable decision records on the candidate path. They never mutate on re-run.
- **Source:** `01_target_operating_model.md` §2; `04_data_model_and_state_changes.md` §1.1-1.2; `05_backend_contract_changes.md` §1-2.
- **Consequence:** Two new tables in iteration 1 with additive schema. `SeoSkuQuerySet` gains a nullable `matcher_run_id` FK. No change to `SeoSkuQuerySetItem` semantics in iteration 1.

### CD-3. `quality_mode` is added to decision-carrying rows and is deterministically inferred

- **Decision:** Add `quality_mode ∈ {full, preview, degraded, fallback}` and `degraded_reasons` to `SeoMatcherRun`, `SeoSkuMeaningAnnotation`, `SeoSkuQuerySet`, `SeoContentVersion`, `SeoGenerationRun`. Values are produced by one shared function (`infer_quality_mode`), not set by humans.
- **Source:** `01_target_operating_model.md` §3; `04_data_model_and_state_changes.md` §2, §6.2; `05_backend_contract_changes.md` §4.
- **Consequence:** One migration per affected table, one shared service module, integration at four call sites (bootstrap, SKU draft, matcher, generation). UI surfaces this via a single `QualityBadge` component.

### CD-4. `LocalPreviewEmbeddingProvider` caps runs at `quality_mode ≤ preview`

- **Decision:** The preview embedding provider enforces its own ceiling at the provider level; any run using it cannot be labeled `full`.
- **Source:** `01_target_operating_model.md` §3; `05_backend_contract_changes.md` §4.
- **Consequence:** Provider interface gains a `max_mode` concept (or equivalent). Until a real embedding provider is wired, candidate runs carry `preview` by construction.

### CD-5. Dead schema is frozen (not deleted) in iteration 1

- **Decision:** `SeoSkuClusterRun`, `SeoSkuCluster`, `SeoSkuClusterAssignment`, `SeoClusterProfile`, `SeoClusterProfileVersion`, `SeoScoreRun`, `SeoQueryScore`, `SeoScoreExplanation`, and associated helpers (`scoring/service.py::create_score_run`, `persist_query_score`, `services/seo/clustering/*`) receive deprecation notices and import guards. No data changes, no drops.
- **Source:** `01_target_operating_model.md` §9; `03_workstreams_and_scope.md` WS-F; `04_data_model_and_state_changes.md` §4; `05_backend_contract_changes.md` §10.
- **Consequence:** Mechanical edits plus one CI rule. Drops are deferred.

### CD-6. Atoms code is promoted out of `experiments/` into production namespace

- **Decision:** `experiments/meaning_atoms/v1.py` and `schemas.py` move to `services/seo/atoms/v1/` in iteration 1. The move is a relocation with minimal code edits; refactor is deferred.
- **Source:** `03_workstreams_and_scope.md` WS-A; `08_top_level_backlog.md` T-2.1.
- **Consequence:** Import paths update across the matcher pipeline. The old location is frozen against further imports from production code.

### CD-7. Generation is a research preview; retry-on-relevance is removed

- **Decision:** `SEO_GENERATION_MAX_ATTEMPTS = 1`, applied only to validator hard errors. The internal relevance report (`build_seo_relevance_report` / V2) is demoted to an internal lint and does not drive retries or promotion. A "Research preview" banner is shown on the generation UI while a category is below `acceptance_passed` or the candidate flag applies.
- **Source:** `01_target_operating_model.md` §5; `03_workstreams_and_scope.md` WS-D; `06_ui_and_operator_flow_changes.md` §5; `08_top_level_backlog.md` T-5.1, T-5.2.
- **Consequence:** Small code/constant change, UI copy change, removal of the hardcoded `generationEndpointReady=true`, and an env flag (`SEO_GENERATION_PREVIEW_ENABLED`).

### CD-8. Parallel validation is the methodology; promotion requires measured evidence

- **Decision:** Candidate-path results and current-path results run side by side on the same SKUs. A read-only compare layer (endpoint + UI panels) surfaces per-SKU deltas. Promotion of the candidate flow requires the acceptance gate on eval plus human verdicts on a fixed panel.
- **Source:** `00_executive_decision_memo.md` §"What 'parallel validation' means here"; `02_parallel_validation_strategy.md` whole document; `07_iteration_plan.md` Iteration 2 & 3 sections.
- **Consequence:** Iteration 2 ships `GET /compare/matcher` and `GET /compare/generation`. Compare is read-only and architecturally isolated from the matcher modules.

### CD-9. No new category-specific logic in iteration 1; profile extraction is locked as the iteration 2 mechanism

- **Decision:** Iteration 1 does not add any new category-specific logic (category-name literals, new hardcoded category dictionaries, per-category branches) to candidate modules — in particular `services/seo/matcher_v2/` and `services/seo/atoms/v1/`. Extraction of category-specific rules into `SeoCategoryProfile` is locked as the iteration 2 mechanism. Pre-existing category-calibrated dictionaries in the current matcher remain where they are until iteration 2 extracts them.
- **Source:** `01_target_operating_model.md` §4; `03_workstreams_and_scope.md` WS-C; `07_iteration_plan.md` Iteration 2 scope; strategic clarification response on Q10.
- **Consequence:** Iteration 1 refactors are structural (stage ordering, trace writing, atoms relocation) and must not introduce fresh category literals. `SeoCategoryProfile` table, loader, and 812 seed land in iteration 2 and are not treated as operational truth before then.

### CD-10. Labels are eval-only; not read by runtime decision paths; not introduced in iteration 1

- **Decision:** `seo_eval_labels` is consumed by the eval harness only. No production decision path (matcher, query selection, generation) reads labels. The labels table and the one-time import of existing 191 labels for category 812 land in iteration 2, not iteration 1.
- **Source:** `04_data_model_and_state_changes.md` §1.4; `07_iteration_plan.md` Iteration 2 scope; strategic clarification response on Q2.
- **Consequence:** Iteration 1 touches no labeling code, schema, or import. A CI check added in iteration 2 enforces the "no runtime reader of labels" rule.

### CD-11. Iteration 1 and iteration 2 each have a defined "what we can prove"

- **Decision:** Iteration 1 proves that every decision carries a quality mode and a replayable trace, and that dead schema cannot be re-entangled. Iteration 2 proves that eval gates category advancement, that matcher behavior is reproducible from a versioned profile, and that generation lifecycle is server-enforced.
- **Source:** `07_iteration_plan.md` §"Iteration 1" and §"Iteration 2".
- **Consequence:** Iteration close criteria are measurable. No vague milestones.

---

## 2. `OPEN_DECISIONS_REQUIRING_OWNER_SIGNOFF`

Decisions the package either leaves unresolved, recommends a default for, or frames as leadership choices.

### OD-1. Default of `SEO_GENERATION_PREVIEW_ENABLED` in production

- **Question:** Default-off (enabled per category post tier-flip) or default-on (banner-driven discipline)?
- **Why it matters:** Affects whether iteration 1 changes user-visible generation behavior.
- **Package recommendation:** Default-off. (`09_open_questions_and_decision_points.md` Q3, plan default A.)
- **Risk if unresolved:** Operators turn generation on ad hoc; preview discipline becomes aspirational.

### OD-2. Iteration 2 category scope

- **Question:** Do iteration 1 and iteration 2 remain strictly 812-only, or does iteration 2 include a second category as a stress test of the profile abstraction?
- **Why it matters:** Labeling owner (OD-3), eval threshold portability, and profile loader assumptions all change.
- **Package recommendation:** 812 only. (`09_open_questions_and_decision_points.md` Q1, plan default A.)
- **Risk if unresolved:** WS-C may over- or under-invest in abstractions. Scope of iteration 2 remains ambiguous.

### OD-3. Owner for per-category measurement workload (profile seed, 50-200 labels, ~10-card rubric, ~20-SKU compare verdicts)

- **Question:** Product ops, engineering, third-party annotators, or unassigned until iteration 2?
- **Why it matters:** Gates iteration 2's acceptance of labels for any new category. Iteration 2 for 812 alone does not depend on this owner (labels already exist).
- **Package recommendation:** None; explicitly unnamed in `09_open_questions_and_decision_points.md` Q2.
- **Risk if unresolved:** The eval gate exists but cannot be fed for new categories, blocking any Stage-2 expansion.

### OD-4. Sunset timing of the current matcher after promotion

- **Question:** Immediate removal, one-release archival (plan default), or two-release archival?
- **Why it matters:** Drives when maintenance overhead of two systems actually ends.
- **Package recommendation:** One-release archival under `legacy/`. (`09_open_questions_and_decision_points.md` Q11.)
- **Risk if unresolved:** Candidate gets promoted and the team continues supporting both paths indefinitely.

### OD-5. Whether matcher compare human verdict is a formal gate or informational

- **Question:** Promotion requires ≥70% favor-candidate on a verdict panel (plan default) or metrics-only promotion?
- **Why it matters:** Determines whether the human-verdict capture in iteration 2 is load-bearing or merely diagnostic.
- **Package recommendation:** Required. (`09_open_questions_and_decision_points.md` Q8.)
- **Risk if unresolved:** Iteration 2 ships a UI that captures data leadership does not use; or leadership expects signal that engineering did not wire.

### OD-6. Scope of `selection_state` / `trust_state` decomposition in iteration 1

- **Question:** Does iteration 1 introduce the two-axis selection state, or is this strictly iteration 2 (plan default)?
- **Why it matters:** Renaming "Confirm" to "Approve selection" is small; adding the two-axis model touches several readers.
- **Package recommendation:** Iteration 2. (`07_iteration_plan.md` Iteration 2 bulleting; `08_top_level_backlog.md` T-7.1 priority P0 iteration 2.)
- **Risk if unresolved:** Pulled into iteration 1 scope under UI pressure, inflating iteration 1.

### OD-7. Whether `seo_quality_events` ships in iteration 1

- **Question:** Ship the append-only quality events table as a P2 item in iteration 1, or defer.
- **Why it matters:** Support visibility now vs iteration scope.
- **Package recommendation:** Defer; listed as P2 with optional pull-in. (`04_data_model_and_state_changes.md` §1.7; `08_top_level_backlog.md` T-7.5.)
- **Risk if unresolved:** Pulled in inconsistently across teams.

### OD-8. Whether `SEO_CANDIDATE_FLOW_DEFAULT` exists as a flag from day one or is introduced in iteration 2

- **Question:** Ship the flag in iteration 1 (off, but wired), or introduce it in iteration 2 at compare-layer time?
- **Why it matters:** Affects how candidate endpoints are reached in iteration 1 (explicit URL only vs flag-reachable).
- **Package recommendation:** The plan mentions the flag but does not firmly pin the iteration. `02_parallel_validation_strategy.md` §10 implies the flag exists; the iteration 1 scope in `07_iteration_plan.md` does not require it to be wired.
- **Risk if unresolved:** Routing story for candidate endpoints is ambiguous at kickoff.

### OD-9. Eval threshold locality

- **Question:** Are acceptance-gate thresholds constants in the harness (iteration 2 simpler), or profile-valued with 812 defaults (future-proofed per the universality correction)?
- **Why it matters:** Profile-valued thresholds are cheap if designed in from day one; retrofitting later is costlier.
- **Package recommendation:** Strategic clarification recommended profile-valued with 812 defaults; the iteration plan (`07_iteration_plan.md` Iteration 2) does not pin this.
- **Risk if unresolved:** Thresholds get hardcoded and become the second-category migration tax.

### OD-10. Who signs off on `candidate → approved` generation promotion

- **Question:** Content/product lead, engineering + product jointly (plan default), or automated once metrics cross a threshold?
- **Why it matters:** Irrelevant in iteration 1; required before iteration 2 closes.
- **Package recommendation:** Engineering + product together. (`09_open_questions_and_decision_points.md` Q12.)
- **Risk if unresolved:** Promotion happens under unclear authority at end of iteration 2.

---

## 3. `UNVERIFIED_ASSUMPTIONS_TO_AVOID_TREATING_AS_LOCKED`

Assumptions that sound safe but are not clearly established in the existing package. Treat as uncertain.

### UA-1. Iteration durations (~2 weeks each)

- **Assumption:** Each iteration fits in roughly two weeks.
- **Why unsafe:** `07_iteration_plan.md` uses "≈ 2 weeks" as an estimate, not a commitment. No team capacity check, no resourcing plan, no task-level sizing in the package.
- **To verify:** Engineering capacity review against `08_top_level_backlog.md` tasks.

### UA-2. Matcher_v2 can reproduce current 812 behavior within tolerance without meaningful logic changes

- **Assumption:** Refactoring the current matcher into staged functions will preserve 812 bucketing closely enough for compare to be meaningful.
- **Why unsafe:** `03_workstreams_and_scope.md` WS-A and `08_top_level_backlog.md` T-2.2 list this as a "medium" risk. Current matcher orders soft score before the atoms gate, so switching to eligibility-first is a real semantic change, not a pure refactor. Parity is a hypothesis to be tested, not a fact.
- **To verify:** Regression harness on a frozen 812 SKU panel during iteration 1 (work item exists at least implicitly in WS-A success criteria).

### UA-3. The existing 191 labels are directly usable as `label_set_id=1`

- **Assumption:** The existing `artifacts/meaning_atoms/20260422*` labels map cleanly onto the new eval schema and produce the numbers referenced in `23_atoms_v1_design_and_implementation_plan.md`.
- **Why unsafe:** The package flags label-quality risk (`03_workstreams_and_scope.md` WS-E Risks; `09_open_questions_and_decision_points.md` §1). A parity check is planned but not done.
- **To verify:** One-shot parity test on ingest in iteration 2.

### UA-4. Hardcoded category dictionaries in `matcher.py` translate cleanly to a YAML profile

- **Assumption:** The 812 profile seed generated from current hardcoded dictionaries reproduces current matcher behavior under matcher_v2.
- **Why unsafe:** The dictionaries are intertwined with code-level scoring paths in the current matcher. Extracting them into a declarative profile may change subtle behaviors in ways that cannot be called pure refactors.
- **To verify:** Same 812 regression panel, comparing matcher_v2 with and without the profile-driven configuration against the current matcher baseline.

### UA-5. The existing embedding provider is adequate for eval parity

- **Assumption:** Running the candidate path with `LocalPreviewEmbeddingProvider` produces eval numbers good enough to demonstrate improvement over the current path.
- **Why unsafe:** Strategic clarification and plan sections acknowledge that preview-mode embeddings will systematically cap run quality at `preview`. Eval numbers may look worse than the candidate logic deserves.
- **To verify:** Either a decision to run eval with a real provider before promotion, or documented acceptance that iteration 2 eval is diagnostic rather than dispositive. Not decided in the package.

### UA-6. `quality_mode` propagation rule (upstream_mode_min via reasons) is semantically sound

- **Assumption:** Each layer computing its own mode and including `upstream_mode_min` as a `degraded_reason` yields a coherent end-to-end read.
- **Why unsafe:** Written once in the plan without exercise against real flows. Operator-facing interpretation ("why is my matcher run `degraded`?") depends on this rule being intuitive.
- **To verify:** A pass on 5-10 representative pipeline traces during iteration 1, checking that the computed mode matches operator intuition.

### UA-7. A single `QualityBadge` enum is operator-sufficient

- **Assumption:** Four states (`full | preview | degraded | fallback`) are enough for operators to make decisions.
- **Why unsafe:** The enum is plan-level; operators have not been shown it. Real flows may produce a `degraded`-heavy distribution that renders the badge low-information.
- **To verify:** Distribution review after 1-2 weeks of iteration 1 use.

### UA-8. Two iterations are sufficient to reach a promotion decision

- **Assumption:** Iteration 2 closes with enough eval + compare data to pick promote / extend / reject.
- **Why unsafe:** Depends on UA-2, UA-3, UA-5. Also depends on human-verdict panel throughput being realistic, which is not sized.
- **To verify:** Iteration 1 close review with realistic scoping of iteration 2 human-review and label budget.

### UA-9. Compare layer can stay purely read-only in practice

- **Assumption:** The compare layer will remain a diff + verdict capture and will not accumulate reconciliation logic.
- **Why unsafe:** The risk is called out in the prior review but not mechanically eliminated. It is a discipline bet, not an architectural one, until lint/CI rules are in place.
- **To verify:** Lint rule forbidding compare router imports from matcher modules, and read-only DB session enforcement, landed with the compare endpoints.

### UA-10. Storage cost of one `SeoMatcherRun` per run is acceptable

- **Assumption:** Writing a full run + per-query results on every candidate invocation is fine at current and near-term SKU/query volumes.
- **Why unsafe:** No volume estimate or retention analysis in the package beyond "retention policy after 90 days" (`03_workstreams_and_scope.md` WS-A Risks). The policy is mentioned but not sized.
- **To verify:** A back-of-envelope volume calculation at kickoff and a confirmation that the 90-day policy is sufficient.

---

## 4. `ITERATION_1_LOCKED_SCOPE`

Items locked for iteration 1 based on the package. Split by priority. Pull-ins beyond this list require explicit justification.

### 4.1 `ITERATION_1_LOCKED_SCOPE — P0 (must-ship core)`

1. **Quality-mode columns + shared `infer_quality_mode` + integrations** at four call sites (bootstrap, SKU draft, matcher, generation). (`08_top_level_backlog.md` T-1.1, T-1.2.)
2. **Provider-level preview ceiling** on `LocalPreviewEmbeddingProvider`. (T-1.3.)
3. **`QualityBadge` component** and its initial placements (SKU summary, query selection, generation, product list). (T-1.4.)
4. **Atoms relocation** from `experiments/meaning_atoms/*` to `services/seo/atoms/v1/` with minimal edits. (T-2.1.)
5. **Matcher v2 staged function** as a refactor of current matcher into `eligibility → bucket_cap → soft_score → demand_ordering`, writing `SeoMatcherRun` + `SeoMatcherResult`. (T-2.2.)
6. **New matcher tables and endpoint**: `seo_matcher_runs`, `seo_matcher_results`, `SeoSkuQuerySet.matcher_run_id` FK, `POST /matcher/v2/run`, `GET /matcher/v2/runs/{run_id}`. (T-2.3.)
7. **Generation retry cap** and **relevance relabel as internal lint**. (T-5.1.)
8. **Preview banner** on generation page and removal of hardcoded `generationEndpointReady=true`; env flag `SEO_GENERATION_PREVIEW_ENABLED` wired. (T-5.2.)
9. **Deprecation notices** on frozen ORM classes (clustering + scoring schema). (T-6.1.)
10. **Import guards** on frozen service modules + CI check. (T-6.2.)

### 4.2 `ITERATION_1_LOCKED_SCOPE — P1 (can slip if capacity is tight)`

1. **Matcher run viewer** read-only page. (T-2.4.)
2. **Physical move of `scoring/preparation.py`, `scoring/actual.py` under `diagnostics/`**. (T-6.3.)

---

## 5. `ITERATION_1_EXPLICITLY_OUT_OF_SCOPE`

Items that must not be pulled into iteration 1 regardless of perceived usefulness.

- `SeoCategoryProfile` table, loader, or 812 seed (iteration 2).
- Eval endpoint or `seo_eval_labels` / `seo_eval_runs` tables.
- `SeoCategoryMatchingReadiness.eligibility_tier` column.
- `seo_generation_human_review` table or `POST /generation/{id}/promote` endpoint.
- `SeoSkuQuerySet.selection_state` / `trust_state` decomposition.
- `content_kind` enum tightening beyond adding `mode_used`, `publishable`, `matcher_run_id`, `quality_mode`, `degraded_reasons`. The enum tightening and four-state promotion flow belong to iteration 2.
- Compare endpoints (`GET /compare/*`) and compare UI panels.
- `CategoryTierBadge` component (introduced with tier column in iteration 2).
- Any `SEO_CANDIDATE_FLOW_DEFAULT` forwarding behavior (flag may be defined but not used to route default traffic).
- Any data migration or backfill of existing `SeoSkuQuerySet`, `SeoSkuQuerySetItem`, `SeoContentVersion` rows.
- Any drop of frozen clustering or scoring tables.
- Any second-category profile or seed.
- Any new labeling UI.
- Any stable-category-scope / WB subject-id surrogate work.
- Any batch generation or WB Content API work.

---

## 6. `SAFE_START_CRITERIA`

Conditions that must hold before iteration 1 engineering kickoff. If any is unmet, kickoff should be deferred or the scope adjusted.

1. **Leadership sign-off on the CONFIRMED_DECISIONS block** (§1 of this document), treating them as locked for iteration 1.
2. **Explicit acceptance of the iteration-1 proof criteria.** The team must agree, before kickoff, that iteration 1 is intended to prove only these four things:
   1. every candidate decision has a replayable matcher trace (via `SeoMatcherRun` + `SeoMatcherResult`);
   2. every surfaced result carries `quality_mode`;
   3. candidate matcher runs additively, without corrupting current-path semantics (no overwrite of current-path decision rows, no breaking schema change);
   4. generation no longer presents itself as production-ready (preview banner, retry cap, relevance relabel, env-flag gating).
   Anything outside these four is out of scope for iteration-1 proof and must not be used to judge iteration 1.
3. **Owners assigned per workstream** in iteration 1 scope: WS-A (matcher authority), WS-B (quality mode), WS-D (generation discipline first-cut), WS-F (freeze dead schema). Names, not roles.
4. **A documented resolution for OD-1** (default of `SEO_GENERATION_PREVIEW_ENABLED` in production). Default-off per package recommendation is acceptable; the decision must be on record.
5. **A documented resolution for OD-8** (whether `SEO_CANDIDATE_FLOW_DEFAULT` exists as a wired flag in iteration 1). Either answer is acceptable; silence is not.
6. **Explicit acknowledgement that UA-2, UA-6, UA-9, UA-10 are unverified**, with a named engineer responsible for producing verification artifacts during iteration 1 (parity harness for UA-2, trace review for UA-6, lint/CI rules for UA-9, volume estimate for UA-10).
7. **Engineering capacity check against the iteration-1 locked scope**, with the understanding that UA-1 (two-week estimate) is an estimate, not a commitment. If capacity does not fit the locked scope, scope is trimmed from the P1 items (§4.2) before kickoff, not during.
8. **Repository-level CI capability confirmed**: lint rules, import guards, and additive migrations can land without blocking the main branch. (The plan assumes these are available but does not verify them.)
9. **Agreement that OD-2 through OD-7, OD-9, OD-10 can be resolved during iteration 1 execution without blocking kickoff**, on the condition that OD-2, OD-3, OD-5, OD-9, OD-10 are resolved before iteration 2 scoping begins.

If conditions 1, 2, 3, 4, 5, 7, 8 are met, kickoff is safe. Condition 6 is a process commitment rather than a gate. Condition 9 is a scheduling rule for iteration 2, not iteration 1.

---

End of draft lock v1. Items not appearing in `CONFIRMED_DECISIONS` should not be treated as locked in downstream planning documents without explicit leadership confirmation.
