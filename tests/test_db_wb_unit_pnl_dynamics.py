from datetime import date
from unittest.mock import MagicMock

from app.db_wb_unit_pnl import get_wb_unit_pnl_monthly_dynamics


def test_monthly_dynamics_converts_rows_and_uses_report_line_formulas():
    rows = [
        {
            "month": date(2026, 4, 1),
            "rows_total": 120,
            "sale": 100000,
            "total_to_pay": 61000.5,
            "commission_and_related": 24000,
            "logistics_cost": 12000,
            "storage_cost": 2000,
            "acceptance_cost": 500,
        },
        {
            "month": date(2026, 5, 1),
            "rows_total": 0,
            "sale": 0,
            "total_to_pay": 0,
            "commission_and_related": 0,
            "logistics_cost": 0,
            "storage_cost": 0,
            "acceptance_cost": 0,
        },
    ]
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.all.return_value = rows

    result = get_wb_unit_pnl_monthly_dynamics(
        connection,
        7,
        rr_dt_from=date(2026, 4, 15),
        rr_dt_to=date(2026, 5, 20),
    )

    assert result == rows
    sql = str(connection.execute.call_args.args[0])
    params = connection.execute.call_args.args[1]
    assert "generate_series" in sql
    assert "GROUP BY month" in sql
    assert "sale, 0) - COALESCE(a.transfer_for_goods" in sql
    assert "ppvz_for_pay" in sql
    assert "payload->>'nm_id'" in sql
    assert params == {
        "project_id": 7,
        "rr_dt_from": date(2026, 4, 15),
        "rr_dt_to": date(2026, 5, 20),
    }
