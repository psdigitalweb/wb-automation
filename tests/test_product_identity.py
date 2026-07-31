from __future__ import annotations

import pytest

from app.services.product_identity import (
    MarketplaceProductIdentityConflictError,
    WB_PRODUCT_SOURCE_CTES,
    resolve_marketplace_product,
    resolve_marketplace_product_id,
    resolve_marketplace_product_ids,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _Result(self.rows)


def _identity_row(product_id: int = 42):
    return {
        "marketplace_product_id": product_id,
        "project_id": 7,
        "project_marketplace_id": 11,
        "marketplace_code": "wildberries",
        "marketplace_item_id": "123456",
        "marketplace_sku": "SKU-1",
    }


def test_resolves_external_id_to_project_scoped_internal_identity():
    connection = _Connection([_identity_row()])

    identity = resolve_marketplace_product(
        project_id=7,
        marketplace_code=" Wildberries ",
        marketplace_item_id=" 123456 ",
        connection=connection,
    )

    assert identity is not None
    assert identity.marketplace_product_id == 42
    assert identity.marketplace_item_id == "123456"
    _, params = connection.calls[0]
    assert params == {
        "project_id": 7,
        "marketplace_code": "wildberries",
        "marketplace_item_id": "123456",
    }


def test_returns_none_without_internal_catalog_dependency():
    connection = _Connection([])

    assert resolve_marketplace_product_id(
        project_id=7,
        marketplace_code="ozon",
        marketplace_item_id="OZ-9",
        connection=connection,
    ) is None
    assert "internal_catalog" not in connection.calls[0][0]


def test_wb_compatibility_source_prefers_canonical_rows_and_keeps_fallback():
    assert "FROM marketplace_products mp" in WB_PRODUCT_SOURCE_CTES
    assert "legacy_product_fallback AS" in WB_PRODUCT_SOURCE_CTES
    assert "NULL::bigint AS marketplace_product_id" in WB_PRODUCT_SOURCE_CTES
    assert "internal_catalog" not in WB_PRODUCT_SOURCE_CTES


def test_rejects_ambiguous_identity():
    connection = _Connection([_identity_row(42), _identity_row(43)])

    with pytest.raises(MarketplaceProductIdentityConflictError):
        resolve_marketplace_product_id(
            project_id=7,
            marketplace_code="wildberries",
            marketplace_item_id=123456,
            connection=connection,
        )


def test_bulk_resolver_normalizes_ids_and_returns_internal_ids():
    connection = _Connection(
        [
            {"marketplace_product_id": 42, "marketplace_item_id": "123456"},
            {"marketplace_product_id": 43, "marketplace_item_id": "OZ-9"},
        ]
    )

    result = resolve_marketplace_product_ids(
        project_id=7,
        marketplace_code=" OZON ",
        marketplace_item_ids=[" 123456 ", "OZ-9", "OZ-9", None],
        connection=connection,
    )

    assert result == {"123456": 42, "OZ-9": 43}
    _, params = connection.calls[0]
    assert params["marketplace_code"] == "ozon"
    assert params["marketplace_item_ids"] == ["123456", "OZ-9"]


@pytest.mark.parametrize("field,value", [("marketplace_code", " "), ("marketplace_item_id", "")])
def test_rejects_blank_identifiers(field, value):
    kwargs = {
        "project_id": 7,
        "marketplace_code": "wildberries",
        "marketplace_item_id": "123456",
        "connection": _Connection([]),
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        resolve_marketplace_product_id(**kwargs)
