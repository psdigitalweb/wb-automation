"""Keep WB SEO on the canonical, backwards-compatible product projection."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SEO_SERVICE_ROOT = REPO_ROOT / "src" / "app" / "services" / "seo"
SEO_CATEGORY_ROUTER = REPO_ROOT / "src" / "app" / "routers" / "seo_category_bootstrap.py"
DIRECT_LEGACY_PRODUCT_SQL = re.compile(r"\b(?:FROM|JOIN)\s+products\b", re.IGNORECASE)


def test_active_seo_sql_uses_wb_product_projection() -> None:
    violations: list[str] = []
    paths = [*SEO_SERVICE_ROOT.rglob("*.py"), SEO_CATEGORY_ROUTER]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for match in DIRECT_LEGACY_PRODUCT_SQL.finditer(source):
            line_number = source.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(REPO_ROOT)}:{line_number}")

    assert not violations, (
        "WB SEO must read products through v_wb_product_source so canonical-only "
        "and legacy projects share one product universe:\n" + "\n".join(violations)
    )
