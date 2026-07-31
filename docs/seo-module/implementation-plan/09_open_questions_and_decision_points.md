# 09. Open Questions And Decision Points

Audience: CTO / CEO / architect
Date: 2026-04-23

Purpose: surface every decision the plan silently assumes. Each item lists the decision, the tradeoff, the default the plan runs on if leadership is silent, and the risk of deferring.

---

## 1. Must-decide-before-implementation

These shape iteration 1 scope. Deferring them means iteration 1 drifts.

### Q1. Do we accept "the candidate path exists only for category 812" as the scope for both iterations?

- Options:
  - A. Yes. Only 812 gets a calibrated profile; new categories stay preview_only.
  - B. Expand to a second category in iteration 2 to stress-test the profile abstraction.
- Tradeoff: B validates that profiles actually generalize but multiplies labeling cost and UI polish work.
- Plan default: A.
- Risk of indecision: WS-C may over-invest in abstractions we never test, or under-invest because we assumed single-category.

### Q2. Who owns labeling for categories beyond 812?

- Options:
  - A. Product ops team (hiring / process not yet defined).
  - B. Engineering team as a side task.
  - C. Third-party / annotator contract.
- Tradeoff: cost vs speed vs quality.
- Plan default: unnamed; iteration 2 relies on the existing 191 labels only.
- Risk of indecision: we land the eval gate then cannot advance categories because no one labels.

### Q3. Is `SEO_GENERATION_PREVIEW_ENABLED` default-on or default-off in production environment?

- Options:
  - A. Default-off; enabled only for specific categories post-tier-flip.
  - B. Default-on; banner and gates carry the weight.
- Tradeoff: A is safest; B gives faster feedback but relies on UI discipline.
- Plan default: A.
- Risk of indecision: teams turn generation on ad hoc without a consistent story.

### Q4. Do we keep `SeoSkuQuerySet.status` as a derived field for one release, or do we drop it immediately when we add `selection_state` + `trust_state`?

- Options:
  - A. Keep derived for one release (safer integrations).
  - B. Drop immediately.
- Tradeoff: A risks ambiguity; B risks integration breakage.
- Plan default: A.
- Risk of indecision: every consumer keeps a stale meaning of "confirmed."

### Q5. Is `LocalPreviewEmbeddingProvider` an acceptable default on the candidate path during iteration 2?

- Options:
  - A. Yes. Candidate path stays in `preview` mode until a real provider is wired.
  - B. Block candidate path unless a real embedding provider is available.
- Tradeoff: A lets us validate matcher logic independent of embedding swap; B blocks progress on a dependency.
- Plan default: A (with a `QualityBadge: preview` on every run).
- Risk of indecision: eval results look mediocre because the provider is the bottleneck, not the logic.

### Q6. Where does the candidate-matcher logic live on day one: a copy of current matcher inside `matcher_v2/`, or a minimal rewrite that enforces eligibility-first?

- Options:
  - A. Copy + small refactor to enforce stage ordering. Fast.
  - B. Clean rewrite informed by atoms v1 experiment. Higher quality, longer.
- Tradeoff: A is faster and safer but carries accumulated heuristics; B is cleaner but adds iteration risk.
- Plan default: A in iteration 1, incremental tightening in iteration 2.
- Risk of indecision: team pulls toward B mid-iteration and slips scope.

### Q7. Do we introduce `seo_quality_events` now or defer?

- Options:
  - A. Introduce in iteration 1 as part of WS-B (P2 task).
  - B. Defer to iteration 3 cleanup.
- Tradeoff: support value vs plumbing cost.
- Plan default: B, but T-7.5 is listed as P2 in iteration 1 if slack exists.
- Risk of indecision: support requests come in without a timeline and we bolt it on poorly.

---

## 2. Must-decide-before-iteration-2

These shape iteration 2 scope. Deferring into iteration 2 week 1 is still fine; deferring past that creates drift.

### Q8. Matcher compare human verdict: is it required for promotion or informational?

- Options:
  - A. Required — promotion gate includes ≥ 70% favor-candidate on a panel.
  - B. Informational — eval metrics alone gate promotion.
- Tradeoff: A is stricter and slower but catches issues eval doesn't; B is cleaner.
- Plan default: A.
- Risk of indecision: promotion criteria feel unprincipled and drift later.

### Q9. What is the minimum label count for `preview_only → eligible_for_preview`?

- Plan default: 50 labels, reduced gate thresholds.
- Tradeoff: lower bar = faster tier flips for new categories = less confident previews.
- Risk of indecision: new categories flip too fast, surfacing bad previews under the banner.

### Q10. What is the promotion rule for the candidate flow to become default?

- Options:
  - A. Per-category decision: candidate default only for categories that are `acceptance_passed`.
  - B. Module-wide decision: candidate default globally once 812 passes.
- Tradeoff: A is granular and safer; B is simpler but riskier for unvalidated categories.
- Plan default: A.
- Risk of indecision: leadership expects B while team implements A.

### Q11. What is the sunset window for the current-path matcher after candidate is promoted?

- Options: immediate removal vs one-release archival vs two-release archival.
- Plan default: one-release archival under `legacy/`.
- Risk of indecision: current-path code accumulates "just in case" tweaks and the team is supporting two systems.

### Q12. Who signs off on promotion to `approved` generation state?

- Options:
  - A. Head of product / content lead.
  - B. Engineering lead + product together.
  - C. Automated once metrics cross a threshold.
- Tradeoff: C is the easiest to scale but removes judgment from a preview-era product.
- Plan default: B until data supports C.
- Risk of indecision: promotions happen under unclear authority.

---

## 3. Tradeoffs leadership must choose

These are not blocking but carry meaningful product consequence.

### Q13. Investment split: matcher stability vs generation polish.

The plan puts weight on matcher. Leadership may prefer faster generation polish because it is visible to customers.

- Risk of picking generation: reintroduces the audit's core problem (generation before selection proven).
- Risk of picking matcher: customer-visible polish is slow.
- Plan recommendation: matcher first.

### Q14. Whether to introduce a stable category scope surrogate during this plan.

- The audit flagged WB subject id instability as a risk. Plan defers.
- Cost of addressing: migration + new FK on most SEO tables.
- Cost of deferring: occasional category mis-scoping when WB renumbers subjects.
- Plan default: defer. Risk tracked, not mitigated.

### Q15. Whether to build a minimal labeling UI in iteration 2 instead of iteration 3+.

- Without it, label ingestion relies on scripts or DB inserts.
- Cost: about 3 days of frontend work.
- Benefit: unblocks category 2 labeling workflows the moment a product ops owner is named.
- Plan default: defer. Add only if Q2 resolves with an owner.

### Q16. Compare-layer retention policy.

- How long do we keep `SeoMatcherRun` rows on the candidate path?
- Options: indefinite vs 90 days vs purge after promotion decision.
- Plan default: 90 days for runs not referenced by an `approved` content version.
- Risk: storage creep if unsettled.

### Q17. Human rubric thresholds on generation promotion.

- Plan default: relevance ≥ 8/10, fidelity ≥ 8/10, zero unsupported hard claims.
- Leadership may want 7/10 to speed throughput, or 9/10 to be conservative.
- Plan will lock at 8/8 unless overridden before iteration 2.

### Q18. Do we instrument any telemetry export (e.g., to BI or logs) on `quality_mode` distributions?

- Useful for trend reporting; costs some infra plumbing.
- Plan default: per-iteration rolling metrics are gathered via ad-hoc queries against the new tables. No automated export.
- Risk of deferring: fewer quantitative signals available in leadership reviews.

---

## 4. Items that can be deferred (and should be)

- Stable `category_scope_id` migration.
- Learnable / auto-profile generation.
- Batch generation.
- Publish / WB Content API.
- Cross-category rollout plan.
- Labeling UI.
- Deletion of frozen schema (waits for 30-day audit window).
- Replacing `SeoQueryAnnotation.meta["hybrid_annotation"]` JSON-as-schema pattern.
- Model policy overhaul.

Each can wait. None affects the two-iteration plan's success criteria.

---

## 5. Risks of indecision (summary)

If any of Q1-Q6 remain open past iteration 1 kickoff:

- WS-A and WS-C will pull scope against each other.
- Implementation team will re-open the audit in standups.
- "Preview" banner will be argued over.
- Parallel validation will not actually start because no one knows which path is default.

If Q7-Q12 remain open past iteration 2 week 1:

- Compare layer will be built without a clear consumer of its signal.
- Eval thresholds may be misaligned with promotion criteria.
- Leadership promotion decision in iteration 3 will lack explicit authority.

---

## 6. Suggested resolution format

For each question, capture the decision in a single line in this document with the date and owner:

```
Q1. 2026-04-24 — CEO — A (only 812 in-scope; re-evaluate after iteration 2).
Q3. 2026-04-24 — CTO — A (env flag default off).
...
```

Once the must-decide-before-implementation block (Q1-Q7) has all lines filled, iteration 1 kickoff is unblocked.

Once Q8-Q12 are filled, iteration 2 kickoff is unblocked.

Q13-Q18 may be decided mid-iteration but each is tied to a specific task; when that task starts, the decision must be on record.
