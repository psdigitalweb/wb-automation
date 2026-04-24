"""Backend eval harness — Iteration 2 (WS-E).

Only entrypoint exposed to the rest of the app is
:func:`app.services.seo.eval.harness.run_matcher_eval`. The harness is the
single writer of ``SeoCategoryMatchingReadiness.eligibility_tier``; no other
module is allowed to update that column.
"""

from app.services.seo.eval.harness import (
    ELIGIBILITY_TIER_APPROVED,
    ELIGIBILITY_TIER_EVALUATED,
    ELIGIBILITY_TIER_PREVIEW_ONLY,
    EVAL_THRESHOLDS,
    EvalHarnessError,
    MatcherEvalResult,
    run_matcher_eval,
)


__all__ = [
    "ELIGIBILITY_TIER_APPROVED",
    "ELIGIBILITY_TIER_EVALUATED",
    "ELIGIBILITY_TIER_PREVIEW_ONLY",
    "EVAL_THRESHOLDS",
    "EvalHarnessError",
    "MatcherEvalResult",
    "run_matcher_eval",
]
