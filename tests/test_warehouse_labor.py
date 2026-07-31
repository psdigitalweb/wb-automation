from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app import db_warehouse_labor


class _FakeResult:
    def __init__(self, *, one=None, all_rows=None):
        self._one = one
        self._all_rows = all_rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all_rows


class _FakeConn:
    def __init__(self):
        self.calls = []
        self.now = datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc)

    def execute(self, sql, params=None):
        self.calls.append((str(sql), params or {}))
        call_index = len(self.calls)

        if call_index == 1:
            return _FakeResult(one=None)
        if call_index == 2:
            return _FakeResult(
                one=(10, 1, date(2026, 3, 23), "wildberries", None, self.now, self.now)
            )
        if call_index in (3, 4):
            return _FakeResult()
        if call_index == 5:
            return _FakeResult(
                all_rows=[
                    (
                        10,
                        1,
                        date(2026, 3, 23),
                        "wildberries",
                        None,
                        self.now,
                        self.now,
                        20,
                        "Общий",
                        1,
                        Decimal("2000.00"),
                        "RUB",
                        self.now,
                        self.now,
                    )
                ]
            )

        raise AssertionError(f"Unexpected execute call {call_index}: {sql}")


class _FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _FakeBegin(self.conn)


def test_upsert_warehouse_labor_day_fetches_created_day_inside_transaction(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(db_warehouse_labor, "engine", _FakeEngine(conn))

    day = db_warehouse_labor.upsert_warehouse_labor_day(
        project_id=1,
        data={
            "work_date": date(2026, 3, 23),
            "marketplace_code": "wildberries",
            "notes": None,
            "rates": [
                {
                    "rate_name": "Общий",
                    "employees_count": 1,
                    "rate_amount": Decimal("2000.00"),
                }
            ],
        },
    )

    assert day["id"] == 10
    assert day["rates"][0]["rate_name"] == "Общий"
    assert day["total_amount"] == Decimal("2000.00")
    assert len(conn.calls) == 5
    assert "LEFT JOIN warehouse_labor_day_rates" in conn.calls[-1][0]
