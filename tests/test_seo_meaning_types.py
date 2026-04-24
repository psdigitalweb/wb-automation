from __future__ import annotations

import json


def test_category_meaning_shape_and_serialization():
    from app.services.seo.meaning_extraction import CategoryMeaning

    meaning = CategoryMeaning(project_id=1, category_id=821)
    payload = meaning.to_dict()

    assert payload["project_id"] == 1
    assert payload["category_id"] == 821
    assert payload["version"] == "v1_mvp"
    assert "functional" in payload
    assert "expressive" in payload
    assert payload["functional"]["product_types"] == []
    assert payload["functional"]["use_cases"] == []
    assert payload["functional"]["attributes"] == []
    assert payload["expressive"]["vibes"] == []

    json.dumps(payload, ensure_ascii=False)


def test_product_projection_shape_and_serialization():
    from app.services.seo.meaning_extraction import ProductProjection

    projection = ProductProjection(project_id=1, category_id=821, nm_id=38802116)
    payload = projection.to_dict()

    assert payload["project_id"] == 1
    assert payload["category_id"] == 821
    assert payload["nm_id"] == 38802116
    assert payload["version"] == "v1_mvp"
    assert payload["functional"]["product_type"] is None
    assert payload["functional"]["use_cases"] == []
    assert payload["functional"]["attributes"] == []
    assert payload["expressive"]["vibes"] == []

    json.dumps(payload, ensure_ascii=False)


def test_query_meaning_shape_and_serialization():
    from app.services.seo.meaning_extraction import QueryMeaning

    meaning = QueryMeaning(project_id=1, category_id=821, cluster_key="k:1")
    payload = meaning.to_dict()

    assert payload["project_id"] == 1
    assert payload["category_id"] == 821
    assert payload["cluster_key"] == "k:1"
    assert payload["version"] == "v1_mvp"
    assert payload["functional"]["product_type"] is None
    assert payload["functional"]["use_cases"] == []
    assert payload["functional"]["attributes"] == []
    assert payload["expressive"]["vibes"] == []

    json.dumps(payload, ensure_ascii=False)


def test_normalization_dedupes_lists_and_strips_values():
    from app.services.seo.meaning_extraction import (
        CategoryExpressiveMeaning,
        CategoryFunctionalMeaning,
        CategoryMeaning,
        ProductExpressiveProfile,
        ProductFunctionalProfile,
        ProductProjection,
        QueryExpressiveIntent,
        QueryFunctionalIntent,
        QueryMeaning,
    )

    category = CategoryMeaning(
        project_id=1,
        category_id=821,
        functional=CategoryFunctionalMeaning(product_types=["тарелка", "тарелка", " "], use_cases=["для супа", "для супа"], attributes=["керамика", "керамика"]),
        expressive=CategoryExpressiveMeaning(vibes=["aesthetic", "aesthetic", ""]),
    )
    assert category.to_dict()["functional"]["product_types"] == ["тарелка"]
    assert category.to_dict()["expressive"]["vibes"] == ["aesthetic"]

    projection = ProductProjection(
        project_id=1,
        category_id=821,
        nm_id=1,
        functional=ProductFunctionalProfile(product_type=" тарелка ", use_cases=["для супа", "для супа"], attributes=["керамика", "керамика"]),
        expressive=ProductExpressiveProfile(vibes=["premium", "premium"]),
    )
    assert projection.to_dict()["functional"]["product_type"] == "тарелка"
    assert projection.to_dict()["expressive"]["vibes"] == ["premium"]

    query = QueryMeaning(
        project_id=1,
        category_id=821,
        cluster_key="k",
        functional=QueryFunctionalIntent(product_type=" тарелка ", use_cases=["для супа", "для супа"], attributes=["керамика", "керамика"]),
        expressive=QueryExpressiveIntent(vibes=["premium", "premium"]),
    )
    assert query.to_dict()["functional"]["product_type"] == "тарелка"
    assert query.to_dict()["expressive"]["vibes"] == ["premium"]

