from __future__ import annotations

from sqlalchemy import Column, Integer, Table, create_engine, inspect

from app.db import Base
from app.models import CATEGORY_SCOPE_COMMENT
from app.services.seo import cluster_skus_placeholder, get_default_score_weights


EXPECTED_SEO_TABLES = {
    "seo_query_batches",
    "seo_queries_raw",
    "seo_queries_normalized",
    "seo_query_clusters",
    "seo_query_annotations",
    "seo_query_annotation_versions",
    "seo_sku_cluster_runs",
    "seo_sku_clusters",
    "seo_sku_cluster_assignments",
    "seo_cluster_profiles",
    "seo_cluster_profile_versions",
    "seo_score_runs",
    "seo_query_scores",
    "seo_score_explanations",
    "seo_content_versions",
    "seo_generation_runs",
}


def _ensure_projects_stub() -> None:
    if "projects" not in Base.metadata.tables:
        Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


def test_phase1_seo_tables_are_registered_in_base_metadata():
    missing = EXPECTED_SEO_TABLES.difference(Base.metadata.tables)
    assert not missing, f"Missing SEO tables in Base.metadata: {sorted(missing)}"


def test_phase1_seo_tables_can_be_created_after_reconciliation():
    _ensure_projects_stub()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    table_names = sorted(EXPECTED_SEO_TABLES | {"projects"})
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in table_names])

    created_tables = set(inspect(engine).get_table_names())
    missing = EXPECTED_SEO_TABLES.difference(created_tables)
    assert not missing, f"Missing created SEO tables: {sorted(missing)}"


def test_foundation_contract_keeps_category_scope_comment_and_placeholder_services():
    for table_name in EXPECTED_SEO_TABLES:
        table = Base.metadata.tables[table_name]
        if "category_id" in table.c:
            assert table.c.category_id.comment == CATEGORY_SCOPE_COMMENT

    weights = get_default_score_weights().to_dict()
    assert set(weights) == {
        "semantic_similarity",
        "product_type_match",
        "attribute_match",
        "use_case_match",
        "behavior_score",
        "frequency_score",
        "product_type_mismatch",
        "attribute_mismatch",
        "cluster_mismatch",
        "competition_penalty",
    }

    cluster_result = cluster_skus_placeholder([])
    assert cluster_result["status"] == "placeholder"
    assert cluster_result["noise_strategy"]["other_cluster"] == "enabled"
