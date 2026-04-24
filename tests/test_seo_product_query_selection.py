from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SeoSkuQuerySet, SeoSkuQuerySetItem
from app.schemas.seo_products import SeoQuerySelectionUpdateItem, SeoQuerySelectionUpdateRequest
from app.services.seo.products import get_query_selection, update_query_selection


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["projects"],
            Base.metadata.tables["seo_sku_query_sets"],
            Base.metadata.tables["seo_sku_query_set_items"],
        ],
    )
    session = Session(engine)
    session.execute(Base.metadata.tables["projects"].insert().values(id=1))
    session.commit()
    return session


def _seed_confirmed_query_set(session: Session) -> SeoSkuQuerySet:
    query_set = SeoSkuQuerySet(
        project_id=1,
        category_id=812,
        nm_id=535441190,
        status="confirmed",
        matcher_version="matcher-test",
        atoms_version="atoms-test",
        source_hash="source-test",
    )
    session.add(query_set)
    session.flush()
    session.add_all(
        [
            SeoSkuQuerySetItem(
                query_set_id=int(query_set.id),
                normalized_query_text="кружка с капибарой",
                display_query="кружка с капибарой",
                bucket="primary",
                score=1,
                selection_state="auto_selected",
                reasons_payload={"user_reasons": ["test"]},
            ),
            SeoSkuQuerySetItem(
                query_set_id=int(query_set.id),
                normalized_query_text="кружка для кофе",
                display_query="кружка для кофе",
                bucket="broad",
                score=0.2,
                selection_state="excluded",
                reasons_payload={"user_reasons": ["too broad"]},
            ),
        ]
    )
    session.commit()
    return query_set


def test_update_selection_edits_confirmed_set_via_working_copy() -> None:
    session = _make_session()
    try:
        _seed_confirmed_query_set(session)

        draft = update_query_selection(
            session,
            project_id=1,
            nm_id=535441190,
            request=SeoQuerySelectionUpdateRequest(
                category_id=812,
                status="draft",
                items=[
                    SeoQuerySelectionUpdateItem(
                        normalized_query_text="кружка для кофе",
                        selection_state="auto_selected",
                    )
                ],
            ),
        )
        session.commit()

        assert draft.status == "draft"
        assert {item.normalized_query_text for item in draft.items} == {"кружка с капибарой", "кружка для кофе"}
        assert next(item for item in draft.items if item.normalized_query_text == "кружка для кофе").selection_state == "auto_selected"

        confirmed = update_query_selection(
            session,
            project_id=1,
            nm_id=535441190,
            request=SeoQuerySelectionUpdateRequest(
                category_id=812,
                status="confirmed",
                items=[
                    SeoQuerySelectionUpdateItem(
                        normalized_query_text="кружка с капибарой",
                        selection_state="excluded",
                    )
                ],
            ),
        )
        session.commit()

        rows = session.scalars(select(SeoSkuQuerySet)).all()
        assert [row.status for row in rows] == ["confirmed"]
        assert confirmed.status == "confirmed"
        assert next(item for item in confirmed.items if item.normalized_query_text == "кружка с капибарой").selection_state == "excluded"
        assert next(item for item in confirmed.items if item.normalized_query_text == "кружка для кофе").selection_state == "auto_selected"
    finally:
        session.close()


def test_get_query_selection_prefers_latest_working_set() -> None:
    session = _make_session()
    try:
        _seed_confirmed_query_set(session)
        draft = update_query_selection(
            session,
            project_id=1,
            nm_id=535441190,
            request=SeoQuerySelectionUpdateRequest(
                category_id=812,
                status="draft",
                items=[
                    SeoQuerySelectionUpdateItem(
                        normalized_query_text="кружка для кофе",
                        selection_state="auto_selected",
                    )
                ],
            ),
        )
        session.commit()

        current = get_query_selection(session, project_id=1, category_id=812, nm_id=535441190)

        assert current.id == draft.id
        assert current.status == "draft"
        assert len(current.items) == 2
    finally:
        session.close()
