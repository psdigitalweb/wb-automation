"""Candidate matcher authority (matcher_v2) — iteration 1 additive path.

This package is the authoritative candidate-path matcher for SKU query
selection. It is a *copy+refactor* of
``services.seo.query_meaning_matcher.matcher.run_meaning_aware_matcher`` into
four explicit stages: ``eligibility`` -> ``soft_score`` -> ``bucket_cap`` ->
``demand_ordering``, plus a persistence layer that writes a replayable trace
into ``seo_matcher_runs`` / ``seo_matcher_results``.

The original matcher is NOT modified: production / UI flows continue to call
``run_meaning_aware_matcher`` until iteration 2 flips the default. See
``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
CD-1 and ``07_iteration_plan.md`` Iteration 1 § WS-C.

Public entry point::

    from app.services.seo.matcher_v2.api import run_matcher_v2
    result = run_matcher_v2(session, project_id=..., category_id=..., nm_id=...)
    # result.run_id, result.response, result.run_row, result.result_rows
"""

from app.services.seo.matcher_v2.api import (
    MATCHER_V2_POLICY_VERSION,
    MATCHER_V2_VERSION,
    MatcherV2Error,
    MatcherV2RunResult,
    run_matcher_v2,
)


__all__ = [
    "MATCHER_V2_POLICY_VERSION",
    "MATCHER_V2_VERSION",
    "MatcherV2Error",
    "MatcherV2RunResult",
    "run_matcher_v2",
]
