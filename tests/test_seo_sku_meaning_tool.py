from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoQueryAnnotation
from app.schemas.seo_sku_meaning import (
    SkuMeaningAnnotationRequest,
    SkuMeaningEvalExportRequest,
    SkuMeaningPayload,
    SkuQueryJudgmentInput,
)
from app.services.seo.providers.base import ChatMessage, ChatProvider, ChatResponse
from app.services.seo.sku_meaning import (
    build_sku_evidence_pack,
    export_eval_dataset,
    generate_sku_meaning_draft,
    list_candidate_queries,
    save_annotation,
    save_query_judgments,
)
from app.services.seo.sku_meaning.draft import SkuMeaningDraftStore


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
            Base.metadata.tables["seo_sku_meaning_annotations"],
            Base.metadata.tables["seo_sku_query_judgments"],
            Base.metadata.tables["seo_sku_meaning_audit_events"],
        ],
    )
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.execute(
        text(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                nm_id INTEGER NOT NULL,
                vendor_code TEXT,
                title TEXT,
                brand TEXT,
                subject_id INTEGER,
                subject_name TEXT,
                description TEXT,
                price_u INTEGER,
                sale_price_u INTEGER,
                rating NUMERIC,
                feedbacks INTEGER,
                sizes TEXT,
                colors TEXT,
                pics TEXT,
                dimensions TEXT,
                characteristics TEXT,
                raw TEXT,
                updated_at DATETIME
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE wb_feedback_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                nm_id INTEGER NOT NULL,
                product_valuation INTEGER,
                created_date DATETIME,
                raw TEXT
            )
            """
        )
    )
    session.commit()
    return session


def _seed_sku(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO products (
                project_id, nm_id, vendor_code, title, brand, subject_id, subject_name,
                description, rating, feedbacks, characteristics, updated_at
            )
            VALUES (
                1, 1001, 'MUG-1', 'Милая кружка с котом', 'Zakka', 812, 'Кружки',
                'Керамическая кружка для подарка, эстетика pinterest.',
                4.9, 12, :characteristics, :updated_at
            )
            """
        ),
        {
            "characteristics": json.dumps(
                [{"name": "Материал", "value": ["керамика"]}, {"name": "Объем", "value": ["350 мл"]}],
                ensure_ascii=False,
            ),
            "updated_at": datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
        },
    )
    session.execute(
        text(
            """
            INSERT INTO wb_feedback_snapshots (project_id, nm_id, product_valuation, created_date, raw)
            VALUES (1, 1001, 5, :created_date, :raw)
            """
        ),
        {
            "created_date": datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),
            "raw": json.dumps({"text": "Очень милая кружка, брала в подарок.", "pros": "Красивая"}, ensure_ascii=False),
        },
    )
    session.add(
        SeoQueryAnnotation(
            project_id=1,
            category_id=812,
            normalized_query_text="милая кружка",
            pruning_status="keep",
            annotation_status="done",
            is_kept_for_pipeline=True,
            query_type="mid",
            intent_type="product",
        )
    )
    session.add(
        SeoQueryAnnotation(
            project_id=1,
            category_id=812,
            normalized_query_text="кружка для чая",
            pruning_status="keep",
            annotation_status="done",
            is_kept_for_pipeline=True,
            query_type="head",
            intent_type="product",
        )
    )
    session.commit()


class FakeProvider(ChatProvider):
    chat_model = "fake/sku-meaning"

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
                    "functional": {"product_type": "кружка", "use_cases": ["для подарка"], "attributes": ["керамика"]},
                    "expressive": {"vibes": ["милая", "pinterest"], "styles": ["эстетичная"]},
                    "audience": ["подарок"],
                    "negative_constraints": ["классическая кружка для чая"],
                    "confidence": {"functional": 0.8, "expressive": 0.75},
                    "evidence_refs": ["product.title", "review:0"],
                    "review_status": "draft",
                },
                ensure_ascii=False,
            ),
            raw_response={"ok": True},
        )


def test_evidence_pack_and_llm_draft_cache(tmp_path):
    session = _make_session()
    try:
        _seed_sku(session)
        evidence = build_sku_evidence_pack(session, project_id=1, category_id=812, nm_id=1001)

        assert evidence.evidence_hash
        assert evidence.product.title == "Милая кружка с котом"
        assert evidence.reviews[0].ref == "review:0"
        assert evidence.product_projection.get("nm_id") == 1001

        store = SkuMeaningDraftStore(root_dir=tmp_path)
        draft = generate_sku_meaning_draft(evidence, provider=FakeProvider(), store=store)
        cached = generate_sku_meaning_draft(evidence, provider=FakeProvider(), store=store)

        assert draft.cached is False
        assert cached.cached is True
        assert "pinterest" in cached.meaning.expressive["vibes"]
        assert cached.artifact_path
    finally:
        session.close()


def test_annotation_judgments_and_eval_export_roundtrip():
    session = _make_session()
    try:
        _seed_sku(session)
        evidence = build_sku_evidence_pack(session, project_id=1, category_id=812, nm_id=1001)
        meaning = SkuMeaningPayload(
            functional={"product_type": "кружка"},
            expressive={"vibes": ["милая"]},
            audience=["подарок"],
            negative_constraints=["слишком общий запрос"],
            confidence={"functional": 0.9},
            evidence_refs=["product.title"],
            review_status="verified",
        )

        annotation = save_annotation(
            session,
            project_id=1,
            category_id=812,
            nm_id=1001,
            request=SkuMeaningAnnotationRequest(
                meaning=meaning,
                status="verified",
                evidence_hash=evidence.evidence_hash,
                reviewer="qa",
            ),
        )
        candidates = list_candidate_queries(session, project_id=1, category_id=812, nm_id=1001)
        assert {item.normalized_query_text for item in candidates} == {"милая кружка", "кружка для чая"}

        first = save_query_judgments(
            session,
            project_id=1,
            category_id=812,
            nm_id=1001,
            annotation_id=annotation.id,
            items=[
                SkuQueryJudgmentInput(query_text="милая кружка", label="highly_relevant", reviewer="qa"),
                SkuQueryJudgmentInput(query_text="кружка для чая", label="too_broad", reviewer="qa"),
            ],
        )
        second = save_query_judgments(
            session,
            project_id=1,
            category_id=812,
            nm_id=1001,
            annotation_id=annotation.id,
            items=[SkuQueryJudgmentInput(query_text="кружка для чая", label="conflict", reviewer="qa")],
        )
        session.commit()

        assert len(first) == 2
        assert second[0].label == "conflict"

        exported = export_eval_dataset(
            session,
            project_id=1,
            request=SkuMeaningEvalExportRequest(category_id=812, include_drafts=False, format="jsonl"),
            actor="qa",
        )

        assert exported.exported_count == 1
        assert '"schema_version": "eval_dataset_v0"' in exported.content
        assert exported.items[0]["sku_meaning"]["expressive"]["vibes"] == ["милая"]
        assert len(exported.items[0]["query_judgments"]) == 2
    finally:
        session.close()
