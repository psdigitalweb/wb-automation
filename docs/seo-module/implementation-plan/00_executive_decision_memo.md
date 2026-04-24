# 00. Executive Decision Memo

Audience: CEO / CTO
Date: 2026-04-23
Status: proposed for approval

---

## What is being fixed

The SEO module has four accepted structural problems:

1. No single authority for meaning-to-query matching decisions.
2. Degraded modes are invisible (fallback looks like success, "confirmed" looks like validated).
3. The engine is calibrated for one category (mugs / 812) but presents itself as general.
4. Generation is implemented and surfaced before the selection layer has proven itself.

This plan fixes these four problems in a controlled, staged way, without rewriting the system and without removing the current flow.

## Why this matters in business terms

- Today we cannot tell whether a generated product card is based on a validated matcher or on a pseudo-semantic proxy with silent fallbacks. This makes every launch risky.
- Today the team can demo generation as if it were operational. Leadership decisions made on that impression are decisions on sand.
- Expanding to a second category today means copying hardcoded Russian term lists and hoping. There is no measurable onboarding.
- The cost of shipping a wrong card at marketplace scale is margin loss, trust loss, and refund friction. This must be gated.

The fix turns "we think the SEO pipeline is working" into "we can prove, per category, whether it is."

## What is explicitly NOT being done now

- No replatform.
- No universal abstraction / DSL for matcher rules.
- No new super-entity that unifies meanings.
- No batch generation.
- No WB Content API publish path.
- No cross-category rollout.
- No stable-category-scope migration (WB subject id instability is documented but not addressed).
- No deletion of dead schema in iteration 1 (freeze first, delete later).

## Implementation strategy

Parallel-validatable, not rip-and-replace.

- The current matcher + current query-selection + current generation keep running for category 812.
- A **candidate operating model** is built alongside the current flow behind flags and distinct endpoints.
- Both flows are run on the same SKUs; results are visible side by side in a compare layer.
- A real eval gate (based on the existing 191 labels + a reduced onboarding label set for any new category) decides if the candidate replaces the current path.
- Nothing promotes to "operational" without that eval gate going green.

The candidate model rests on four pieces:

- One staged matcher authority (`SeoMatcherRun` as the only decision trace).
- Explicit `quality_mode` visible on every decision and every generated card.
- A versioned `SeoCategoryProfile` that holds all category-specific rules. Category 812 is the only calibrated profile.
- A four-state generation lifecycle (`preview → candidate → approved → published`) with promotion gated by matcher eval and human review. `published` has no code path yet.

## What "parallel validation" means here

Parallel validation means:

- Current and candidate both run, per request, producing comparable outputs.
- A UI compare view shows the delta on the same SKU: bucket assignments, primary precision, conflict handling, generated card differences.
- Metrics (eval accuracy / primary precision / bad primary count / human rubric) accumulate on candidate until it meets or exceeds current, then promotion is proposed.
- No operator decision (approval, "send to production") is allowed to skip the compare layer while candidate is in shadow.

We are not picking winners in code reviews. We are picking winners on measured deltas.

## What decision will be made after validation

At the end of the two planned iterations, leadership decides one of three outcomes per category (starting with 812):

1. **Promote candidate → becomes default.** Current path is archived in code but not deleted. Requires matcher acceptance gate green + generation human review green.
2. **Keep both, extend candidate.** Candidate has measurable gains but not enough for promotion. Next iteration tightens the gaps.
3. **Reject candidate.** Candidate did not improve. The candidate flow is rolled back; insights feed the current path.

This is a decision against measured evidence. No promotion by narrative.

## Iteration scope summary

**Iteration 1 (≈ 2 weeks):**

- Introduce `quality_mode` and `degraded_reasons` across matcher run, query set, content version.
- Move atoms code out of `experiments/` into production namespace.
- Reorder the matcher to eligibility-first, write `SeoMatcherRun` as the decision trace.
- Cap generation retry logic and put generation behind an explicit preview flag with a banner.
- Freeze dead schema (SKU clustering, score tables, cluster profiles) via deprecation notices and import guards.

End of iteration 1, we can answer: "given a SKU, which decision trace produced its bucket, at what quality, against which category profile, on which matcher version."

**Iteration 2 (≈ 2 weeks):**

- Extract category-specific rules into `SeoCategoryProfile` with a category-812 seed.
- Wire a runnable eval endpoint that turns the 191 labels into a live acceptance-gate check.
- Introduce the four-state `content_kind` lifecycle and `seo_generation_human_review`.
- Add the compare layer in UI (current vs candidate for matcher and for generation).
- Make `eligibility_tier` on category readiness the gate that enables generation preview per category.

End of iteration 2, we can answer: "is the candidate matcher better than the current one for category 812, against labels, with explainable reasons, and is generation allowed to move past preview."

## Out of scope for this package

- Stable category scope migration (documented as risk, deferred).
- Second-category rollout.
- Batch generation / publish flow.
- Learnable category profile.
- Replacing the provider boundary or embedding infrastructure.

## Ask

Approve this plan, approve the two-iteration scope, and approve "no promotion without measured evidence" as the promotion rule.
