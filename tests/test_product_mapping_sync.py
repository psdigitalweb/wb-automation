from __future__ import annotations

import pytest

from app.services.product_mapping_sync import (
    get_product_mapping_diagnostics,
    reconcile_project_product_mappings,
    update_product_mapping_status,
)


class _Result:
    def __init__(self, *, scalar_value=None, rowcount: int = 0):
        self._scalar_value = scalar_value
        self.rowcount = rowcount

    def scalar(self):
        return self._scalar_value


class _Connection:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.results = [
            _Result(scalar_value=1),
            _Result(rowcount=3),
            _Result(rowcount=2),
            _Result(rowcount=1),
        ]

    def execute(self, statement, params=None):
        self.calls.append((str(statement), dict(params or {})))
        return self.results.pop(0)


def test_reconcile_builds_confirmed_and_safe_proposed_mappings() -> None:
    connection = _Connection()

    result = reconcile_project_product_mappings(
        project_id=7,
        snapshot_id=11,
        connection=connection,
    )

    assert result == {
        "status": "ok",
        "snapshot_id": 11,
        "catalog_products_upserted": 3,
        "confirmed_mappings_upserted": 2,
        "proposed_mappings_created": 1,
    }
    sql = "\n".join(statement for statement, _ in connection.calls)
    assert "catalog_identifier" in sql
    assert "mapping_status" in sql
    assert "HAVING COUNT(DISTINCT internal_catalog_product_id) = 1" in sql
    assert "marketplace_sku_rule" in sql
    assert "settings_json #>> '{product_identity,sku_normalization}'" in sql
    assert "WHEN 'strip_prefix_before_last_slash'" in sql
    assert "'exact'" in sql
    assert "project_id = 1" not in sql
    assert "regexp_replace" in sql
    assert "ON CONFLICT (marketplace_product_id) DO NOTHING" in sql


def test_diagnostics_rejects_unknown_status_before_querying() -> None:
    with pytest.raises(ValueError, match="invalid_mapping_status"):
        get_product_mapping_diagnostics(project_id=7, status="automatic")


def test_mapping_decision_rejects_proposed_as_input_status() -> None:
    with pytest.raises(ValueError, match="invalid_mapping_status"):
        update_product_mapping_status(project_id=7, mapping_id=1, status="proposed")
