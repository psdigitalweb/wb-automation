"""Runtime import guards for frozen SEO modules.

Iteration 1 of the SEO module rework freezes several legacy code paths
(clustering, scoring service helpers, experimental atoms) so that nothing new
depends on them. Rather than delete them (which would break migrations, tests,
and research scripts), we install a runtime check at module load time.

The guard inspects the import stack: if the caller is a production module
(e.g. ``app.routers.*``, ``app.services.seo.*`` *excluding* the allowed
prefixes below), loading the frozen module raises ``FrozenModuleImportError``.
Research scripts, tests, and migrations keep working.

See ``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
CD-5 and ``07_iteration_plan.md`` Iteration 1 § WS-F.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Tuple


class FrozenModuleImportError(ImportError):
    """Raised when a production module tries to import a frozen SEO module."""


# Modules whose import of frozen code is *allowed*. The guard checks whether
# any frame in the current import stack starts with one of these prefixes.
_DEFAULT_ALLOWED: Tuple[str, ...] = (
    "tests.",
    "scripts.",
    "alembic.",
    # Frozen modules cross-import each other internally.
    "app.services.seo.experiments.",
    "app.services.seo.clustering.",
    "app.services.seo.scoring.",
    # Diagnostics (not yet physically moved in iteration 1) may still use
    # legacy helpers; see P1 scoring move.
    "app.services.seo.diagnostics.",
    # Direct REPL / script / __main__ invocation.
    "__main__",
    "pytest",
    "_pytest",
)


def _iter_stack_module_names() -> Iterable[str]:
    frame = sys._getframe(1)
    while frame is not None:
        module = frame.f_globals.get("__name__")
        if module:
            yield module
        frame = frame.f_back


def guard_frozen_module(
    module_name: str,
    *,
    allowed_caller_prefixes: Tuple[str, ...] = (),
    env_override_var: str = "SEO_ALLOW_FROZEN_IMPORTS",
) -> None:
    """Raise ``FrozenModuleImportError`` if the importer is a production module.

    Parameters
    ----------
    module_name:
        The ``__name__`` of the frozen module invoking the guard.
    allowed_caller_prefixes:
        Additional prefixes (on top of :data:`_DEFAULT_ALLOWED`) that are
        considered safe importers. Use for tight per-module allow-lists.
    env_override_var:
        Environment variable name. When set to a truthy value, the guard is
        skipped entirely — intended only for migration / emergency use.
    """

    if os.getenv(env_override_var, "").lower() in {"1", "true", "yes"}:
        return

    allowed = _DEFAULT_ALLOWED + tuple(allowed_caller_prefixes)

    # Walk the *full* import stack and collect every caller frame that could
    # plausibly be "the importer". A frozen module load is considered safe if
    # ANY frame in that stack is an allowed caller (test / script / another
    # frozen module / explicit opt-in). It is only rejected when every
    # candidate frame is on a production path.
    #
    # Walking the whole stack matters because a frozen module is often
    # imported transitively through multiple ``importlib`` and
    # package-level ``__getattr__`` frames, and the test/script that
    # actually triggered the import sits several frames up.
    candidates: list[str] = []
    for caller in _iter_stack_module_names():
        if caller == module_name or caller == __name__:
            continue
        if caller.startswith("importlib") or caller.startswith("pkgutil"):
            continue
        # Match allowed prefix at any depth.
        if any(caller == prefix.rstrip(".") or caller.startswith(prefix) for prefix in allowed):
            return
        # Pytest imports top-level test modules with bare names like
        # ``test_foo`` when there is no ``tests/__init__.py``. Treat those as
        # test imports.
        if caller.startswith("test_") or caller.endswith("_test") or ".test_" in caller:
            return
        candidates.append(caller)

    # No allowed caller found anywhere in the stack: raise with the nearest
    # production caller for a legible error.
    if candidates:
        raise FrozenModuleImportError(
            f"Frozen SEO module '{module_name}' cannot be imported from production module "
            f"'{candidates[0]}'. If you need this in a diagnostic / migration / test context, "
            "add the caller prefix to the allow list or set SEO_ALLOW_FROZEN_IMPORTS=1 for the "
            "duration of the call."
        )

    # Empty stack or only importlib frames = unattributable, treat as safe
    # (e.g. top-level script, interactive session).


__all__ = ["FrozenModuleImportError", "guard_frozen_module"]
