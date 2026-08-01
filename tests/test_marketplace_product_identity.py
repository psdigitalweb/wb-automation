from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app import ingest_products
from app.db_internal_data import (
    InternalIdentifierConflictError,
    _build_identifier_rows,
)
from app.services import marketplace_product_backfill as backfill
from app.services import marketplace_product_dual_write as dual_write


def _catalog_row(
    internal_sku: str,
    *,
    marketplace_code: str = "wildberries",
    marketplace_item_id: str | None = None,
    marketplace_sku: str | None = None,
) -> dict:
    return {
        "internal_sku": internal_sku,
        "identifiers": [
            {
                "marketplace_code": marketplace_code,
                "marketplace_item_id": marketplace_item_id,
                "marketplace_sku": marketplace_sku,
                "extra_identifiers": None,
            }
        ],
    }


def test_identifier_rows_are_normalized_and_exact_duplicates_are_deduplicated():
    row = _catalog_row(
        "SKU-1",
        marketplace_code=" Wildberries ",
        marketplace_item_id=" 123 ",
        marketplace_sku=" seller-1 ",
    )

    result = _build_identifier_rows(
        project_id=7,
        snapshot_id=11,
        rows=[row, row],
        internal_product_ids={"SKU-1": 91},
    )

    assert result == [
        {
            "project_id": 7,
            "snapshot_id": 11,
            "internal_product_id": 91,
            "marketplace_code": "wildberries",
            "marketplace_sku": "seller-1",
            "marketplace_item_id": "123",
            "extra_identifiers": None,
        }
    ]


@pytest.mark.parametrize(
    ("first", "second", "identifier_label"),
    [
        (
            _catalog_row("SKU-1", marketplace_item_id="123"),
            _catalog_row("SKU-2", marketplace_item_id="123"),
            "marketplace_item_id",
        ),
        (
            _catalog_row("SKU-1", marketplace_sku="seller-1"),
            _catalog_row("SKU-2", marketplace_sku="seller-1"),
            "marketplace_sku",
        ),
    ],
)
def test_identifier_rows_reject_ambiguous_marketplace_mapping(first, second, identifier_label):
    with pytest.raises(InternalIdentifierConflictError) as error:
        _build_identifier_rows(
            project_id=7,
            snapshot_id=11,
            rows=[first, second],
            internal_product_ids={"SKU-1": 91, "SKU-2": 92},
        )

    assert identifier_label in str(error.value)
    assert "SKU-1" in str(error.value)
    assert "SKU-2" in str(error.value)


def test_identifier_rows_reject_empty_identifier():
    with pytest.raises(InternalIdentifierConflictError, match="empty"):
        _build_identifier_rows(
            project_id=7,
            snapshot_id=11,
            rows=[_catalog_row("SKU-1")],
            internal_product_ids={"SKU-1": 91},
        )


def test_identifier_rows_reject_same_item_with_conflicting_seller_sku():
    with pytest.raises(InternalIdentifierConflictError, match="marketplace_item_id"):
        _build_identifier_rows(
            project_id=7,
            snapshot_id=11,
            rows=[
                _catalog_row("SKU-1", marketplace_item_id="123", marketplace_sku="seller-1"),
                _catalog_row("SKU-1", marketplace_item_id="123", marketplace_sku="seller-2"),
            ],
            internal_product_ids={"SKU-1": 91},
        )


class _MappingsResult:
    def __init__(self, row: dict):
        self._row = row

    def mappings(self):
        return self

    def one(self):
        return self._row


class _Connection:
    def __init__(self, scope: dict):
        self.scope = scope
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if len(self.calls) == 1:
            return _MappingsResult(self.scope)
        return SimpleNamespace(rowcount=self.scope["eligible_products"])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _Engine:
    def __init__(self, connection: _Connection):
        self.connection = connection

    def connect(self):
        return self.connection

    def begin(self):
        return self.connection


def test_wb_backfill_defaults_to_read_only_dry_run(monkeypatch):
    connection = _Connection(
        {
            "legacy_products": 10,
            "eligible_products": 8,
            "skipped_without_connection": 2,
            "skipped_ambiguous_connection": 0,
            "existing_marketplace_products": 3,
        }
    )
    monkeypatch.setattr(backfill, "engine", _Engine(connection))

    result = backfill.backfill_wildberries_marketplace_products(project_id=4)

    assert result["dry_run"] is True
    assert result["eligible_products"] == 8
    assert result["skipped_without_connection"] == 2
    assert result["skipped_ambiguous_connection"] == 0
    assert result["rows_upserted"] == 0
    assert len(connection.calls) == 1
    assert connection.calls[0][1] == {"project_id": 4}


def test_wb_backfill_apply_is_idempotent_upsert(monkeypatch):
    connection = _Connection(
        {
            "legacy_products": 10,
            "eligible_products": 10,
            "skipped_without_connection": 0,
            "skipped_ambiguous_connection": 0,
            "existing_marketplace_products": 4,
        }
    )
    monkeypatch.setattr(backfill, "engine", _Engine(connection))

    result = backfill.backfill_wildberries_marketplace_products(dry_run=False)

    assert result["rows_upserted"] == 10
    assert len(connection.calls) == 2
    upsert_sql = connection.calls[1][0]
    assert "ON CONFLICT (project_marketplace_id, marketplace_item_id)" in upsert_sql
    assert "JOIN marketplaces" in upsert_sql
    assert "m.code = 'wildberries'" in upsert_sql


def test_dual_write_is_disabled_by_default_flag(monkeypatch):
    monkeypatch.setattr(dual_write.settings, "MARKETPLACE_PRODUCTS_DUAL_WRITE_ENABLED", False)
    monkeypatch.setattr(
        dual_write,
        "mirror_wb_products",
        lambda **_kwargs: pytest.fail("disabled mirror must not write"),
    )

    result = dual_write.mirror_wb_products_best_effort(
        project_id=1,
        rows=[{"nm_id": 123}],
    )

    assert result == {"status": "disabled", "rows_requested": 0, "rows_upserted": 0}


def test_wb_product_identity_does_not_depend_on_supplier_directory_id():
    """Different supplier aliases must not split one WB nmId into two products."""

    assert dual_write._unique_nm_ids(
        [
            {"nm_id": 101, "supplier_id": 17},
            {"nm_id": 101, "supplier_id": 999_017},
        ]
    ) == [101]


def test_dual_write_failure_does_not_escape_to_legacy_ingest(monkeypatch):
    monkeypatch.setattr(dual_write.settings, "MARKETPLACE_PRODUCTS_DUAL_WRITE_ENABLED", True)

    def fail_mirror(**_kwargs):
        raise RuntimeError("new table unavailable")

    monkeypatch.setattr(dual_write, "mirror_wb_products", fail_mirror)

    result = dual_write.mirror_wb_products_best_effort(
        project_id=1,
        rows=[{"nm_id": 123}],
    )

    assert result == {"status": "failed", "rows_requested": 1, "rows_upserted": 0}


class _DualWriteConnection:
    def __init__(self, *, connection_count: int, connection_id: int | None):
        self.connection_count = connection_count
        self.connection_id = connection_id
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if len(self.calls) == 1:
            return _MappingsResult(
                {
                    "connection_count": self.connection_count,
                    "connection_id": self.connection_id,
                }
            )
        if "nm_ids" in params:
            return SimpleNamespace(rowcount=len(params["nm_ids"]))
        return SimpleNamespace(rowcount=0)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_dual_write_upserts_unique_nm_ids_for_single_wb_connection(monkeypatch):
    connection = _DualWriteConnection(connection_count=1, connection_id=15)
    monkeypatch.setattr(dual_write, "engine", _Engine(connection))

    result = dual_write.mirror_wb_products(
        project_id=4,
        rows=[{"nm_id": 101}, {"nm_id": 101}, {"nm_id": 102}],
    )

    assert result == {
        "status": "ok",
        "rows_requested": 2,
        "rows_upserted": 2,
        "connection_count": 1,
    }
    assert len(connection.calls) == 3
    assert connection.calls[1][1] == {
        "project_id": 4,
        "connection_id": 15,
        "nm_ids": [101, 102],
    }
    assert "ON CONFLICT (project_marketplace_id, marketplace_item_id)" in connection.calls[1][0]
    assert "UPDATE wb_feedback_snapshots" in connection.calls[2][0]
    assert "UPDATE wb_product_content_versions" in connection.calls[2][0]
    assert connection.calls[2][1]["marketplace_item_ids"] == ["101", "102"]


def test_dual_write_skips_project_without_wb_connection(monkeypatch):
    connection = _DualWriteConnection(connection_count=0, connection_id=None)
    monkeypatch.setattr(dual_write, "engine", _Engine(connection))

    result = dual_write.mirror_wb_products(project_id=4, rows=[{"nm_id": 101}])

    assert result["status"] == "skipped_without_connection"
    assert result["rows_upserted"] == 0
    assert len(connection.calls) == 1


def test_wb_ingest_mirrors_only_after_legacy_upsert(monkeypatch):
    events: list[str] = []

    class _AsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    async def fake_fetch_page(*_args, **_kwargs):
        return ([{"nmID": 123, "vendorCode": "SKU-123", "title": "Product"}], None, 1)

    def fake_upsert(rows, project_id, **_kwargs):
        events.append("legacy")
        assert project_id == 7
        assert rows[0]["nm_id"] == 123
        return {"inserted": 1, "updated": 0}

    def fake_mirror(*, project_id, rows):
        events.append("mirror")
        assert project_id == 7
        assert rows[0]["nm_id"] == 123
        return {"status": "ok", "rows_requested": 1, "rows_upserted": 1}

    monkeypatch.setattr(ingest_products, "ensure_schema", lambda: None)
    monkeypatch.setattr(ingest_products, "get_wb_api_token_for_project", lambda _project_id: "test")
    monkeypatch.setattr(ingest_products.httpx, "AsyncClient", lambda **_kwargs: _AsyncClient())
    monkeypatch.setattr(ingest_products, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(ingest_products, "_get_existing_nm_ids", lambda *_args: set())
    monkeypatch.setattr(ingest_products, "upsert_products", fake_upsert)
    monkeypatch.setattr(ingest_products, "mirror_wb_products_best_effort", fake_mirror)
    monkeypatch.setattr(
        "app.services.wb_product_content.history.history_enabled_for_project",
        lambda _project_id: False,
    )

    result = asyncio.run(ingest_products.ingest(project_id=7, loop_delay_s=0))

    assert result["ok"] is True
    assert events == ["legacy", "mirror"]
