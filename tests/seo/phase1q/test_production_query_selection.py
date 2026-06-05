from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, Numeric, Table, Text, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    SeoCategoryMeaningAxes,
    SeoMeaningAtom,
    SeoQueryAnnotation,
    SeoQueryBatch,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoSkuMeaningAnnotation,
)
from app.services.seo import production_query_selection as pqs
from app.services.seo.production_query_selection import (
    PRODUCTION_QUERY_SELECTION_MODEL,
    PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
    _parse_json_object,
    build_production_query_selection_preview,
    run_production_query_selection,
)
from app.services.seo.providers.base import ChatMessage, ChatProvider, ChatResponse


class FakeProvider(ChatProvider):
    chat_model = "fake-query-selection-model"

    def generate_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.messages = list(messages)
        self.calls = getattr(self, "calls", [])
        self.calls.append(list(messages))
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        content = {
            "lines": [
                {
                    "line": "exact product",
                    "selected": [1],
                    "operator_candidates": [2],
                }
            ],
        }
        return ChatResponse(model=self.chat_model, content=json.dumps(content), raw_response={"content": content})


class CapturingDefaultProvider(FakeProvider):
    def __init__(self, **kwargs):
        self.chat_model = kwargs.get("chat_model")
        self.kwargs = kwargs


def _session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS products"))
    metadata = MetaData()
    Table(
        "products",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("project_id", Integer, nullable=False),
        Column("nm_id", Integer, nullable=False),
        Column("subject_id", Integer),
        Column("subject_name", Text),
        Column("title", Text),
        Column("description", Text),
        Column("rating", Numeric),
        Column("feedbacks", Integer),
        Column("pics", JSON),
        Column("dimensions", JSON),
        Column("characteristics", JSON),
        Column("updated_at", DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    with SessionLocal.begin() as session:
        session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    return SessionLocal


def _seed_ready_selection_scope(SessionLocal: sessionmaker) -> None:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, project_id, nm_id, subject_id, subject_name, title, description, dimensions, characteristics, updated_at)
                VALUES
                    (1, 1, 1001, 73001, 'Alpha category', 'Alpha product', 'Alpha description', '{"width": 10}', '[{"name":"size","value":"small"},{"name":"Сертификат соответствия","value":"ЕАЭС"},{"name":"Ставка НДС","value":"20%"},{"name":"Декларация","value":"registered"}]', :updated_at)
                """
            ),
            {"updated_at": now},
        )
        batch = SeoQueryBatch(
            project_id=1,
            category_id=73001,
            status="completed",
            row_count=10,
            normalized_row_count=2,
            deduplicated_row_count=2,
            created_at=now,
            updated_at=now,
        )
        annotation = SeoSkuMeaningAnnotation(
            project_id=1,
            category_id=73001,
            nm_id=1001,
            status="ready",
            meaning_payload={},
            evidence_hash="evidence-hash",
            created_at=now,
            updated_at=now,
        )
        session.add_all([batch, annotation])
        session.flush()
        session.add_all(
            [
                SeoQueryCluster(
                    id=1,
                    project_id=1,
                    category_id=73001,
                    cluster_key="cluster-compact",
                    label="compact use",
                    top_query_text="alpha compact",
                    status="ready",
                    query_count=7,
                    created_at=now,
                    updated_at=now,
                ),
                SeoQueryCluster(
                    id=2,
                    project_id=1,
                    category_id=73001,
                    cluster_key="cluster-gift",
                    label="gift use",
                    top_query_text="alpha gift",
                    status="ready",
                    query_count=3,
                    created_at=now,
                    updated_at=now,
                ),
                SeoCategoryMeaningAxes(
                    project_id=1,
                    category_id=73001,
                    status="ready",
                    evidence_hash="axes-hash",
                    axes_payload={"expressive_axes": ["minimal"], "audience_axes": ["office"]},
                    canonical_text="alpha axes",
                    input_hash="axes-input",
                    created_at=now,
                    updated_at=now,
                ),
                SeoMeaningAtom(
                    project_id=1,
                    category_id=73001,
                    entity_type="sku_vision",
                    entity_id=int(annotation.id),
                    nm_id=1001,
                    input_hash="vision-input",
                    atoms_payload={
                        "facts": [{"type": "visual", "field": "style", "value": "minimal"}],
                        "selected_image_urls": ["https://cdn.example.test/1.jpg"],
                    },
                    canonical_summary="minimal",
                    status="ready",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )


def _seed_large_ready_selection_scope(SessionLocal: sessionmaker) -> None:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    cluster_count = 2600
    representatives_per_cluster = 1
    with SessionLocal.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO products
                    (id, project_id, nm_id, subject_id, subject_name, title, description, dimensions, characteristics, updated_at)
                VALUES
                    (1, 1, 2002, 73002, 'Wide category', 'Wide product', 'Wide description', '{"width": 10}', '[{"name":"style","value":"милая эстетичная pinterest"}]', :updated_at)
                """
            ),
            {"updated_at": now},
        )
        batch = SeoQueryBatch(
            project_id=1,
            category_id=73002,
            status="completed",
            row_count=cluster_count * representatives_per_cluster,
            normalized_row_count=cluster_count * representatives_per_cluster,
            deduplicated_row_count=cluster_count * representatives_per_cluster,
            created_at=now,
            updated_at=now,
        )
        annotation = SeoSkuMeaningAnnotation(
            project_id=1,
            category_id=73002,
            nm_id=2002,
            status="ready",
            meaning_payload={},
            evidence_hash="wide-evidence-hash",
            created_at=now,
            updated_at=now,
        )
        session.add_all([batch, annotation])
        session.flush()
        session.add(
            SeoCategoryMeaningAxes(
                project_id=1,
                category_id=73002,
                status="ready",
                evidence_hash="wide-axes-hash",
                axes_payload={"expressive_axes": ["minimal"], "audience_axes": ["office"]},
                canonical_text="wide axes",
                input_hash="wide-axes-input",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SeoMeaningAtom(
                project_id=1,
                category_id=73002,
                entity_type="sku_vision",
                entity_id=int(annotation.id),
                nm_id=2002,
                input_hash="wide-vision-input",
                atoms_payload={
                        "facts": [{"type": "visual", "field": "style", "value": "minimal"}],
                        "style": ["милая", "эстетичная", "pinterest"],
                        "selected_image_urls": ["https://cdn.example.test/2.jpg"],
                },
                canonical_summary="minimal",
                status="ready",
                created_at=now,
                updated_at=now,
            )
        )
        for cluster_index in range(cluster_count):
            is_expressive_probe = cluster_index == cluster_count - 1
            top_query_text = (
                "милая эстетичная pinterest кружка"
                if is_expressive_probe
                else f"wide query {cluster_index} head"
            )
            cluster = SeoQueryCluster(
                project_id=1,
                category_id=73002,
                cluster_key=f"wide-cluster-{cluster_index}",
                label=f"meaning line {cluster_index}",
                top_query_text=top_query_text,
                status="ready",
                query_count=representatives_per_cluster,
                created_at=now,
                updated_at=now,
            )
            session.add(cluster)
            session.flush()
            for representative_index in range(representatives_per_cluster):
                query_text = (
                    "милая эстетичная pinterest кружка"
                    if is_expressive_probe
                    else f"wide query {cluster_index} rep {representative_index}"
                )
                query_annotation = SeoQueryAnnotation(
                    project_id=1,
                    category_id=73002,
                    normalized_query_text=query_text,
                    annotation_status="ready",
                    pruning_status="keep",
                    pruning_reason_code="pipeline_candidate",
                    is_kept_for_pipeline=True,
                    query_type="tail",
                    annotation_reason_code="test",
                    latest_version_number=1,
                    meta={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(query_annotation)
                session.flush()
                session.add(
                    SeoQueryClusterMembership(
                        project_id=1,
                        category_id=73002,
                        cluster_id=int(cluster.id),
                        annotation_id=int(query_annotation.id),
                        normalized_query_text=query_text,
                        query_type="tail",
                        ranking_value_used=Decimal(1000 + cluster_index),
                        membership_reason_code="test_representative",
                        created_at=now,
                        updated_at=now,
                    )
                )


def test_preview_reports_readiness_and_total_candidate_count() -> None:
    SessionLocal = _session_factory()
    _seed_ready_selection_scope(SessionLocal)

    with SessionLocal() as session:
        preview = build_production_query_selection_preview(
            session,
            project_id=1,
            nm_id=1001,
            category_id=73001,
            preview_limit=1,
        )

    assert preview.readiness.can_run is True
    assert preview.readiness.blocking_reasons == []
    assert preview.category.query_count == 10
    assert preview.category.cluster_count == 2
    assert preview.candidates.candidate_count == 2
    assert len(preview.candidates.items) == 1
    assert preview.ai_vision.ready is True


def test_run_input_uses_wide_candidate_set_when_corpus_is_large() -> None:
    SessionLocal = _session_factory()
    _seed_large_ready_selection_scope(SessionLocal)
    provider = FakeProvider()

    with SessionLocal.begin() as session:
        result = run_production_query_selection(
            session,
            project_id=1,
            nm_id=2002,
            category_id=73002,
            provider=provider,
        )

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT request_payload FROM seo_generation_runs WHERE id = :id"),
            {"id": result.run_id},
        ).mappings().one()
    request_payload = row["request_payload"]
    if isinstance(request_payload, str):
        request_payload = json.loads(request_payload)
    input_payload = request_payload["input"]

    assert len(input_payload["query_candidates"]) > 240
    frequencies = [item["frequency"] for item in input_payload["query_candidates"]]
    assert frequencies == sorted(frequencies, reverse=True)
    assert any("pinterest" in item["query"] for item in input_payload["query_candidates"])
    assert input_payload["candidate_count_sent"] == len(input_payload["query_candidates"])
    assert input_payload["candidate_count_total"] >= input_payload["candidate_count_sent"]
    assert result.sent_candidate_count == len(input_payload["query_candidates"])
    assert len(provider.calls) > 1


def test_default_production_model_is_gpt4o(monkeypatch) -> None:
    SessionLocal = _session_factory()
    _seed_ready_selection_scope(SessionLocal)
    created: list[CapturingDefaultProvider] = []

    def fake_openrouter_provider(**kwargs):
        provider = CapturingDefaultProvider(**kwargs)
        created.append(provider)
        return provider

    monkeypatch.setattr(pqs, "OpenRouterProvider", fake_openrouter_provider)

    with SessionLocal.begin() as session:
        result = run_production_query_selection(
            session,
            project_id=1,
            nm_id=1001,
            category_id=73001,
        )

    assert created
    assert created[0].chat_model == PRODUCTION_QUERY_SELECTION_MODEL
    assert created[0].chat_model == "openai/gpt-4o"
    assert result.model == "openai/gpt-4o"

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT model_name FROM seo_generation_runs WHERE id = :id"),
            {"id": result.run_id},
        ).mappings().one()
    assert row["model_name"] == "openai/gpt-4o"


def test_generated_messages_use_agreed_test_contract() -> None:
    SessionLocal = _session_factory()
    _seed_ready_selection_scope(SessionLocal)
    provider = FakeProvider()

    with SessionLocal.begin() as session:
        run_production_query_selection(
            session,
            project_id=1,
            nm_id=1001,
            category_id=73001,
            provider=provider,
        )

    user_message = provider.messages[1].content
    assert "Ты помогаешь выбрать поисковые запросы" in user_message
    assert "Покупательские смыслы товара важнее частотности" in user_message
    assert "Нишевая смысловая линия не должна исчезать" in user_message
    assert "Частотность используй только для выбора между запросами внутри одной и той же смысловой линии" in user_message
    assert "визуальный или эмоциональный стиль" in user_message
    assert "selected: ориентир 30-50 запросов" in user_message
    assert '"lines": [' in user_message
    assert '"selected": [58658, 58768, 61713]' in user_message
    assert '"operator_candidates": [65927, 58648]' in user_message
    assert "id | запрос | частотность" in user_message
    assert "Input JSON" not in user_message


def test_parser_accepts_id_only_contract() -> None:
    SessionLocal = _session_factory()
    _seed_ready_selection_scope(SessionLocal)

    with SessionLocal.begin() as session:
        result = run_production_query_selection(
            session,
            project_id=1,
            nm_id=1001,
            category_id=73001,
            provider=FakeProvider(),
        )

    assert [line.line for line in result.meaning_lines] == ["exact product"]
    assert result.meaning_lines[0].coverage_status == "covered"
    assert result.selected_queries[0].confidence is None
    assert result.selected_queries[0].explanation == ""
    assert [item.query for item in result.selected_queries] == ["alpha compact"]
    assert [item.query for group in result.operator_candidates.values() for item in group] == ["alpha gift"]

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT response_payload FROM seo_generation_runs WHERE id = :id"),
            {"id": result.run_id},
        ).mappings().one()
    response_payload = row["response_payload"]
    if isinstance(response_payload, str):
        response_payload = json.loads(response_payload)
    assert isinstance(response_payload["parsed"], list)
    assert "reject" not in response_payload["parsed"][0]
    assert response_payload["parsed"][0]["lines"][0]["selected"] == [1]
    assert response_payload["parsed"][0]["lines"][0]["operator_candidates"] == [2]
    assert "meaning_lines" in response_payload


def test_seo_noise_characteristics_are_excluded_from_llm_input() -> None:
    SessionLocal = _session_factory()
    _seed_ready_selection_scope(SessionLocal)

    with SessionLocal.begin() as session:
        result = run_production_query_selection(
            session,
            project_id=1,
            nm_id=1001,
            category_id=73001,
            provider=FakeProvider(),
        )

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT request_payload FROM seo_generation_runs WHERE id = :id"),
            {"id": result.run_id},
        ).mappings().one()
    request_payload = row["request_payload"]
    if isinstance(request_payload, str):
        request_payload = json.loads(request_payload)
    product_payload = request_payload["input"]["product"]
    assert "characteristics" not in product_payload
    assert "dimensions" not in product_payload


def test_preview_display_limit_does_not_limit_backend_run_input() -> None:
    SessionLocal = _session_factory()
    _seed_large_ready_selection_scope(SessionLocal)

    with SessionLocal() as session:
        preview = build_production_query_selection_preview(
            session,
            project_id=1,
            nm_id=2002,
            category_id=73002,
            preview_limit=5,
        )

    assert len(preview.candidates.items) == 5
    assert preview.candidates.display_candidate_count == 5
    assert preview.candidates.total_candidate_count > 240

    with SessionLocal.begin() as session:
        result = run_production_query_selection(
            session,
            project_id=1,
            nm_id=2002,
            category_id=73002,
            provider=FakeProvider(),
        )

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT request_payload FROM seo_generation_runs WHERE id = :id"),
            {"id": result.run_id},
        ).mappings().one()
    request_payload = row["request_payload"]
    if isinstance(request_payload, str):
        request_payload = json.loads(request_payload)

    assert len(request_payload["input"]["query_candidates"]) > len(preview.candidates.items)
    assert len(request_payload["input"]["query_candidates"]) > 240


def test_run_persists_artifact_and_does_not_store_rejected_contract() -> None:
    SessionLocal = _session_factory()
    _seed_ready_selection_scope(SessionLocal)

    with SessionLocal.begin() as session:
        result = run_production_query_selection(
            session,
            project_id=1,
            nm_id=1001,
            category_id=73001,
            provider=FakeProvider(),
        )

    assert result.status == "completed"
    assert result.prompt_version == PRODUCTION_QUERY_SELECTION_PROMPT_VERSION
    assert result.selected_queries[0].query == "alpha compact"
    assert [item.query for item in result.selected_queries] == ["alpha compact"]
    assert [item.query for group in result.operator_candidates.values() for item in group] == ["alpha gift"]
    assert result.artifact_path is not None

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT request_payload, response_payload FROM seo_generation_runs WHERE id = :id"),
            {"id": result.run_id},
        ).mappings().one()
    response_payload = row["response_payload"]
    if isinstance(response_payload, str):
        response_payload = json.loads(response_payload)
    assert "reject" not in response_payload["parsed"]
    assert response_payload["prompt_version"] == PRODUCTION_QUERY_SELECTION_PROMPT_VERSION
