from datetime import date
from unittest.mock import MagicMock, patch

from app.db_wb_sales_trends import get_sales_trends


def test_get_sales_trends_groups_points_and_converts_numeric_values():
    rows = [
        {
            "nm_id": 101,
            "vendor_code": "SKU-101",
            "title": "Product 101",
            "stat_date": date(2026, 7, 1),
            "orders": 2,
            "revenue": 1500,
            "impressions": 100,
            "card_clicks": 14,
            "ctr_percent": 14,
            "moving_average_orders": 1.25,
            "moving_average_revenue": 900.5,
            "moving_average_impressions": 80,
            "moving_average_card_clicks": 10,
            "moving_average_ctr_percent": 12.5,
        },
        {
            "nm_id": 101,
            "vendor_code": "SKU-101",
            "title": "Product 101",
            "stat_date": date(2026, 7, 2),
            "orders": 0,
            "revenue": 0,
            "impressions": 0,
            "card_clicks": 0,
            "ctr_percent": None,
            "moving_average_orders": 1,
            "moving_average_revenue": 750,
            "moving_average_impressions": 50,
            "moving_average_card_clicks": 7,
            "moving_average_ctr_percent": 14,
        },
    ]

    with patch("app.db_wb_sales_trends.engine") as mock_engine:
        connection = MagicMock()
        connection.execute.return_value.mappings.return_value.all.return_value = rows
        mock_engine.connect.return_value.__enter__.return_value = connection

        result = get_sales_trends(
            project_id=7,
            nm_ids=[101],
            period_from=date(2026, 7, 1),
            period_to=date(2026, 7, 2),
            window_days=7,
        )

    assert result == [
        {
            "nm_id": 101,
            "vendor_code": "SKU-101",
            "title": "Product 101",
            "points": [
                {
                    "date": "2026-07-01",
                    "orders": 2,
                    "revenue": 1500.0,
                    "impressions": 100,
                    "card_clicks": 14,
                    "ctr_percent": 14.0,
                    "moving_average_orders": 1.25,
                    "moving_average_revenue": 900.5,
                    "moving_average_impressions": 80.0,
                    "moving_average_card_clicks": 10.0,
                    "moving_average_ctr_percent": 12.5,
                },
                {
                    "date": "2026-07-02",
                    "orders": 0,
                    "revenue": 0.0,
                    "impressions": 0,
                    "card_clicks": 0,
                    "ctr_percent": None,
                    "moving_average_orders": 1.0,
                    "moving_average_revenue": 750.0,
                    "moving_average_impressions": 50.0,
                    "moving_average_card_clicks": 7.0,
                    "moving_average_ctr_percent": 14.0,
                },
            ],
        }
    ]
    params = connection.execute.call_args.args[1]
    assert params["window_preceding"] == 6
    assert params["nm_ids"] == [101]
    sql = str(connection.execute.call_args.args[0])
    assert "wb_funnel_ctr_daily" in sql
    assert "SUM(card_clicks)" in sql
    assert "SUM(impressions)" in sql
    assert "AVG(ctr_percent)" not in sql


def test_get_sales_trends_deduplicates_ids_and_skips_query_for_empty_selection():
    with patch("app.db_wb_sales_trends.engine") as mock_engine:
        assert get_sales_trends(
            project_id=1,
            nm_ids=[],
            period_from=date(2026, 7, 1),
            period_to=date(2026, 7, 2),
            window_days=3,
        ) == []
        mock_engine.connect.assert_not_called()

    with patch("app.db_wb_sales_trends.engine") as mock_engine:
        connection = MagicMock()
        connection.execute.return_value.mappings.return_value.all.return_value = []
        mock_engine.connect.return_value.__enter__.return_value = connection
        get_sales_trends(
            project_id=1,
            nm_ids=[101, 101, 102],
            period_from=date(2026, 7, 1),
            period_to=date(2026, 7, 2),
            window_days=3,
        )
        assert connection.execute.call_args.args[1]["nm_ids"] == [101, 102]
