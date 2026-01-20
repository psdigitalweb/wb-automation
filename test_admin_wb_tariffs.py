from fastapi.testclient import TestClient
from fastapi import HTTPException, status
from sqlalchemy import text

from app.main import app
from app.deps import get_current_superuser
from app.db import engine


client = TestClient(app)


def test_wb_tariffs_ingest_requires_admin():
    """Non-admin (or failed superuser check) should receive 403 on ingest endpoint."""

    def fake_not_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    app.dependency_overrides[get_current_superuser] = fake_not_admin

    resp = client.post(
        "/api/v1/admin/marketplaces/wildberries/tariffs/ingest",
        json={"days_ahead": 10},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    app.dependency_overrides.clear()


def test_wb_tariffs_ingest_admin_starts_task(monkeypatch):
    """Admin should get 202 and Celery task.delay should be called with correct days_ahead."""
    from app.tasks import wb_tariffs

    calls = {}

    class DummyResult:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    def fake_delay(days_ahead: int):
        calls["called"] = True
        calls["days_ahead"] = days_ahead
        return DummyResult("test-task-id")

    monkeypatch.setattr(wb_tariffs.ingest_wb_tariffs_all_task, "delay", fake_delay)

    def fake_admin():
        return {
            "id": 1,
            "username": "admin",
            "email": "admin@example.com",
            "is_superuser": True,
            "is_active": True,
        }

    app.dependency_overrides[get_current_superuser] = fake_admin

    resp = client.post(
        "/api/v1/admin/marketplaces/wildberries/tariffs/ingest",
        json={"days_ahead": 5},
    )

    assert resp.status_code == status.HTTP_202_ACCEPTED
    body = resp.json()
    assert body["status"] == "started"
    assert body["days_ahead"] == 5
    assert body["task"] == "ingest_wb_tariffs_all"

    assert calls.get("called") is True
    assert calls.get("days_ahead") == 5

    app.dependency_overrides.clear()


def test_wb_tariffs_status_empty_table():
    """When marketplace_api_snapshots is empty, status endpoint returns 200 with nulls."""

    def fake_admin():
        return {
            "id": 1,
            "username": "admin",
            "email": "admin@example.com",
            "is_superuser": True,
            "is_active": True,
        }

    app.dependency_overrides[get_current_superuser] = fake_admin

    # Ensure table is empty (if it exists)
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM marketplace_api_snapshots"))
    except Exception:
        # If table doesn't exist, we still expect the endpoint to handle it gracefully
        pass

    resp = client.get("/api/v1/admin/marketplaces/wildberries/tariffs/status")
    assert resp.status_code == status.HTTP_200_OK

    body = resp.json()
    assert body["marketplace_code"] == "wildberries"
    assert body["data_domain"] == "tariffs"
    assert body["latest_fetched_at"] is None

    types = body.get("types", {})
    for t in ["commission", "acceptance_coefficients", "box", "pallet", "return"]:
        assert t in types
        assert types[t]["latest_fetched_at"] is None
        assert types[t]["latest_as_of_date"] is None
        # locale may be null for all in empty case

    app.dependency_overrides.clear()

