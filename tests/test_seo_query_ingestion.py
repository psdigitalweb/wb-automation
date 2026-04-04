from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, Table, create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoQueryBatch, SeoQueryNormalized, SeoQueryRaw
from app.services.seo.query_pipeline import import_queries_from_csv, normalize_query_text
from app.services.seo.query_pipeline.ingestion import CsvImportError


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def _make_session() -> Session:
    _ensure_projects_stub()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.commit()
    return session


def test_normalization_is_deterministic():
    assert normalize_query_text("  Платье,   красное!! ") == "платье красное"
    assert normalize_query_text("Ёлка") == "елка"


def test_import_queries_from_csv_persists_raw_normalized_and_diagnostics(tmp_path):
    csv_path = tmp_path / "queries.csv"
    csv_path.write_text(
        "Запрос;Частота\n"
        " Платье, красное ;10\n"
        "платье красное;5\n"
        "\"\";7\n"
        " ;9\n"
        "Ёлка;2\n"
        "елка;3\n"
        "елка;bad\n",
        encoding="utf-8",
    )

    session = _make_session()
    try:
        diagnostics = import_queries_from_csv(session, csv_path=str(csv_path), project_id=1, category_id=777)
        session.commit()

        assert diagnostics.project_id == 1
        assert diagnostics.category_id == 777
        assert diagnostics.query_column_resolved == "Запрос"
        assert diagnostics.frequency_column_resolved == "Частота"
        assert diagnostics.raw_rows_imported == 5
        assert diagnostics.raw_rows_skipped == 2
        assert diagnostics.normalized_rows_created == 2
        assert diagnostics.duplicate_groups_collapsed == 3
        assert diagnostics.duplicate_raw_rows_detected == 0
        assert diagnostics.top_normalized_queries[0].normalized_query == "платье красное"
        assert Decimal(str(diagnostics.top_normalized_queries[0].frequency_total)) == Decimal("15")
        assert any(item.reason == "invalid_frequency_value" for item in diagnostics.suspicious_rows)
        assert any(item.reason == "empty_or_whitespace_query" for item in diagnostics.suspicious_rows)

        batch = session.scalars(select(SeoQueryBatch)).one()
        assert batch.meta["query_column_resolved"] == "Запрос"
        assert batch.meta["frequency_column_resolved"] == "Частота"

        raw_count = session.scalar(select(func.count()).select_from(SeoQueryRaw))
        normalized = session.scalars(
            select(SeoQueryNormalized).order_by(SeoQueryNormalized.normalized_query.asc())
        ).all()
        assert raw_count == 5
        assert len(normalized) == 2
        assert normalized[0].normalized_query == "елка"
        assert Decimal(str(normalized[0].frequency_total)) == Decimal("6")
        assert normalized[1].normalized_query == "платье красное"
        assert Decimal(str(normalized[1].frequency_total)) == Decimal("15")
    finally:
        session.close()


def test_import_queries_without_frequency_column_still_succeeds(tmp_path):
    csv_path = tmp_path / "queries_no_freq.csv"
    csv_path.write_text('query\n"dress red"\n"dress, red"\n', encoding="utf-8")

    session = _make_session()
    try:
        diagnostics = import_queries_from_csv(session, csv_path=str(csv_path), project_id=1, category_id=777)
        session.commit()

        assert diagnostics.query_column_resolved == "query"
        assert diagnostics.frequency_column_resolved is None
        assert diagnostics.raw_rows_imported == 2
        assert diagnostics.normalized_rows_created == 1
        assert diagnostics.top_normalized_queries == []
    finally:
        session.close()


def test_import_queries_fails_when_query_column_missing(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("name;count\nabc;1\n", encoding="utf-8")

    session = _make_session()
    try:
        with pytest.raises(CsvImportError, match="missing a required query column"):
            import_queries_from_csv(session, csv_path=str(csv_path), project_id=1, category_id=777)
    finally:
        session.close()


def test_import_queries_fails_on_non_utf8_input(tmp_path):
    csv_path = tmp_path / "cp1251.csv"
    csv_path.write_bytes("Запрос;Частота\nтест;1\n".encode("cp1251"))

    session = _make_session()
    try:
        with pytest.raises(CsvImportError, match="UTF-8"):
            import_queries_from_csv(session, csv_path=str(csv_path), project_id=1, category_id=777)
    finally:
        session.close()
