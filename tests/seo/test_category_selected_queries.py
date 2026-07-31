"""Tests for operator-maintained category selected query lists."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoCategorySelectedQuery, SeoSkuQuerySet, SeoSkuQuerySetItem
from app.schemas.seo_products import SeoCategorySelectedQuerySaveRequest
from app.services.seo.products import (
    apply_category_selected_queries_to_product,
    list_category_selected_queries,
    save_category_selected_queries,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.tables["projects"].create(engine)
    SeoSkuQuerySet.__table__.create(engine)
    SeoSkuQuerySetItem.__table__.create(engine)
    SeoCategorySelectedQuery.__table__.create(engine)
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.commit()
    return session


def test_save_category_selected_queries_normalizes_deduplicates_and_preserves_order() -> None:
    session = _session()

    response = save_category_selected_queries(
        session,
        project_id=1,
        category_id=812,
        request=SeoCategorySelectedQuerySaveRequest(
            queries=[" Кружка  Капибара ", "кружка капибара", "", "Милая кружка"]
        ),
    )

    assert [item.query_text for item in response.items] == ["кружка капибара", "милая кружка"]
    assert [item.sort_order for item in response.items] == [0, 1]


def test_list_category_selected_queries_includes_saved_sku_query_sets() -> None:
    session = _session()
    save_category_selected_queries(
        session,
        project_id=1,
        category_id=812,
        request=SeoCategorySelectedQuerySaveRequest(queries=["кружка капибара"]),
    )
    query_set = SeoSkuQuerySet(project_id=1, category_id=812, nm_id=123, status="confirmed")
    session.add(query_set)
    session.flush()
    session.add_all(
        [
            SeoSkuQuerySetItem(
                query_set_id=query_set.id,
                normalized_query_text="кружка капибара",
                display_query="кружка капибара",
                bucket="primary",
                ranking_value_used=10,
                selection_state="auto_selected",
                reasons_payload={},
            ),
            SeoSkuQuerySetItem(
                query_set_id=query_set.id,
                normalized_query_text="подарочная кружка",
                display_query="Подарочная кружка",
                bucket="primary",
                ranking_value_used=25,
                selection_state="pinned",
                reasons_payload={},
            ),
            SeoSkuQuerySetItem(
                query_set_id=query_set.id,
                normalized_query_text="лишний запрос",
                display_query="лишний запрос",
                bucket="rejected",
                selection_state="excluded",
                reasons_payload={},
            ),
        ]
    )
    session.flush()

    response = list_category_selected_queries(session, project_id=1, category_id=812)

    assert [item.query_text for item in response.items] == ["кружка капибара", "подарочная кружка"]
    assert [item.source for item in response.items] == ["category_list", "saved_sku"]
    assert [item.ranking_value_used for item in response.items] == [10, 25]
    assert response.items[1].sku_count == 1


def test_apply_category_selected_queries_creates_confirmed_query_set() -> None:
    session = _session()
    save_category_selected_queries(
        session,
        project_id=1,
        category_id=812,
        request=SeoCategorySelectedQuerySaveRequest(queries=["кружка капибара", "милая кружка"]),
    )

    response = apply_category_selected_queries_to_product(session, project_id=1, category_id=812, nm_id=123)

    assert response.status == "confirmed"
    assert response.matcher_version == "category_selected_queries"
    assert [item.display_query for item in response.items] == ["кружка капибара", "милая кружка"]
    assert {item.bucket for item in response.items} == {"primary"}
    assert {item.selection_state for item in response.items} == {"auto_selected"}


def test_apply_category_selected_queries_can_apply_checked_subset() -> None:
    session = _session()
    save_category_selected_queries(
        session,
        project_id=1,
        category_id=812,
        request=SeoCategorySelectedQuerySaveRequest(
            queries=["кружка капибара", "милая кружка", "подарочная кружка"]
        ),
    )

    response = apply_category_selected_queries_to_product(
        session,
        project_id=1,
        category_id=812,
        nm_id=123,
        query_texts=[" Милая   кружка ", "подарочная кружка"],
    )

    assert [item.display_query for item in response.items] == ["милая кружка", "подарочная кружка"]


def test_apply_category_selected_queries_rejects_empty_checked_subset() -> None:
    session = _session()
    save_category_selected_queries(
        session,
        project_id=1,
        category_id=812,
        request=SeoCategorySelectedQuerySaveRequest(queries=["кружка капибара"]),
    )

    try:
        apply_category_selected_queries_to_product(
            session,
            project_id=1,
            category_id=812,
            nm_id=123,
            query_texts=[],
        )
    except ValueError as exc:
        assert "Выберите хотя бы один запрос" in str(exc)
    else:
        raise AssertionError("empty category selected subset should fail")
