from __future__ import annotations

from app.services.seo.expressive_llm.category_input_builder import build_category_expressive_input
from app.services.seo.expressive_llm.models import ReviewSnippet


def test_category_input_builder_dedup_truncate_and_caps_reviews_and_titles():
    reviews = [
        ReviewSnippet(project_id=1, nm_id=1, rating=5, text="  Привет  "),
        ReviewSnippet(project_id=1, nm_id=2, rating=5, text="привет"),  # duplicate by key (case/space)
        ReviewSnippet(project_id=1, nm_id=3, rating=5, text="Ёлка"),  # key uses ё→е
        ReviewSnippet(project_id=1, nm_id=4, rating=5, text="Елка"),  # duplicate by key
        ReviewSnippet(project_id=1, nm_id=5, rating=5, text="x" * 500),  # truncation
        ReviewSnippet(project_id=1, nm_id=6, rating=5, text="ok"),  # short is kept
    ]
    titles = ["  Title  ", "title", "t" * 1000]

    built = build_category_expressive_input(
        category_name="  Маркеры ",
        reviews=reviews,
        titles=titles,
        max_reviews=3,
        max_review_chars=10,
        max_title_chars=12,
    )

    assert built.payload["category_name"] == "Маркеры"
    assert built.payload["reviews"] == ["Привет", "Ёлка", "xxxxxxxxxx"]
    assert built.payload["titles"] == ["Title", "tttttttttttt"]
    assert built.reviews_count == 3
    assert built.titles_count == 2

    # Evidence text is built from reviews only.
    assert built.evidence_text == "Привет\nЁлка\nxxxxxxxxxx"


def test_category_input_hash_is_stable_for_same_payload():
    reviews = [ReviewSnippet(project_id=1, nm_id=1, rating=5, text=" A ")]
    a = build_category_expressive_input(category_name="Cat", reviews=reviews, titles=["T"])
    b = build_category_expressive_input(category_name="Cat", reviews=reviews, titles=["T"])
    assert a.input_hash == b.input_hash

