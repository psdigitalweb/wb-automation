from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem
from app.services.seo.category_profile import CategoryProfile, ProfileMissingError
from app.services.seo.matcher_v2 import api as matcher_v2_api
from app.services.seo.matcher_v2.stages.bucket_cap import decide_bucket
from app.services.seo.matcher_v2.stages.demand_ordering import partition_buckets
from app.services.seo.matcher_v2.stages.eligibility import EligibilityVerdict, evaluate_eligibility
from app.services.seo.matcher_v2.stages.soft_score import SoftScoreResult, compute_soft_score
from app.services.seo.query_meaning_matcher.profile_matcher import (
    _FeatureSet,
    _query_features,
    _sku_features,
)


TEMPLATE_PATH = Path("config/seo/category_profiles/templates/812_skeleton_v1.json")
REPO_ROOT = Path(__file__).resolve().parents[3]
SEO_ROOT = REPO_ROOT / "src" / "app" / "services" / "seo"
MATCHER_V2_ROOT = SEO_ROOT / "matcher_v2"


def _payload() -> dict[str, Any]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _profile(*, payload: dict[str, Any] | None = None) -> CategoryProfile:
    return CategoryProfile.from_payload(
        profile_id=1,
        project_id=1,
        category_id=812,
        version="v1.812.test",
        payload=payload or _payload(),
    )


def _query_row(
    text: str,
    *,
    query_meaning_id: int = 101,
    cluster_id: int = 7,
    genericness: str = "specific",
    constraints: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=query_meaning_id,
        cluster_id=cluster_id,
        cluster_key=f"cluster-{cluster_id}",
        canonical_text=text,
        genericness=genericness,
        source_query_examples=[text],
        meaning_payload={
            "functional": {},
            "expressive": {},
            "audience": [],
            "occasion": [],
            "constraints": constraints or [],
        },
        constraints=constraints or [],
    )


def _item(query_id: int, *, bucket: str, score: float) -> MeaningAwareMatcherItem:
    return MeaningAwareMatcherItem(
        query=f"query-{query_id}",
        cluster_id=query_id,
        cluster_key=f"cluster-{query_id}",
        query_meaning_id=query_id,
        bucket=bucket,  # type: ignore[arg-type]
        score=score,
        semantic_similarity=0.8,
        ranking_value_used=0.5,
        genericness="specific",
        matched_meanings=[],
        conflicts=[],
        reasons=[],
        user_bucket_label=bucket,
        user_reasons=[],
        matched_atoms=[],
        missing_atoms=[],
        conflict_atoms=[],
        debug_reasons=[],
    )


class _ScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _FakeSession:
    def __init__(self, query_rows: list[Any]) -> None:
        self.query_rows = query_rows

    def scalars(self, _stmt: Any) -> _ScalarResult:
        return _ScalarResult(self.query_rows)


def test_matcher_v2_refuses_to_run_without_active_profile() -> None:
    session = object()

    def _missing_profile(_session: Any, *, project_id: int, category_id: int) -> None:
        assert project_id == 1
        assert category_id == 812
        return None

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(matcher_v2_api, "load_active_profile", _missing_profile)
    try:
        with pytest.raises(ProfileMissingError, match="Active CategoryProfile is required"):
            matcher_v2_api.run_matcher_v2(
                session,  # type: ignore[arg-type]
                project_id=1,
                category_id=812,
                nm_id=291861306,
            )
    finally:
        monkeypatch.undo()


def test_matcher_v2_loads_active_profile_once_and_records_version(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile()
    query_rows = [_query_row("кружка капибара")]
    session = _FakeSession(query_rows)
    load_calls: list[tuple[int, int]] = []
    captured_run: dict[str, Any] = {}
    captured_finalize: dict[str, Any] = {}

    monkeypatch.setattr(
        matcher_v2_api,
        "load_active_profile",
        lambda _session, *, project_id, category_id: load_calls.append((project_id, category_id)) or profile,
    )
    monkeypatch.setattr(
        matcher_v2_api,
        "_get_sku_annotation",
        lambda _session, **_kwargs: SimpleNamespace(id=11, meaning_payload={}, status="ready"),
    )
    monkeypatch.setattr(
        matcher_v2_api,
        "_get_readiness",
        lambda _session, **_kwargs: SimpleNamespace(
            id=5,
            status="ready",
            queries_count=1,
            query_meanings_count=1,
            query_atoms_count=1,
            embeddings_count=1,
        ),
    )
    monkeypatch.setattr(matcher_v2_api, "_latest_atoms_row_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(matcher_v2_api, "get_atoms_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(matcher_v2_api, "merge_sku_and_vision_atoms", lambda *args, **kwargs: None)
    monkeypatch.setattr(matcher_v2_api, "_judgment_overrides_by_query", lambda *args, **kwargs: ({}, {}))
    monkeypatch.setattr(
        matcher_v2_api,
        "ensure_meaning_embedding",
        lambda *args, **kwargs: SimpleNamespace(model="test-model", embedding=[1.0, 0.0]),
    )
    monkeypatch.setattr(matcher_v2_api, "_ranking_by_cluster", lambda *args, **kwargs: {7: 0.9})
    monkeypatch.setattr(
        matcher_v2_api,
        "_sku_features",
        lambda *args, **kwargs: SimpleNamespace(canonical_text="кружка капибара"),
    )
    monkeypatch.setattr(
        matcher_v2_api,
        "_query_features",
        lambda *args, **kwargs: SimpleNamespace(canonical_text="кружка капибара"),
    )
    monkeypatch.setattr(
        matcher_v2_api,
        "evaluate_eligibility",
        lambda *args, **kwargs: EligibilityVerdict(verdict="eligible"),
    )
    monkeypatch.setattr(
        matcher_v2_api,
        "compute_soft_score",
        lambda *args, **kwargs: SoftScoreResult(
            score=0.71,
            semantic_similarity=0.9,
            genericness="specific",
            product_score=0.16,
            reasons=["score computed"],
            components={"product_score": 0.16},
        ),
    )
    monkeypatch.setattr(
        matcher_v2_api,
        "decide_bucket",
        lambda *args, **kwargs: SimpleNamespace(
            bucket="primary",
            score=0.71,
            matched_atoms=[],
            missing_atoms=[],
            conflict_atoms=[],
            reasons=["bucket decided"],
        ),
    )
    monkeypatch.setattr(matcher_v2_api, "sort_items", lambda items: items)
    monkeypatch.setattr(
        matcher_v2_api,
        "partition_buckets",
        lambda items, *, limit, category_profile: {
            "primary": list(items),
            "secondary": [],
            "broad": [],
            "rejected": [],
        },
    )

    def _create_matcher_run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured_run.update(kwargs)
        return SimpleNamespace(id=22)

    monkeypatch.setattr(matcher_v2_api, "create_matcher_run", _create_matcher_run)
    monkeypatch.setattr(
        matcher_v2_api,
        "finalize_matcher_run",
        lambda _session, run_row, *, metrics, quality_mode, degraded_reasons: captured_finalize.update(
            {
                "run_id": run_row.id,
                "metrics": metrics,
                "quality_mode": quality_mode,
                "degraded_reasons": degraded_reasons,
            }
        ),
    )
    monkeypatch.setattr(matcher_v2_api, "persist_matcher_results", lambda *args, **kwargs: [])

    bundle = matcher_v2_api.run_matcher_v2(
        session,  # type: ignore[arg-type]
        project_id=1,
        category_id=812,
        nm_id=291861306,
    )

    assert bundle.run_id == 22
    assert load_calls == [(1, 812)]
    assert captured_run["category_profile_version"] == profile.version
    assert captured_finalize["metrics"]["category_profile_version"] == profile.version
    assert captured_finalize["metrics"]["category_profile_id"] == profile.profile_id
    assert captured_finalize["metrics"]["category_profile_active"] is True


def test_eligibility_stage_uses_profile_subject_detection() -> None:
    profile = _profile()
    sku_features = _sku_features(
        {"functional": {"product_type": "кружка", "attributes": ["керамика"]}},
        profile=profile,
    )
    query_row = _query_row("термокружка с трубочкой")
    query_features = _query_features(query_row, profile=profile)

    verdict = evaluate_eligibility(
        sku_features=sku_features,
        query_features=query_features,
        query_row=query_row,  # type: ignore[arg-type]
        judgment=None,
        category_profile=profile,
    )

    assert verdict.verdict == "hard_conflict"
    assert any("thermal" in conflict for conflict in verdict.conflicts)


def test_soft_score_uses_profile_product_type_aliases() -> None:
    profile = _profile()
    sku_features = _FeatureSet(
        product_type="",
        tokens={"кружка", "капибара"},
        use_case_terms=set(),
        attribute_terms=set(),
        expressive_terms=set(),
        audience_terms=set(),
        occasion_terms=set(),
        negative_terms=set(),
        negative_audience_terms=set(),
        constraints=set(),
        materials=set(),
        canonical_text="кружка капибара",
    )
    query_features = _FeatureSet(
        product_type="кружка",
        tokens={"кружка", "капибара"},
        use_case_terms=set(),
        attribute_terms=set(),
        expressive_terms=set(),
        audience_terms=set(),
        occasion_terms=set(),
        negative_terms=set(),
        negative_audience_terms=set(),
        constraints=set(),
        materials=set(),
        canonical_text="кружка капибара",
    )

    result = compute_soft_score(
        sku_features=sku_features,
        query_features=query_features,
        semantic_similarity=0.5,
        genericness="specific",
        ranking_value=None,
        has_conflicts=False,
        category_profile=profile,
    )

    assert result.product_score == pytest.approx(
        profile.product_type_aliases["кружка"].score_bonus or 0.0
    )
    assert any("product_type compatible" in reason for reason in result.reasons)


def test_bucket_cutoffs_and_caps_use_profile_scoring() -> None:
    payload = _payload()
    payload["scoring"]["bucket_cutoffs"] = {
        "primary": 0.7,
        "secondary": 0.5,
        "broad": 0.2,
    }
    payload["scoring"]["bucket_caps"] = {
        "primary": 1,
        "secondary": 2,
        "broad": 3,
        "rejected": 4,
    }
    profile = _profile(payload=payload)

    decision = decide_bucket(
        score=0.56,
        genericness="specific",
        conflicts=[],
        semantic_similarity=0.76,
        expressive_overlap=[],
        audience_overlap=[],
        occasion_overlap=[],
        use_case_overlap=[],
        attribute_overlap=[],
        row=_query_row("кружка капибара"),  # type: ignore[arg-type]
        query_display="кружка капибара",
        ranking_value=None,
        sku_atoms=None,
        query_atoms_payload=None,
        category_profile=profile,
    )
    buckets = partition_buckets(
        [_item(1, bucket="primary", score=0.9), _item(2, bucket="primary", score=0.8)],
        limit=40,
        category_profile=profile,
    )

    assert decision.bucket == "secondary"
    assert len(buckets["primary"]) == 1


def test_no_del_category_profile_or_legacy_imports_remain() -> None:
    del_hits: list[str] = []
    for path in SEO_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "del category_profile" in text:
            del_hits.append(str(path.relative_to(REPO_ROOT)))
    assert del_hits == []

    violations: list[str] = []
    allowed_matcher_imports = {
        "CategoryBootstrapBuildingError",
        "MissingQueryMeaningLibraryError",
        "MissingSkuMeaningAnnotationError",
    }
    for path in MATCHER_V2_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            rel = path.relative_to(REPO_ROOT)
            if module.startswith("app.services.seo.query_meaning_matcher._legacy"):
                violations.append(f"{rel}:{node.lineno}: legacy module import remains")
            if module == "app.services.seo.query_meaning_matcher.matcher":
                for alias in node.names:
                    if alias.name not in allowed_matcher_imports:
                        violations.append(
                            f"{rel}:{node.lineno}: matcher helper import {alias.name!r} remains"
                        )

    assert violations == []
