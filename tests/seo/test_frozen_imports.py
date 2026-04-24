"""CI guard: no production module may import a frozen SEO module.

Iteration 1 of the SEO module rework froze three legacy code paths:

* ``app.services.seo.clustering.*`` (all modules)
* ``app.services.seo.scoring.service`` — specifically the legacy
  persistence helpers ``create_score_run`` / ``persist_query_score`` and
  the dataclasses ``ScoreComponents`` / ``PersistedScoreResult``
* ``app.services.seo.experiments.meaning_atoms.*``

Runtime guards at
``app.services.seo._freeze.guard_frozen_module`` reject unexpected
production imports, but runtime guards are opt-in (they only fire if the
frozen module actually loads at request time). This static AST walk is
the belt-and-suspenders check: if anyone adds a ``from
app.services.seo.clustering ...`` line to a router or production service,
this test fails during normal pytest runs.

See ``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
§4.1 E and ``07_iteration_plan.md`` WS-F.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "src" / "app"

# Directories under ``src/app`` whose files are themselves diagnostic /
# frozen / experimental, and are therefore allowed to import the frozen
# code paths. The walk below skips these prefixes.
ALLOWED_DIR_PREFIXES: tuple[Path, ...] = (
    APP_ROOT / "services" / "seo" / "clustering",
    APP_ROOT / "services" / "seo" / "scoring",
    APP_ROOT / "services" / "seo" / "experiments",
    APP_ROOT / "services" / "seo" / "diagnostics",
    APP_ROOT / "services" / "seo" / "_freeze.py",  # self-reference helper
)

# Individual files that are allowed because they ARE the freeze shim
# and advertise which legacy helpers they forward.
ALLOWED_FILES: tuple[Path, ...] = (
    APP_ROOT / "services" / "seo" / "__init__.py",
)


def _is_allowed(path: Path) -> bool:
    try:
        path_resolved = path.resolve()
    except OSError:
        return False
    for prefix in ALLOWED_DIR_PREFIXES:
        try:
            path_resolved.relative_to(prefix)
            return True
        except ValueError:
            continue
    for allowed in ALLOWED_FILES:
        if path_resolved == allowed.resolve():
            return True
    return False


def _iter_python_files() -> Iterable[Path]:
    for path in APP_ROOT.rglob("*.py"):
        if _is_allowed(path):
            continue
        yield path


def _is_frozen_import(module: str | None) -> str | None:
    """Return a human-readable reason if ``module`` is a frozen path, else None."""
    if not module:
        return None
    if module == "app.services.seo.clustering" or module.startswith("app.services.seo.clustering."):
        return f"frozen clustering path: {module}"
    if module == "app.services.seo.experiments.meaning_atoms" or module.startswith(
        "app.services.seo.experiments.meaning_atoms."
    ):
        return f"frozen experiments.meaning_atoms path: {module}"
    # scoring.service is only *partially* frozen — we accept imports of
    # ``config`` / ``preparation`` / ``actual`` / package root, but NOT the
    # persistence helpers from ``scoring.service``.
    if module == "app.services.seo.scoring.service":
        return f"frozen scoring.service module: {module}"
    return None


FORBIDDEN_SCORING_SYMBOLS = {
    "create_score_run",
    "persist_query_score",
    "ScoreComponents",
    "PersistedScoreResult",
}


def test_no_production_import_of_frozen_modules() -> None:
    """Fail if any production file imports a frozen SEO module."""

    violations: list[str] = []
    for path in _iter_python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover
            violations.append(f"{path}: could not read ({exc})")
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover
            violations.append(f"{path}: syntax error ({exc})")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                reason = _is_frozen_import(node.module)
                if reason is not None:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {reason}"
                    )
                    continue
                # Partial freeze of scoring.service: re-imports from the
                # package root that pull the legacy persistence helpers.
                if node.module == "app.services.seo.scoring":
                    for alias in node.names:
                        if alias.name in FORBIDDEN_SCORING_SYMBOLS:
                            violations.append(
                                f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                                f"imports frozen scoring helper '{alias.name}' via package root"
                            )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    reason = _is_frozen_import(alias.name)
                    if reason is not None:
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {reason}"
                        )

    if violations:
        message = "\n".join(violations)
        pytest.fail(
            "Production code imports frozen SEO modules. Remove the import, "
            "move the caller under an allowed diagnostic/experiments package, "
            "or adjust the freeze policy in "
            "docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md.\n\n"
            f"{message}"
        )
