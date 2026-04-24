from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, Table, create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from app.db import Base
from app.models import SeoCategoryBootstrapRun, SeoCategoryMatchingReadiness, SeoQueryBatch
from app import deps
from app.routers import seo_query_import as seo_query_import_router


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def _build_client(tmp_path: Path) -> tuple[TestClient, sessionmaker]:
    _ensure_projects_stub()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    with TestingSessionLocal.begin() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))

    app = FastAPI()
    app.include_router(seo_query_import_router.router)
    app.dependency_overrides[deps.require_project_admin] = lambda: {
        "project_id": 1,
        "user_id": 1,
        "role": "owner",
    }
    app.dependency_overrides[seo_query_import_router.require_project_admin] = lambda: {
        "project_id": 1,
        "user_id": 1,
        "role": "owner",
    }

    seo_query_import_router.SessionLocal = TestingSessionLocal
    seo_query_import_router.SEO_QUERY_IMPORT_TMP_DIR = str(tmp_path / "seo-import-tmp")
    client = TestClient(app)
    return client, TestingSessionLocal


def test_import_endpoint_returns_batch_detail_and_normalized_preview(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    csv_bytes = (
        "Запрос;Частота\n"
        " Платье, красное ;10\n"
        "платье красное;5\n"
        "\"\";7\n"
        "Ёлка;2\n"
        "елка;3\n"
    ).encode("utf-8")
    response = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777", "limit": "1", "offset": "0"},
        files={"file": ("queries.csv", io.BytesIO(csv_bytes), "text/csv")},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["batch"]["project_id"] == 1
    assert payload["batch"]["category_id"] == 777
    assert payload["diagnostics"]["raw_rows_imported"] == 4
    assert payload["diagnostics"]["raw_rows_skipped"] == 1
    assert payload["normalized_queries"]["limit"] == 1
    assert payload["normalized_queries"]["offset"] == 0
    assert payload["normalized_queries"]["total"] == 2
    assert isinstance(payload["bootstrap_run_id"], int)
    assert payload["readiness_status"] in {"building", "ready_with_fallback", "ready_for_matching", "failed"}
    assert payload["normalized_queries"]["items"][0]["raw_query_example"] in {"Платье, красное", "платье красное"}
    assert isinstance(payload["normalized_queries"]["items"][0]["frequency_total"], str)
    assert payload["suspicious_rows_preview"][0]["reason"] == "empty_or_whitespace_query"

    with SessionLocal() as session:
        batch = session.query(SeoQueryBatch).one()
        bootstrap_run = session.query(SeoCategoryBootstrapRun).one()
        readiness = session.query(SeoCategoryMatchingReadiness).one()
        assert bootstrap_run.category_id == 777
        assert readiness.latest_run_id == bootstrap_run.id
        assert batch.meta["suspicious_rows_preview"][0]["reason"] == "empty_or_whitespace_query"
        normalized = batch.normalized_row_count
        assert normalized == 2

        first_row = session.execute(
            Base.metadata.tables["seo_queries_normalized"].select().limit(1)
        ).mappings().first()
        assert isinstance(first_row["frequency_total"], Decimal)


def test_import_endpoint_deletes_temp_file_on_success(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    response = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("queries.csv", io.BytesIO(b"query\nalpha\n"), "text/csv")},
    )

    assert response.status_code == 201, response.text
    temp_dir = Path(seo_query_import_router.SEO_QUERY_IMPORT_TMP_DIR)
    remaining = list(temp_dir.iterdir()) if temp_dir.exists() else []
    assert remaining == []


def test_import_endpoint_deletes_temp_file_on_failure(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    response = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("queries.csv", io.BytesIO(b"name;count\nabc;1\n"), "text/csv")},
    )

    assert response.status_code == 400
    temp_dir = Path(seo_query_import_router.SEO_QUERY_IMPORT_TMP_DIR)
    remaining = list(temp_dir.iterdir()) if temp_dir.exists() else []
    assert remaining == []


def test_latest_endpoint_returns_latest_batch_and_echoes_q(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    first = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("first.csv", io.BytesIO(b"query\nalpha\n"), "text/csv")},
    )
    second = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("second.csv", io.BytesIO("query;freq\nbeta;9\nbeta plus;2\n".encode("utf-8")), "text/csv")},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get(
        "/api/v1/projects/1/wildberries/seo/query-import/latest",
        params={"category_id": 777, "limit": 100, "offset": 0, "q": "beta"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch"]["original_filename"] == "second.csv"
    assert payload["normalized_queries"]["q"] == "beta"


def test_batch_detail_endpoint_honors_limit_and_offset(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    response = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={
            "file": (
                "queries.csv",
                io.BytesIO("query;freq\nalpha;10\nbeta;9\ngamma;8\n".encode("utf-8")),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201, response.text
    batch_id = response.json()["batch"]["batch_id"]

    detail = client.get(
        f"/api/v1/projects/1/wildberries/seo/query-import/batches/{batch_id}",
        params={"limit": 1, "offset": 1},
    )
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["normalized_queries"]["limit"] == 1
    assert payload["normalized_queries"]["offset"] == 1
    assert len(payload["normalized_queries"]["items"]) == 1


def test_corpus_endpoint_aggregates_multiple_completed_batches(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    first = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("first.csv", io.BytesIO("query;freq\nalpha;10\nshared;5\n".encode("utf-8")), "text/csv")},
    )
    second = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("second.csv", io.BytesIO("query;freq\nshared;7\nbeta;3\n".encode("utf-8")), "text/csv")},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get(
        "/api/v1/projects/1/wildberries/seo/query-import/corpus",
        params={"category_id": 777, "limit": 100, "offset": 0},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["active_batches_count"] == 2
    assert payload["summary"]["total_batches_count"] == 2
    assert payload["summary"]["total_normalized_rows"] == 4
    assert payload["summary"]["unique_normalized_queries"] == 3
    assert payload["summary"]["duplicate_across_batches_count"] == 1
    rows = {item["normalized_query"]: item for item in payload["normalized_queries"]["items"]}
    assert rows["shared"]["frequency_total"] == "12"
    assert rows["shared"]["raw_row_count"] == 2


def test_delete_batch_rebuilds_corpus_from_remaining_batches(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    first = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("first.csv", io.BytesIO("query;freq\nalpha;10\n".encode("utf-8")), "text/csv")},
    )
    second = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("second.csv", io.BytesIO("query;freq\nbeta;3\n".encode("utf-8")), "text/csv")},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    first_batch_id = first.json()["batch"]["batch_id"]

    response = client.delete(f"/api/v1/projects/1/wildberries/seo/query-import/batches/{first_batch_id}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["deleted_batch_id"] == first_batch_id
    assert payload["remaining_active_batches_count"] == 1
    assert payload["remaining_unique_queries_count"] == 1

    corpus = client.get(
        "/api/v1/projects/1/wildberries/seo/query-import/corpus",
        params={"category_id": 777},
    )
    assert corpus.status_code == 200, corpus.text
    rows = {item["normalized_query"] for item in corpus.json()["normalized_queries"]["items"]}
    assert rows == {"beta"}


def test_clear_category_removes_query_corpus(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    response = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("queries.csv", io.BytesIO("query;freq\nalpha;10\n".encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201

    clear = client.delete(
        "/api/v1/projects/1/wildberries/seo/query-import/category",
        params={"category_id": 777},
    )
    assert clear.status_code == 200, clear.text
    payload = clear.json()
    assert payload["action"] == "clear_category"
    assert payload["remaining_active_batches_count"] == 0
    assert payload["readiness_status"] == "not_started"

    corpus = client.get(
        "/api/v1/projects/1/wildberries/seo/query-import/corpus",
        params={"category_id": 777},
    )
    assert corpus.status_code == 200, corpus.text
    assert corpus.json()["summary"]["active_batches_count"] == 0
    assert corpus.json()["normalized_queries"]["total"] == 0


def test_latest_endpoint_returns_404_when_missing(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    response = client.get(
        "/api/v1/projects/1/wildberries/seo/query-import/latest",
        params={"category_id": 999},
    )
    assert response.status_code == 404


def test_import_endpoint_rejects_non_utf8_csv(tmp_path):
    client, SessionLocal = _build_client(tmp_path)

    response = client.post(
        "/api/v1/projects/1/wildberries/seo/query-import",
        data={"category_id": "777"},
        files={"file": ("bad.csv", io.BytesIO("Запрос;Частота\nтест;1\n".encode("cp1251")), "text/csv")},
    )
    assert response.status_code == 400
    assert "UTF-8" in response.json()["detail"]
