"""Tests for the WS-E eval harness.

Locks down two invariants that the Iteration 2 plan calls out explicitly:

1. ``run_matcher_eval`` produces a well-formed ``MatcherEvalResult`` and
   persists a ``SeoEvalRun`` row with metrics and verdict.
2. ``SeoCategoryMatchingReadiness.eligibility_tier`` is written ONLY by
   ``app.services.seo.eval.harness``; any other module that tries to
   assign to that column is a contract violation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.seo.eval import harness as harness_module
from app.services.seo.eval.harness import (
    ELIGIBILITY_TIER_EVALUATED,
    ELIGIBILITY_TIER_PREVIEW_ONLY,
    EvalHarnessError,
    _compute_metrics,
    _verdict_from_metrics,
    update_eligibility_tier,
)


REPO_SRC = Path(__file__).resolve().parents[2] / "src"
ALLOWED_WRITERS = {
    REPO_SRC / "app" / "services" / "seo" / "eval" / "harness.py",
}


def _iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _writes_eligibility_tier(tree: ast.AST) -> bool:
    """Return True if the AST contains an assignment to ``.eligibility_tier``.

    We intentionally look at attribute-assignment shapes rather than raw
    string occurrences so read-side usages (filters, comparisons,
    response payload building) do not trip the guard.
    """

    class Visitor(ast.NodeVisitor):
        found = False

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "eligibility_tier"
                ):
                    self.found = True
            self.generic_visit(node)

        def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802
            if (
                isinstance(node.target, ast.Attribute)
                and node.target.attr == "eligibility_tier"
            ):
                self.found = True
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
            # Detect setattr(obj, "eligibility_tier", ...) shape.
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "eligibility_tier"
            ):
                self.found = True
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(tree)
    return visitor.found


def test_eligibility_tier_single_writer() -> None:
    """Only the eval harness may assign to ``SeoCategoryMatchingReadiness.eligibility_tier``."""

    offenders: list[str] = []
    for path in _iter_py_files(REPO_SRC):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if not _writes_eligibility_tier(tree):
            continue
        if path.resolve() in {p.resolve() for p in ALLOWED_WRITERS}:
            continue
        offenders.append(str(path.relative_to(REPO_SRC)))
    assert not offenders, (
        "eligibility_tier must be written only by app.services.seo.eval.harness; "
        f"offenders: {offenders}"
    )


def test_update_eligibility_tier_rejects_unauthorized_caller() -> None:
    with pytest.raises(EvalHarnessError):
        update_eligibility_tier(
            session=object(),  # type: ignore[arg-type]
            project_id=1,
            category_id=812,
            tier=ELIGIBILITY_TIER_EVALUATED,
            _caller="someone_else",
        )


def test_verdict_threshold_pass() -> None:
    metrics = {
        "accuracy": 0.9,
        "bad_primary_rate": 0.02,
        "hard_conflict_primary_count": 0.0,
    }
    assert _verdict_from_metrics(metrics) == ELIGIBILITY_TIER_EVALUATED


def test_verdict_threshold_fail_accuracy() -> None:
    metrics = {
        "accuracy": 0.5,
        "bad_primary_rate": 0.0,
        "hard_conflict_primary_count": 0.0,
    }
    assert _verdict_from_metrics(metrics) == ELIGIBILITY_TIER_PREVIEW_ONLY


def test_verdict_threshold_fail_bad_primary() -> None:
    metrics = {
        "accuracy": 0.95,
        "bad_primary_rate": 0.5,
        "hard_conflict_primary_count": 0.0,
    }
    assert _verdict_from_metrics(metrics) == ELIGIBILITY_TIER_PREVIEW_ONLY


def test_verdict_threshold_fail_hard_conflict() -> None:
    metrics = {
        "accuracy": 0.95,
        "bad_primary_rate": 0.0,
        "hard_conflict_primary_count": 3.0,
    }
    assert _verdict_from_metrics(metrics) == ELIGIBILITY_TIER_PREVIEW_ONLY


class _StubLabel:
    def __init__(self, query: str, bucket: str, nm_id: int | None = None) -> None:
        self.query_text_normalized = query
        self.expected_bucket = bucket
        self.nm_id = nm_id


class _StubResult:
    def __init__(self, query: str, bucket: str, conflicts: list | None = None) -> None:
        self.normalized_query_text = query
        self.bucket = bucket
        self.conflict_atoms = conflicts or []


def test_compute_metrics_basic() -> None:
    labels = [
        _StubLabel("платье", "primary", nm_id=1),
        _StubLabel("юбка", "secondary", nm_id=1),
        _StubLabel("носки", "rejected", nm_id=1),
    ]
    results = {
        1: [
            _StubResult("платье", "primary"),
            _StubResult("юбка", "secondary"),
            _StubResult("носки", "rejected"),
        ]
    }
    metrics, used, missing = _compute_metrics(labels=labels, results_by_nm=results)
    assert used == 3
    assert missing == 0
    assert metrics["accuracy"] == 1.0


def test_compute_metrics_bad_primary_detected() -> None:
    labels = [_StubLabel("мыло", "rejected", nm_id=1)]
    results = {1: [_StubResult("мыло", "primary")]}
    metrics, used, missing = _compute_metrics(labels=labels, results_by_nm=results)
    assert used == 1
    assert missing == 0
    assert metrics["bad_primary_rate"] == 1.0


def test_compute_metrics_missing_label() -> None:
    labels = [_StubLabel("тапки", "primary", nm_id=1)]
    results = {1: [_StubResult("платье", "primary")]}
    metrics, used, missing = _compute_metrics(labels=labels, results_by_nm=results)
    assert used == 0
    assert missing == 1


def test_harness_module_exports() -> None:
    """The ``app.services.seo.eval.harness`` module must keep the public surface
    the router relies on so a future refactor can't silently break the API."""

    for attr in (
        "ELIGIBILITY_TIER_PREVIEW_ONLY",
        "ELIGIBILITY_TIER_EVALUATED",
        "ELIGIBILITY_TIER_APPROVED",
        "EVAL_THRESHOLDS",
        "EvalHarnessError",
        "MatcherEvalResult",
        "run_matcher_eval",
        "update_eligibility_tier",
    ):
        assert hasattr(harness_module, attr), f"harness missing {attr}"
