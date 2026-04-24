"""CI guard: no new category-specific literals inside ``matcher_v2``.

Iteration 2 (WS-C) externalizes category-calibrated rules into
``SeoCategoryProfile`` (seeded from ``config/seo/category_profiles/812.json``).
The ``matcher_v2`` package must consume the profile; it must NOT reintroduce
the hardcoded dictionaries that live in
``app.services.seo.query_meaning_matcher.matcher`` today.

This test walks every module under ``app/services/seo/matcher_v2/`` and fails
if it finds:

1. A module-level ``dict`` or ``list`` or ``set`` literal whose elements
   include any of the seeded category-812 term strings (Russian or English).
   This catches a developer copy-pasting ``_EXPRESSIVE_GROUPS`` into
   ``matcher_v2`` to avoid the profile plumbing.
2. New ``from app.services.seo.query_meaning_matcher.matcher import ...``
   statements that pull in helpers outside an allowlist. The allowlist
   contains the iteration-1 parity helpers (``_hard_conflicts``,
   ``_bucket_for``, etc.) which still back the profile-free fallback path
   until the stages are fully ported in a later iteration.

Pattern mirrors ``tests/seo/test_frozen_imports.py``. Runs on every pytest
invocation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "src" / "app"
MATCHER_V2_ROOT = APP_ROOT / "services" / "seo" / "matcher_v2"


# Seeded category-812 terms from ``config/seo/category_profiles/812.json``.
# A match against any of these inside a ``matcher_v2`` module literal means
# someone is hardcoding category-specific vocabulary there.
SEEDED_TERM_STRINGS: frozenset[str] = frozenset(
    {
        # expressive
        "милота",
        "милая",
        "няшная",
        "уют",
        "уютная",
        "эстет",
        "эстетичная",
        "пинтерест",
        "pinterest",
        "стильный",
        # audience
        "женская",
        "мужская",
        "школьник",
        "подросток",
        "подростковый",
        # material
        "стекло",
        "стеклянная",
        "керамика",
        "керамическая",
        "фарфор",
        "фарфоровая",
        "металл",
        "металлическая",
        "пластик",
        "пластиковая",
        # conflict / product-type hints
        "термокруж",
        "термокружка",
        "beer_use_case",
    }
)


# Helpers from the legacy matcher module that ``matcher_v2`` is allowed to
# import for iteration-2 parity preservation. Any new import from
# ``query_meaning_matcher.matcher`` not in this set fails the test.
ALLOWED_LEGACY_MATCHER_HELPERS: frozenset[str] = frozenset(
    {
        # public exception types
        "CategoryBootstrapBuildingError",
        "MissingQueryMeaningLibraryError",
        "MissingSkuMeaningAnnotationError",
        # private helpers used in iteration-1 stage copies
        "_FeatureSet",
        "_apply_atoms_gate",
        "_bucket_for",
        "_frequency_boost",
        "_hard_conflicts",
        "_judgment_overrides_by_query",
        "_manual_bucket_override",
        "_overlap_score",
        "_product_type_score",
        "_query_display",
        "_query_features",
        "_ranking_by_cluster",
        "_sku_features",
        "_user_reasons",
        "_USER_BUCKET_LABELS",
    }
)


def _iter_matcher_v2_files() -> Iterable[Path]:
    for path in MATCHER_V2_ROOT.rglob("*.py"):
        # __pycache__ and migration artifacts are irrelevant.
        if "__pycache__" in path.parts:
            continue
        yield path


def _collect_string_leaves(node: ast.AST) -> list[tuple[str, int]]:
    """Return every ``str`` constant inside ``node`` with its line number."""
    leaves: list[tuple[str, int]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            leaves.append((child.value, child.lineno))
    return leaves


def test_no_category_literals_in_matcher_v2() -> None:
    """Fail if any ``matcher_v2`` module ships seeded category-812 term strings."""

    if not MATCHER_V2_ROOT.exists():  # pragma: no cover - defensive
        pytest.skip("matcher_v2 package not present in this checkout")

    violations: list[str] = []
    for path in _iter_matcher_v2_files():
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover
            violations.append(f"{path}: syntax error ({exc})")
            continue

        for node in tree.body:
            # Only flag module-level bindings: `_FOO = {...}` or `_FOO = [...]`.
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
                continue
            for text, lineno in _collect_string_leaves(value):
                lowered = text.lower()
                for seeded in SEEDED_TERM_STRINGS:
                    if seeded.lower() == lowered or seeded.lower() in lowered:
                        rel = path.relative_to(REPO_ROOT)
                        violations.append(
                            f"{rel}:{lineno}: module-level literal contains "
                            f"seeded category-812 term '{text}'. "
                            "Load the value from SeoCategoryProfile instead "
                            "(see app.services.seo.category_profile.load_active_profile)."
                        )
                        break

    if violations:
        pytest.fail(
            "matcher_v2 modules must not hardcode category-specific term "
            "literals. Externalize them into SeoCategoryProfile (WS-C).\n\n"
            + "\n".join(violations)
        )


def test_no_new_legacy_matcher_imports_in_matcher_v2() -> None:
    """Fail if any ``matcher_v2`` module imports new helpers from the legacy matcher.

    The allowlist freezes the iteration-1 surface; anything new must come
    from ``SeoCategoryProfile`` or from a dedicated helper that the profile
    loader owns.
    """

    if not MATCHER_V2_ROOT.exists():  # pragma: no cover - defensive
        pytest.skip("matcher_v2 package not present in this checkout")

    violations: list[str] = []
    for path in _iter_matcher_v2_files():
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover
            violations.append(f"{path}: syntax error ({exc})")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "app.services.seo.query_meaning_matcher.matcher":
                continue
            for alias in node.names:
                name = alias.name
                if name == "*":
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                        "star import of legacy matcher is forbidden"
                    )
                    continue
                if name not in ALLOWED_LEGACY_MATCHER_HELPERS:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                        f"new import '{name}' from legacy matcher. Consume "
                        "SeoCategoryProfile instead, or add to the allowlist "
                        "in tests/seo/test_matcher_v2_no_category_literals.py "
                        "with a written justification."
                    )

    if violations:
        pytest.fail(
            "matcher_v2 gained a new legacy-matcher import. Consume the "
            "category profile instead.\n\n" + "\n".join(violations)
        )
