from __future__ import annotations

from decimal import Decimal

from scripts.experiments.seo_dedupe_cluster_representatives_812 import (
    Representative,
    canonical_signature,
    dedupe_representatives,
)


def test_canonical_signature_removes_only_service_tokens_and_sorts() -> None:
    assert canonical_signature("Подарок для дома") == "дома подарок"


def test_dedupe_keeps_highest_ranking_representative() -> None:
    representatives = [
        Representative(cluster_id=1, query="подарок для дома", ranking_value_used=Decimal("700")),
        Representative(cluster_id=2, query="дома подарок", ranking_value_used=Decimal("900")),
        Representative(cluster_id=3, query="подарок коллеге", ranking_value_used=Decimal("800")),
    ]

    kept, groups = dedupe_representatives(representatives)

    assert [item.cluster_id for item in kept] == [2, 3]
    assert len(groups) == 1
    assert groups[0].kept.cluster_id == 2
    assert [item.cluster_id for item in groups[0].removed] == [1]


def test_dedupe_does_not_merge_different_intents() -> None:
    representatives = [
        Representative(cluster_id=1, query="подарок подруге", ranking_value_used=Decimal("700")),
        Representative(cluster_id=2, query="подарок любимой", ranking_value_used=Decimal("900")),
        Representative(cluster_id=3, query="подарок для чая", ranking_value_used=Decimal("800")),
        Representative(cluster_id=4, query="подарок для кофе", ranking_value_used=Decimal("850")),
    ]

    kept, groups = dedupe_representatives(representatives)

    assert len(kept) == 4
    assert groups == []
