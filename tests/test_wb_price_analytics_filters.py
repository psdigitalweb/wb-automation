from types import SimpleNamespace

from app import api_wb_price_discrepancies as price_api


def _filters(**overrides):
    values = {
        "q": None,
        "category_ids": [],
        "only_below_rrp": False,
        "has_wb_stock": "any",
        "has_enterprise_stock": "any",
        "has_showcase_price": "any",
        "front_snapshot_at": None,
        "sort": "showcase_price_desc",
        "page": 1,
        "page_size": 25,
    }
    values.update(overrides)
    return price_api.DiscrepancyFilters(**values)


def test_price_analytics_sort_keys_are_supported():
    assert price_api._parse_sort("wb_admin_price_desc") == "wb_admin_price_desc"
    assert price_api._sort_to_order_clause("wb_discount_desc").startswith("wb_discount_percent DESC")
    assert price_api._sort_to_order_clause("spp_desc").startswith("spp_percent DESC")


def test_showcase_availability_filter_is_applied_in_sql(monkeypatch):
    monkeypatch.setattr(
        price_api,
        "get_project_storefront_snapshot_scope",
        lambda project_id: SimpleNamespace(query_values=[101], query_type="brand"),
    )

    with_showcase_sql, _ = price_api._build_discrepancies_sql(
        3,
        _filters(has_showcase_price="true"),
    )
    without_showcase_sql, _ = price_api._build_discrepancies_sql(
        3,
        _filters(has_showcase_price="false"),
    )

    assert "front_latest.showcase_price IS NOT NULL" in with_showcase_sql
    assert "front_latest.showcase_price IS NULL" in without_showcase_sql
    assert "computed.is_below_rrp = TRUE" not in with_showcase_sql
