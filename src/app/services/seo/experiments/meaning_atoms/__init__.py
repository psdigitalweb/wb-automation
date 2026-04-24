"""Meaning atoms research/experiment package — FROZEN for production imports.

Iteration 1 of the SEO module rework relocated the production-consumed parts
of this package (``v1.py`` -> ``atoms.v1.matcher_v1``, ``schemas.py``,
``guards.py``, ``llm_extractors.py``, ``vision.py``) into
``app.services.seo.atoms.v1``. What remains here is research-only tooling
(comparison runners, reports, readiness reports, error analysis) used by
offline experiments and their tests.

Production code must not import from this package. The :func:`__getattr__`
below redirects research-script re-exports to their new home so existing
experiment CLIs keep working; any attempt to import from production code
paths is blocked at load time by
``services.seo._freeze.guard_frozen_module``.

See ``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
CD-5, CD-6.
"""

from __future__ import annotations

from app.services.seo._freeze import guard_frozen_module


guard_frozen_module(
    __name__,
    allowed_caller_prefixes=(
        "app.services.seo.experiments.",
        "app.services.seo.atoms.",  # used by back-compat shims only
        "tests.",
        "scripts.",
        "alembic.",
        # Allow direct CLI / __main__ invocations.
        "__main__",
    ),
)


__all__ = [
    "ATOMS_MATCHER_V1_VERSION",
    "extract_query_atoms",
    "extract_sku_atoms",
    "match_atoms",
    "match_atoms_v1",
    "normalize_query_atoms_v1",
    "normalize_sku_atoms_v1",
    "parse_query_atoms_response",
    "parse_sku_atoms_response",
    "run_comparison",
]


def __getattr__(name: str):
    if name == "run_comparison":
        from app.services.seo.experiments.meaning_atoms.comparison import run_comparison

        return run_comparison
    if name in {"extract_query_atoms", "extract_sku_atoms", "parse_query_atoms_response", "parse_sku_atoms_response"}:
        from app.services.seo.atoms.v1 import llm_extractors

        return getattr(llm_extractors, name)
    if name == "match_atoms":
        from app.services.seo.experiments.meaning_atoms.matcher import match_atoms

        return match_atoms
    if name in {"ATOMS_MATCHER_V1_VERSION", "match_atoms_v1", "normalize_query_atoms_v1", "normalize_sku_atoms_v1"}:
        from app.services.seo.atoms.v1 import matcher_v1 as _matcher_v1

        return getattr(_matcher_v1, name)
    raise AttributeError(name)
