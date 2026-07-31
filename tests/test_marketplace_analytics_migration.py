from __future__ import annotations

import importlib.util
from pathlib import Path


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260731_marketplace_analytics_links.py"
)


def _migration_sql(monkeypatch) -> str:
    spec = importlib.util.spec_from_file_location("marketplace_analytics_links", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    statements: list[str] = []
    monkeypatch.setattr(migration.op, "add_column", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(migration.op, "create_foreign_key", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(migration.op, "execute", lambda statement: statements.append(str(statement)))

    migration.upgrade()
    return statements[-1]


def test_product_source_fallback_uses_view_column_order(monkeypatch):
    sql = _migration_sql(monkeypatch)

    assert "SELECT p.*" not in sql
    fallback = sql.split("UNION ALL", maxsplit=1)[1]
    expected_columns = (
        "p.id",
        "p.nm_id",
        "p.vendor_code",
        "p.category",
        "p.title",
        "p.brand",
        "p.subject_name",
        "p.price_u",
        "p.sale_price_u",
        "p.rating",
        "p.feedbacks",
        "p.sizes",
        "p.colors",
        "p.pics",
        "p.raw",
        "p.updated_at",
        "p.first_seen_at",
        "p.subject_id",
        "p.description",
        "p.dimensions",
        "p.characteristics",
        "p.created_at_api",
        "p.need_kiz",
        "p.project_id",
        "p.vendor_code_norm",
        "p.content_hash",
        "p.content_version",
        "p.content_changed_at",
        "p.content_last_seen_at",
        "p.wb_content_updated_at",
        "p.main_photo_asset_hash",
        "NULL::bigint AS marketplace_product_id",
    )

    positions = [fallback.index(column) for column in expected_columns]
    assert positions == sorted(positions)
