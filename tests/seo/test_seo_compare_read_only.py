"""Static guard: compare layer must be read-only.

The Iteration 2 contract forbids the compare layer from importing any
service function that mutates matcher trace, generation content, eval runs,
or candidate query-set state. Human verdicts live in ``seo_compare_verdicts``
and are written directly from the router; no mutating service indirection
is allowed.

This test is intentionally brittle: adding a new mutating import to
``app/routers/seo_compare.py`` or ``app/services/seo/compare.py`` without
updating the allowlist will fail CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_SRC = Path(__file__).resolve().parents[2] / "src"
COMPARE_FILES = [
    REPO_SRC / "app" / "routers" / "seo_compare.py",
    REPO_SRC / "app" / "services" / "seo" / "compare.py",
]


FORBIDDEN_SYMBOLS = {
    # Matcher trace writers
    "run_matcher_v2",
    "create_matcher_run",
    "finalize_matcher_run",
    "persist_matcher_results",
    # Candidate selection writers
    "project_matcher_run_into_query_set",
    "transition_approval_state",
    "mark_query_set_validated",
    "update_query_selection",
    "run_query_selection",
    # Generation writers
    "run_seo_generation",
    "recalculate_latest_seo_relevance_v2",
    "promote_content_version",
    "record_human_review",
    # Eval writers
    "run_matcher_eval",
    "update_eligibility_tier",
}

FORBIDDEN_MODULES = {
    "app.services.seo.matcher_v2",
    "app.services.seo.matcher_v2.api",
    "app.services.seo.matcher_v2.persistence",
    "app.services.seo.generation.service",
    "app.services.seo.generation.promotion",
    "app.services.seo.eval",
    "app.services.seo.eval.harness",
    "app.services.seo.query_set_candidate",
    "app.services.seo.query_meaning_matcher.matcher",
}


def _collect_imports(tree: ast.AST) -> tuple[set[str], set[str]]:
    imported_names: set[str] = set()
    imported_modules: set[str] = set()

    class V(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
            for alias in node.names:
                imported_modules.add(alias.name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
            mod = node.module or ""
            imported_modules.add(mod)
            for alias in node.names:
                imported_names.add(alias.name)

    V().visit(tree)
    return imported_names, imported_modules


@pytest.mark.parametrize("path", COMPARE_FILES, ids=lambda p: p.name)
def test_compare_layer_has_no_mutating_imports(path: Path) -> None:
    assert path.exists(), f"compare file missing: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names, modules = _collect_imports(tree)

    bad_names = names & FORBIDDEN_SYMBOLS
    assert not bad_names, (
        f"{path.name} imports forbidden mutating symbols: {bad_names}"
    )
    bad_modules = {m for m in modules if m in FORBIDDEN_MODULES}
    assert not bad_modules, (
        f"{path.name} imports forbidden mutating modules: {bad_modules}"
    )


def test_compare_layer_does_not_write_matcher_result_columns() -> None:
    """Defensive AST walk: no assignments to attributes named after
    matcher/content mutable columns in the compare modules."""

    forbidden_attrs = {
        "bucket",
        "score",
        "eligibility_verdict",
        "content_kind",
        "approval_state",
        "trust_state",
        "publishable",
        "eligibility_tier",
    }
    offenders: list[tuple[str, str]] = []
    for path in COMPARE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr in forbidden_attrs
                    ):
                        offenders.append((path.name, target.attr))
            if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Attribute):
                if node.target.attr in forbidden_attrs:
                    offenders.append((path.name, node.target.attr))
    assert not offenders, (
        f"compare layer must not assign to mutating attributes; offenders: {offenders}"
    )
