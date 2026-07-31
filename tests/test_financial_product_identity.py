from datetime import date
from unittest.mock import MagicMock

from app import db_additional_costs, db_wb_financial_events


def _transaction_engine(row: dict | None = None) -> tuple[MagicMock, MagicMock]:
    mocked_engine = MagicMock()
    connection = mocked_engine.begin.return_value.__enter__.return_value
    result = connection.execute.return_value
    result.mappings.return_value.first.return_value = row
    return mocked_engine, connection


def test_additional_product_cost_dual_writes_marketplace_product_id(monkeypatch):
    mocked_engine, connection = _transaction_engine({"id": 1})
    monkeypatch.setattr(db_additional_costs, "engine", mocked_engine)
    monkeypatch.setattr(
        db_additional_costs,
        "resolve_marketplace_product_id",
        lambda **kwargs: 987,
    )

    db_additional_costs.create_additional_cost_entry(
        4,
        {
            "scope": "product",
            "marketplace_code": "wildberries",
            "nm_id": 123,
            "internal_sku": "SKU-123",
            "period_from": date(2026, 7, 1),
            "period_to": date(2026, 7, 31),
            "amount": 100,
            "category": "marketing",
        },
    )

    params = connection.execute.call_args.args[1]
    assert params["marketplace_product_id"] == 987
    assert params["marketplace_item_id"] == "123"


def test_ozon_product_cost_does_not_require_internal_catalog(monkeypatch):
    mocked_engine, connection = _transaction_engine({"id": 2})
    monkeypatch.setattr(db_additional_costs, "engine", mocked_engine)
    resolved = []

    def resolve(**kwargs):
        resolved.append(kwargs)
        return 654

    monkeypatch.setattr(db_additional_costs, "resolve_marketplace_product_id", resolve)
    db_additional_costs.create_additional_cost_entry(
        4,
        {
            "scope": "product",
            "marketplace_code": "ozon",
            "marketplace_item_id": "OZON-ABC-42",
            "period_from": date(2026, 7, 1),
            "period_to": date(2026, 7, 31),
            "amount": 100,
            "category": "marketing",
        },
    )

    assert resolved[0]["marketplace_code"] == "ozon"
    assert resolved[0]["marketplace_item_id"] == "OZON-ABC-42"
    params = connection.execute.call_args.args[1]
    assert params["marketplace_product_id"] == 654
    assert params["internal_sku"] is None


def test_legacy_nm_id_update_refreshes_neutral_item_id(monkeypatch):
    mocked_engine, connection = _transaction_engine({"id": 3})
    monkeypatch.setattr(db_additional_costs, "engine", mocked_engine)
    monkeypatch.setattr(
        db_additional_costs,
        "get_additional_cost_entry",
        lambda *_args: {
            "id": 3,
            "scope": "product",
            "marketplace_code": "wildberries",
            "nm_id": 123,
            "marketplace_item_id": "123",
            "marketplace_product_id": 987,
            "internal_sku": "SKU-123",
        },
    )
    resolved = []

    def resolve(**kwargs):
        resolved.append(kwargs)
        return 988

    monkeypatch.setattr(db_additional_costs, "resolve_marketplace_product_id", resolve)
    db_additional_costs.update_additional_cost_entry(4, 3, {"nm_id": 124})

    assert resolved[0]["marketplace_item_id"] == "124"
    params = connection.execute.call_args.args[1]
    assert params["marketplace_item_id"] == "124"
    assert params["marketplace_product_id"] == 988


def test_financial_event_upsert_persists_marketplace_product_id(monkeypatch):
    mocked_engine, connection = _transaction_engine()
    monkeypatch.setattr(db_wb_financial_events, "engine", mocked_engine)

    db_wb_financial_events.upsert_event(
        project_id=4,
        report_id=10,
        line_id=20,
        line_uid_surrogate=None,
        event_date=date(2026, 7, 15),
        event_date_quality="exact",
        period_from=date(2026, 7, 1),
        period_to=date(2026, 7, 31),
        nm_id=123,
        vendor_code="SKU-123",
        internal_sku="SKU-123",
        event_type="sale",
        scope="product",
        amount=100,
        currency="RUB",
        source_field="retail_amount",
        payload_hash="hash",
        marketplace_product_id=987,
    )

    sql, params = connection.execute.call_args.args
    assert "marketplace_product_id" in str(sql)
    assert params["marketplace_product_id"] == 987
