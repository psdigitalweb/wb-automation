from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, Integer, Table, create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoCategoryMeaningAxes, SeoQueryBatch, SeoQueryNormalized
from app.services.seo.category_profile_derive_evidence import (
    CategoryProfileDeriveEvidence,
    MissingAxesError,
    MissingCorpusError,
    read_category_profile_derive_evidence,
)


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def _make_session() -> Session:
    _ensure_projects_stub()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["projects"],
            Base.metadata.tables["seo_query_batches"],
            Base.metadata.tables["seo_queries_normalized"],
            Base.metadata.tables["seo_category_meaning_axes"],
        ],
    )
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.commit()
    return session


def _seed_batch(session: Session, *, category_id: int) -> int:
    batch = SeoQueryBatch(
        project_id=1,
        category_id=category_id,
        status="completed",
        row_count=3,
        normalized_row_count=3,
        deduplicated_row_count=3,
    )
    session.add(batch)
    session.flush()
    return int(batch.id)


def _seed_corpus(session: Session, *, category_id: int, economic_value: str = "10") -> None:
    batch_id = _seed_batch(session, category_id=category_id)
    session.add_all(
        [
            SeoQueryNormalized(
                project_id=1,
                category_id=category_id,
                batch_id=batch_id,
                normalized_query="alpha carrier travel",
                display_query="Alpha carrier travel",
                raw_row_count=2,
                frequency_total=Decimal("25"),
                sample_source_payload={"raw_query": "Alpha carrier travel", "orders": economic_value},
            ),
            SeoQueryNormalized(
                project_id=1,
                category_id=category_id,
                batch_id=batch_id,
                normalized_query="beta carrier compact",
                display_query="Beta carrier compact",
                raw_row_count=1,
                frequency_total=Decimal("7"),
                sample_source_payload={"raw_query": "Beta carrier compact", "conversion": "2.5"},
            ),
        ]
    )
    session.commit()


def _seed_axes(session: Session, *, category_id: int) -> None:
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    session.add(
        SeoCategoryMeaningAxes(
            project_id=1,
            category_id=category_id,
            schema_version="category_meaning_axes_v0",
            source="deterministic",
            status="ready",
            evidence_hash="axes-hash",
            input_hash="axes-input",
            axes_payload={
                "product_type_axes": ["carrier", "case"],
                "use_case_axes": ["travel"],
                "audience_axes": ["student"],
                "attribute_axes": ["compact"],
            },
            canonical_text="carrier axes",
            prompt_version="category_meaning_axes_v0",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def _seed_axes_row(session: Session, *, category_id: int, source: str, product_type_axes: list[str]) -> None:
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    session.add(
        SeoCategoryMeaningAxes(
            project_id=1,
            category_id=category_id,
            schema_version="category_meaning_axes_v0",
            source=source,
            status="ready",
            evidence_hash=f"axes-hash-{source}",
            input_hash=f"axes-input-{source}",
            axes_payload={"product_type_axes": product_type_axes},
            canonical_text=f"{source} axes",
            prompt_version="category_meaning_axes_v0",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_evidence_reader_is_category_agnostic_for_arbitrary_category() -> None:
    session = _make_session()
    try:
        _seed_corpus(session, category_id=73001)
        _seed_axes(session, category_id=73001)

        evidence = read_category_profile_derive_evidence(session, project_id=1, category_id=73001)

        assert isinstance(evidence, CategoryProfileDeriveEvidence)
        assert evidence.category_id == 73001
        assert evidence.corpus.query_count == 2
        assert evidence.corpus.top_queries_count == 2
        assert evidence.axes.axes_payload["product_type_axes"] == ["carrier", "case"]
        builder_input = evidence.to_builder_input()
        assert builder_input["query_candidates"][0]["normalized_query"] == "alpha carrier travel"
        assert builder_input["diagnostics"]["axes"]["product_type_axes_count"] == 2
    finally:
        session.close()


def test_missing_corpus_and_missing_axes_are_controlled_failures() -> None:
    session = _make_session()
    try:
        _seed_axes(session, category_id=73002)
        with pytest.raises(MissingCorpusError, match="No SeoQueryNormalized corpus"):
            read_category_profile_derive_evidence(session, project_id=1, category_id=73002)

        _seed_corpus(session, category_id=73003)
        with pytest.raises(MissingAxesError, match="No ready SeoCategoryMeaningAxes"):
            read_category_profile_derive_evidence(session, project_id=1, category_id=73003)
    finally:
        session.close()


def test_evidence_hash_is_stable_for_identical_input() -> None:
    session = _make_session()
    try:
        _seed_corpus(session, category_id=73004)
        _seed_axes(session, category_id=73004)

        first = read_category_profile_derive_evidence(session, project_id=1, category_id=73004)
        second = read_category_profile_derive_evidence(session, project_id=1, category_id=73004)

        assert first.evidence_hash == second.evidence_hash
        assert first.to_builder_input() == second.to_builder_input()
    finally:
        session.close()


def test_latest_ready_axes_tie_uses_highest_id_deterministically() -> None:
    session = _make_session()
    try:
        _seed_corpus(session, category_id=73007)
        _seed_axes_row(session, category_id=73007, source="deterministic", product_type_axes=["older"])
        _seed_axes_row(session, category_id=73007, source="llm_enhanced", product_type_axes=["newer"])

        evidence = read_category_profile_derive_evidence(session, project_id=1, category_id=73007)

        assert evidence.axes.source == "llm_enhanced"
        assert evidence.axes.axes_payload["product_type_axes"] == ["newer"]
    finally:
        session.close()


def test_economic_fields_are_diagnostics_not_scoring_evidence() -> None:
    session = _make_session()
    try:
        _seed_corpus(session, category_id=73005, economic_value="999999")
        _seed_axes(session, category_id=73005)

        evidence = read_category_profile_derive_evidence(session, project_id=1, category_id=73005)
        builder_input = evidence.to_builder_input()
        serialized_queries = str(builder_input["query_candidates"])

        assert set(evidence.corpus.economic_field_names_present) == {"conversion", "orders"}
        assert "orders" not in serialized_queries
        assert "conversion" not in serialized_queries
        assert "999999" not in str(builder_input)
        assert "scoring" not in builder_input
    finally:
        session.close()


def test_evidence_shape_contains_inputs_needed_by_generic_builder() -> None:
    session = _make_session()
    try:
        _seed_corpus(session, category_id=73006)
        _seed_axes(session, category_id=73006)

        evidence = read_category_profile_derive_evidence(session, project_id=1, category_id=73006, token_limit=5)
        builder_input = evidence.to_builder_input()

        assert builder_input["evidence_hash"].startswith("sha256:")
        assert builder_input["corpus"]["distinct_query_count"] == 2
        assert builder_input["query_token_counts"]["carrier"] == 32
        assert builder_input["axes"]["axes_payload"]["use_case_axes"] == ["travel"]
        assert builder_input["diagnostics"]["status"] == "ready"
    finally:
        session.close()
