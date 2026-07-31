from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    SeoQueryAnnotation,
    SeoCategoryMatchingReadiness,
    SeoQueryCluster,
    SeoQueryClusterMembership,
    SeoQueryMeaning,
)
from app.schemas.seo_sku_meaning import SkuMeaningAnnotationRequest, SkuMeaningPayload, SkuQueryJudgmentInput
from app.services.seo.providers.base import ChatMessage, ChatProvider, ChatResponse, EmbeddingProvider, EmbeddingResponse
from app.services.seo.query_meaning_matcher import build_query_meaning_library, run_meaning_aware_matcher
from app.services.seo.query_meaning_matcher.matcher import CategoryBootstrapBuildingError
from app.services.seo.query_meaning_matcher.embeddings import ensure_meaning_embedding
from app.services.seo.sku_meaning import save_annotation, save_query_judgments


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["projects"],
            Base.metadata.tables["seo_query_batches"],
            Base.metadata.tables["seo_queries_normalized"],
            Base.metadata.tables["seo_query_annotations"],
            Base.metadata.tables["seo_query_annotation_versions"],
            Base.metadata.tables["seo_query_clusters"],
            Base.metadata.tables["seo_query_cluster_memberships"],
            Base.metadata.tables["seo_query_meanings"],
            Base.metadata.tables["seo_meaning_embeddings"],
            Base.metadata.tables["seo_category_bootstrap_runs"],
            Base.metadata.tables["seo_category_matching_readiness"],
            Base.metadata.tables["seo_category_meaning_axes"],
            Base.metadata.tables["seo_sku_meaning_annotations"],
            Base.metadata.tables["seo_sku_query_judgments"],
            Base.metadata.tables["seo_sku_meaning_audit_events"],
        ],
    )
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.commit()
    return session


def _seed_cluster(session: Session, *, cluster_key: str, query: str, rank: float) -> None:
    annotation = SeoQueryAnnotation(
        project_id=1,
        category_id=812,
        normalized_query_text=query,
        pruning_status="keep",
        annotation_status="done",
        is_kept_for_pipeline=True,
        query_type="head" if rank >= 10000 else "mid",
        intent_type="product",
    )
    session.add(annotation)
    session.flush()
    cluster = SeoQueryCluster(
        project_id=1,
        category_id=812,
        cluster_key=cluster_key,
        label=query,
        top_query_text=query,
        status="ready",
        query_count=1,
    )
    session.add(cluster)
    session.flush()
    session.add(
        SeoQueryClusterMembership(
            project_id=1,
            category_id=812,
            cluster_id=int(cluster.id),
            annotation_id=int(annotation.id),
            normalized_query_text=query,
            query_type=annotation.query_type,
            ranking_value_used=rank,
            membership_reason_code="test",
        )
    )


def _seed_cluster_with_members(session: Session, *, cluster_key: str, top_query: str, members: list[tuple[str, float]]) -> None:
    annotations: list[SeoQueryAnnotation] = []
    for query, rank in members:
        annotation = SeoQueryAnnotation(
            project_id=1,
            category_id=812,
            normalized_query_text=query,
            pruning_status="keep",
            annotation_status="done",
            is_kept_for_pipeline=True,
            query_type="head" if rank >= 10000 else "mid",
            intent_type="product",
        )
        session.add(annotation)
        session.flush()
        annotations.append(annotation)
    cluster = SeoQueryCluster(
        project_id=1,
        category_id=812,
        cluster_key=cluster_key,
        label=top_query,
        top_query_text=top_query,
        status="ready",
        query_count=len(members),
    )
    session.add(cluster)
    session.flush()
    for annotation, (query, rank) in zip(annotations, members, strict=True):
        session.add(
            SeoQueryClusterMembership(
                project_id=1,
                category_id=812,
                cluster_id=int(cluster.id),
                annotation_id=int(annotation.id),
                normalized_query_text=query,
                query_type=annotation.query_type,
                ranking_value_used=rank,
                membership_reason_code="test",
            )
        )


def _seed_project(session: Session) -> None:
    for cluster_key, query, rank in [
        ("c_generic", "кружка", 41597),
        ("c_cute", "милая кружка", 1200),
        ("c_capybara", "кружка с капибарой", 3202),
        ("c_gift", "кружка в подарок", 900),
        ("c_thermal", "термокружка", 28299),
        ("c_set", "кружки набор 6 штук", 6685),
    ]:
        _seed_cluster(session, cluster_key=cluster_key, query=query, rank=rank)
    meaning = SkuMeaningPayload(
        functional={"product_type": "кружка", "attributes": ["керамика"]},
        expressive={"vibes": ["Милота и уют", "Подарочная привлекательность", "Красота и эстетика"]},
        audience=["любимая", "подруга", "себе"],
        negative_constraints=["термокружка", "набор кружек 6 штук"],
        confidence={"functional": 0.9, "expressive": 0.85},
        review_status="verified",
    )
    save_annotation(
        session,
        project_id=1,
        category_id=812,
        nm_id=534824414,
        request=SkuMeaningAnnotationRequest(
            meaning=meaning,
            status="verified",
            evidence_hash="test-evidence",
            reviewer="qa",
        ),
    )
    session.commit()


class FakeChatProvider(ChatProvider):
    chat_model = "fake/query-meaning"

    def generate_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        del messages, temperature, top_p, max_tokens
        return ChatResponse(
            model=self.chat_model,
            content=json.dumps(
                {
                    "functional": {},
                    "expressive": {},
                    "audience": [],
                    "occasion": [],
                    "constraints": [],
                    "conflicts_if_missing": [],
                    "genericness": "specific",
                    "confidence": {"functional": 0.7},
                },
                ensure_ascii=False,
            ),
            raw_response={"ok": True},
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    embedding_model = "fake/meaning-embedding"

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(
            model=self.embedding_model,
            embeddings=[self._vector(text) for text in texts],
            raw_response={"ok": True},
        )

    def _vector(self, text: str) -> list[float]:
        value = text.lower().replace("ё", "е")
        return [
            1.0 if "круж" in value else 0.0,
            1.0 if any(token in value for token in ("мил", "уют", "эстет", "подар")) else 0.0,
            1.0 if "термо" in value else 0.0,
            1.0 if "set" in value or "набор" in value else 0.0,
        ]


def test_query_meaning_library_build_stores_cluster_level_meanings():
    session = _make_session()
    try:
        _seed_project(session)
        _seed_cluster(session, cluster_key="c_fox", query="кружка с лисой", rank=500)
        result = build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=10,
        )
        session.commit()

        assert result.created == 7
        assert result.errors == 0
        meanings = {
            row.cluster_key: row
            for row in session.scalars(select(SeoQueryMeaning).where(SeoQueryMeaning.category_id == 812)).all()
        }
        assert meanings["c_thermal"].constraints == ["thermal"]
        assert "set_quantity:6" in meanings["c_set"].constraints
        assert meanings["c_generic"].genericness == "generic"
        assert "милая" in meanings["c_cute"].meaning_payload["expressive"]["vibes"]
        assert "капибара" in meanings["c_capybara"].meaning_payload["functional"]["attributes"]
        assert "капибара" in meanings["c_capybara"].canonical_text
        assert meanings["c_capybara"].genericness == "specific"
        assert "лиса" in meanings["c_fox"].meaning_payload["functional"]["attributes"]
        assert "лиса" in meanings["c_fox"].canonical_text
        assert meanings["c_fox"].genericness == "specific"
    finally:
        session.close()


def test_embedding_store_deduplicates_by_model_and_input_hash():
    session = _make_session()
    try:
        row1 = ensure_meaning_embedding(
            session,
            project_id=1,
            category_id=812,
            entity_type="sku_meaning",
            entity_id=1,
            canonical_text="товар: кружка\nстиль: милая",
            provider=FakeEmbeddingProvider(),
        )
        row2 = ensure_meaning_embedding(
            session,
            project_id=1,
            category_id=812,
            entity_type="sku_meaning",
            entity_id=1,
            canonical_text="товар: кружка\nстиль: милая",
            provider=FakeEmbeddingProvider(),
        )
        assert row1.id == row2.id
    finally:
        session.close()


def test_meaning_aware_matcher_buckets_expressive_above_generic_and_rejects_conflicts():
    session = _make_session()
    try:
        _seed_project(session)
        build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=10,
        )
        session.commit()

        result = run_meaning_aware_matcher(
            session,
            project_id=1,
            category_id=812,
            nm_id=534824414,
            embedding_provider=FakeEmbeddingProvider(),
        )
        primary_queries = {item.query for item in result.buckets["primary"]}
        secondary_queries = {item.query for item in result.buckets["secondary"]}
        broad_queries = {item.query for item in result.buckets["broad"]}
        rejected_queries = {item.query for item in result.buckets["rejected"]}

        assert "милая кружка" in primary_queries | secondary_queries
        assert "кружка в подарок" in primary_queries | secondary_queries
        assert "кружка" in broad_queries
        assert "термокружка" in rejected_queries
        assert "кружки набор 6 штук" in rejected_queries
        assert "кружка" not in primary_queries
    finally:
        session.close()


def test_query_meaning_rules_avoid_name_false_positive_and_mixed_cluster_hard_constraints():
    session = _make_session()
    try:
        _seed_project(session)
        _seed_cluster(session, cluster_key="c_name_milana", query="кружка милана", rank=55)
        _seed_cluster_with_members(
            session,
            cluster_key="c_300ml_mixed",
            top_query="кружка 300 мл",
            members=[
                ("кружка 300 мл", 300),
                ("кружка фарфоровая 300 мл", 200),
                ("кружки 300 мл набор", 150),
                ("кружка стеклянная 300 мл", 120),
            ],
        )
        build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=20,
        )
        session.commit()

        meanings = {
            row.cluster_key: row
            for row in session.scalars(select(SeoQueryMeaning).where(SeoQueryMeaning.category_id == 812)).all()
        }

        name_payload = meanings["c_name_milana"].meaning_payload
        assert name_payload["expressive"]["vibes"] == []
        assert "милая" not in meanings["c_name_milana"].canonical_text

        mixed = meanings["c_300ml_mixed"]
        assert "set" not in mixed.constraints
        assert "material:glass" not in mixed.constraints
        assert "material:porcelain" not in mixed.constraints
        assert mixed.meaning_payload["expressive"]["vibes"] == []
        assert mixed.meaning_payload["expressive"]["styles"] == []
    finally:
        session.close()


def test_matcher_does_not_promote_names_or_generic_parent_gift_to_primary():
    session = _make_session()
    try:
        _seed_project(session)
        _seed_cluster(session, cluster_key="c_name_milana", query="кружка милана", rank=55)
        _seed_cluster_with_members(
            session,
            cluster_key="c_mom_gift",
            top_query="кружка маме",
            members=[("кружка маме", 600), ("подарок маме кружка", 500)],
        )
        build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=20,
        )
        session.commit()

        result = run_meaning_aware_matcher(
            session,
            project_id=1,
            category_id=812,
            nm_id=534824414,
            embedding_provider=FakeEmbeddingProvider(),
            limit=80,
        )
        primary_queries = {item.query for item in result.buckets["primary"]}
        assert "кружка милана" not in primary_queries
        assert "кружка маме" not in primary_queries
    finally:
        session.close()


def test_manual_rejected_judgment_forces_matcher_rejected_bucket():
    session = _make_session()
    try:
        _seed_project(session)
        build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=10,
        )
        session.commit()

        first = run_meaning_aware_matcher(
            session,
            project_id=1,
            category_id=812,
            nm_id=534824414,
            embedding_provider=FakeEmbeddingProvider(),
            limit=80,
        )
        assert "милая кружка" in {item.query for item in first.buckets["primary"]} | {
            item.query for item in first.buckets["secondary"]
        }

        annotation_id = int(first.sku_annotation_id)
        cute_item = next(
            item
            for bucket in ("primary", "secondary", "broad")
            for item in first.buckets[bucket]
            if item.query == "милая кружка"
        )
        save_query_judgments(
            session,
            project_id=1,
            nm_id=534824414,
            category_id=812,
            annotation_id=annotation_id,
            items=[
                SkuQueryJudgmentInput(
                    query_text=cute_item.query,
                    normalized_query_text=cute_item.query,
                    cluster_id=cute_item.cluster_id,
                    cluster_key=cute_item.cluster_key,
                    label="manual_rejected",
                    rationale="bad candidate for this SKU",
                    matcher_version="test",
                    source="matcher_preview",
                )
            ],
        )
        session.commit()

        result = run_meaning_aware_matcher(
            session,
            project_id=1,
            category_id=812,
            nm_id=534824414,
            embedding_provider=FakeEmbeddingProvider(),
            limit=80,
        )
        rejected = {item.query: item for item in result.buckets["rejected"]}
        assert "милая кружка" in rejected
        assert any("manual judgment: manual_rejected" in reason for reason in rejected["милая кружка"].reasons)
    finally:
        session.close()


def test_sku_negative_audience_constraint_rejects_conflicting_backpack_queries():
    session = _make_session()
    try:
        _seed_cluster(session, cluster_key="c_backpack_boy_school", query="рюкзак школьный для мальчика", rank=5000)
        _seed_cluster(session, cluster_key="c_backpack_girl_school", query="рюкзак школьный для девочки", rank=4500)
        meaning = SkuMeaningPayload(
            functional={"product_type": "рюкзак", "use_cases": ["для школы"], "attributes": ["женский"]},
            expressive={"vibes": ["стильный"]},
            audience=["женский", "школьники"],
            negative_constraints=["не мужской рюкзак"],
            confidence={"functional": 0.9},
            review_status="verified",
        )
        save_annotation(
            session,
            project_id=1,
            category_id=812,
            nm_id=453416555,
            request=SkuMeaningAnnotationRequest(
                meaning=meaning,
                status="verified",
                evidence_hash="backpack-test",
                reviewer="qa",
            ),
        )
        build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=20,
        )
        session.commit()

        result = run_meaning_aware_matcher(
            session,
            project_id=1,
            category_id=812,
            nm_id=453416555,
            embedding_provider=FakeEmbeddingProvider(),
            limit=80,
        )

        rejected = {item.query: item for item in result.buckets["rejected"]}
        primary = {item.query: item for item in result.buckets["primary"]}
        assert "рюкзак школьный для мальчика" in rejected
        assert any("negative constraint" in reason for reason in rejected["рюкзак школьный для мальчика"].reasons)
        assert "рюкзак школьный для девочки" in primary
        assert "для" not in primary["рюкзак школьный для девочки"].matched_meanings
    finally:
        session.close()


def test_matcher_blocks_while_category_bootstrap_is_building():
    session = _make_session()
    try:
        _seed_project(session)
        build_query_meaning_library(
            session,
            project_id=1,
            category_id=812,
            provider=FakeChatProvider(),
            limit=10,
        )
        session.add(
            SeoCategoryMatchingReadiness(
                project_id=1,
                category_id=812,
                status="building",
                category_axes_status="not_started",
            )
        )
        session.commit()

        try:
            run_meaning_aware_matcher(
                session,
                project_id=1,
                category_id=812,
                nm_id=534824414,
                embedding_provider=FakeEmbeddingProvider(),
            )
        except CategoryBootstrapBuildingError as exc:
            assert "still running" in str(exc)
        else:
            raise AssertionError("matcher should block while bootstrap is building")
    finally:
        session.close()
