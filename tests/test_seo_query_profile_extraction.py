from __future__ import annotations

from app.services.seo.query_pipeline import run_query_hybrid_annotation, run_query_profile_extraction
from app.services.seo.query_pipeline.clustering import PersistedQueryClusterView
from app.services.seo.query_pipeline.profiles import (
    _MarkerAggregate,
    _MarkerOccurrence,
    _apply_product_noun_guard,
    _build_profile_label,
    _select_product_markers,
)
from app.services.seo.query_pipeline.diagnostics import QueryProfileMarker, QueryProfileMarkerDecision

from app.models import SeoQueryCluster

from seo_query_pipeline_test_helpers import (
    add_term_query,
    cluster_id_for_query,
    delete_empty_clusters,
    make_session,
    move_query_to_cluster,
    refresh_cluster_stats,
    run_base_pipeline,
    seed_scope_data,
)


def _find_profile(result, needle: str):
    needle = needle.lower()
    return next(
        profile
        for profile in result.profiles
        if needle in (profile.profile_label_candidate or "").lower()
        or needle in (profile.source_anchor_query or "").lower()
        or any(needle in query.lower() for query in profile.source_query_examples)
    )


def test_profile_extraction_separates_product_use_case_and_attributes():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=18, search_text="тарелки для супа", frequency=50)
        add_term_query(session, nm_id=19, search_text="тарелка для супа", frequency=30)
        add_term_query(session, nm_id=20, search_text="для супа тарелки", frequency=20)
        add_term_query(session, nm_id=21, search_text="тарелки для супа синие", frequency=10)
        add_term_query(session, nm_id=22, search_text="тарелка для супа 255мм", frequency=8)

        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_profile_extraction(
            session,
            project_id=1,
            category_id=821,
            refresh_hybrid=False,
            persist=False,
        )

        profile = _find_profile(result, "для супа")
        assert profile.profile_strength in {"strong", "medium"}
        assert profile.profile_confidence >= 0.5
        assert profile.product_type_markers
        assert profile.product_type_markers[0].normalized_value.startswith("тарел")
        assert any(marker.normalized_value == "для супа" for marker in profile.use_case_markers)
        assert any(marker.family == "size" for marker in profile.attribute_markers)
        assert all(marker.family not in {"color", "size"} for marker in profile.use_case_markers)
        assert any(decision.selected and decision.slot == "product_type" for decision in profile.marker_decisions)
        assert any(
            not decision.selected and decision.reason.startswith("rejected")
            for decision in profile.marker_decisions
        )
        assert result.diagnostics.total_profiles_built == len(result.profiles)
        assert result.diagnostics.counts_by_marker_type["product_type"] >= 1
    finally:
        session.close()


def test_profile_extraction_keeps_microwave_phrase_as_use_case_not_product_type():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=18, search_text="тарелка для микроволновки", frequency=40)
        add_term_query(session, nm_id=19, search_text="тарелки для микроволновки", frequency=22)
        add_term_query(session, nm_id=20, search_text="тарелка для микроволновки 255мм", frequency=12)
        add_term_query(session, nm_id=21, search_text="для микроволновки тарелка", frequency=10)

        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_profile_extraction(
            session,
            project_id=1,
            category_id=821,
            refresh_hybrid=False,
            persist=False,
        )

        profile = _find_profile(result, "микроволновки")
        assert any(marker.normalized_value == "для микроволновки" for marker in profile.use_case_markers)
        assert profile.product_type_markers
        assert all("микроволнов" not in marker.normalized_value for marker in profile.product_type_markers)
        assert not any("микроволнов" in marker.normalized_value for marker in profile.attribute_markers)
        assert any(
            decision.slot == "use_case" and decision.selected and decision.normalized_value == "для микроволновки"
            for decision in profile.marker_decisions
        )
    finally:
        session.close()


def test_profile_extraction_keeps_product_after_use_case_reordering():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=18, search_text="для кухни тарелки", frequency=40)
        add_term_query(session, nm_id=19, search_text="тарелки для кухни", frequency=35)
        add_term_query(session, nm_id=20, search_text="тарелка для кухни", frequency=18)

        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        result = run_query_profile_extraction(
            session,
            project_id=1,
            category_id=821,
            refresh_hybrid=False,
            persist=False,
        )

        profile = _find_profile(result, "для кухни")
        assert profile.product_type_markers
        assert profile.product_type_markers[0].normalized_value.startswith("тарел")
        assert any(marker.normalized_value == "для кухни" for marker in profile.use_case_markers)
        assert all("тарел" not in marker.normalized_value for marker in profile.use_case_markers)
        assert "тарел" in (profile.profile_label_candidate or "").lower()
    finally:
        session.close()


def test_profile_extraction_downgrades_broad_and_conflicting_clusters():
    session = make_session()
    try:
        seed_scope_data(session)
        add_term_query(session, nm_id=18, search_text="тарелка белая", frequency=18)
        add_term_query(session, nm_id=19, search_text="тарелка красная", frequency=17)
        add_term_query(session, nm_id=20, search_text="тарелка синяя", frequency=16)
        add_term_query(session, nm_id=21, search_text="тарелка для супа", frequency=15)
        add_term_query(session, nm_id=22, search_text="тарелка для микроволновки", frequency=14)

        run_base_pipeline(session)
        run_query_hybrid_annotation(session, project_id=1, category_id=821, persist=True)
        target_cluster_id = cluster_id_for_query(session, "для дома")
        for query_text, query_type in (
            ("тарелка белая", "head"),
            ("тарелка красная", "head"),
            ("тарелка синяя", "head"),
            ("тарелка для супа", "mid"),
            ("тарелка для микроволновки", "mid"),
        ):
            move_query_to_cluster(session, query_text=query_text, target_cluster_id=target_cluster_id, query_type=query_type)
        delete_empty_clusters(session)
        refresh_cluster_stats(session, target_cluster_id)
        target_cluster_key = str(session.get(SeoQueryCluster, target_cluster_id).cluster_key)
        result = run_query_profile_extraction(
            session,
            project_id=1,
            category_id=821,
            refresh_hybrid=False,
            persist=False,
        )

        profile = next(profile for profile in result.profiles if profile.cluster_key == target_cluster_key)
        assert profile.profile_strength in {"weak", "empty"}
        assert profile.profile_confidence < 0.45
        assert "thin_evidence" in profile.quality_flags
        assert profile.confidence_factors["weak_evidence"] is True
        assert result.diagnostics.profiles_with_low_confidence
    finally:
        session.close()


def test_product_selection_falls_back_to_evidence_when_anchor_candidate_is_wrong():
    def _aggregate(normalized_value: str, query_texts: list[str], *, is_anchor: bool = False) -> _MarkerAggregate:
        aggregate = _MarkerAggregate(slot="product_type", normalized_value=normalized_value, family=None)
        for index, query_text in enumerate(query_texts):
            aggregate.add(
                _MarkerOccurrence(
                    raw_value=normalized_value,
                    normalized_value=normalized_value,
                    family=None,
                    query_text=query_text,
                    source_kind="individual" if is_anchor else "cluster",
                    position=index,
                    is_anchor=is_anchor,
                ),
                is_anchor_head=False,
            )
        return aggregate

    aggregates = [
        _aggregate("тарелки", ["тарелки для кухни", "тарелка для кухни"]),
        _aggregate("кухни", ["для кухни тарелки"], is_anchor=True),
    ]

    markers, decisions, _flags, anchor_aligned = _select_product_markers(
        aggregates,
        total_evidence_queries=3,
        anchor_head_candidate="кухни",
        anchor_candidates={"кухни"},
    )

    assert markers
    assert markers[0].normalized_value == "тарелки"
    assert anchor_aligned is False
    assert any(decision.selected and decision.reason == "selected_evidence_fallback" for decision in decisions)


def test_product_noun_guard_rejects_adjective_only_candidate_and_label_stays_empty():
    selected_markers = [
        QueryProfileMarker(
            value="одноразовые",
            normalized_value="одноразовые",
            family=None,
            support_query_count=1,
            support_share=1.0,
            weighted_support=1.0,
            evidence_queries=["одноразовые"],
        )
    ]
    decisions = [
        QueryProfileMarkerDecision(
            slot="product_type",
            value="одноразовые",
            normalized_value="одноразовые",
            family=None,
            support_query_count=1,
            support_ratio=1.0,
            evidence_queries=["одноразовые"],
            source_kinds=["individual"],
            selected=True,
            reason="selected_evidence_fallback",
        )
    ]
    guarded_markers, guarded_decisions = _apply_product_noun_guard(
        selected_markers,
        decisions,
        anchor_noun_candidates=set(),
    )

    assert guarded_markers == []
    assert guarded_decisions[0].reason == "rejected_non_noun_product_candidate"
    assert guarded_decisions[0].selected is False

    label = _build_profile_label(
        cluster=PersistedQueryClusterView(
            project_id=1,
            category_id=821,
            cluster_id=1,
            cluster_key="cluster",
            cluster_label_candidate="одноразовые",
            top_query_text="одноразовые",
            query_count=1,
            head_query_count=1,
            mid_query_count=0,
            tail_query_count=0,
            members=[],
        ),
        product_type_markers=[],
        use_case_markers=[],
        attribute_markers=[
            QueryProfileMarker(
                value="одноразовые",
                normalized_value="одноразовые",
                family="format",
                support_query_count=1,
                support_share=1.0,
                weighted_support=1.0,
                evidence_queries=["одноразовые"],
            )
        ],
    )
    assert label == ""
