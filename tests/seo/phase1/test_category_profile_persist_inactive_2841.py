from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.models import SeoCategoryProfile, SeoCategoryProfileDeriveRun
from app.services.seo.category_profile_derive import derive_category_profile


class _ScalarResult:
    def first(self) -> None:
        return None


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, item: object) -> None:
        if isinstance(item, SeoCategoryProfileDeriveRun):
            item.id = 101
        if isinstance(item, SeoCategoryProfile):
            item.id = 202
        self.added.append(item)

    def flush(self) -> None:
        self.flush_count += 1

    def scalars(self, statement: object) -> _ScalarResult:
        del statement
        return _ScalarResult()


class _Evidence:
    evidence_hash = "sha256:synthetic-persist-2841"

    def to_builder_input(self) -> dict[str, Any]:
        return {
            "project_id": 1,
            "category_id": 2841,
            "evidence_hash": self.evidence_hash,
            "corpus": {
                "query_count": 4,
                "distinct_query_count": 4,
                "top_queries_count": 4,
                "total_frequency": "100",
                "nonzero_frequency_count": 4,
                "source_payload_keys_sample": ["raw_query"],
                "economic_field_names_present": [],
                "notes": [],
            },
            "query_candidates": [
                {
                    "normalized_query": "alpha box compact",
                    "display_query": "Alpha box compact",
                    "frequency_total": "60",
                    "raw_row_count": 1,
                }
            ],
            "query_token_counts": {
                "alpha": 100,
                "alphabox": 60,
                "compact": 60,
            },
            "axes": {
                "axes_id": 2841,
                "schema_version": "category_meaning_axes_v0",
                "source": "deterministic",
                "evidence_hash": "axes-hash",
                "input_hash": "input-hash",
                "axes_payload": {
                    "product_type_axes": ["alpha", "alphabox", "compact"],
                    "synonym_groups": [{"label": "alphabox", "variants": ["alpha"]}],
                },
            },
            "diagnostics": {"status": "ready"},
        }


def test_category_2841_persist_writes_inactive_profile_and_derive_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.services.seo.category_profile_derive.read_category_profile_derive_evidence",
        lambda *args, **kwargs: _Evidence(),
    )
    monkeypatch.setattr(
        "app.services.seo.category_profile_derive._compute_subject_match_share",
        lambda *args, **kwargs: 0.75,
    )
    session = _Session()

    result = derive_category_profile(
        project_id=1,
        category_id=2841,
        session=session,  # type: ignore[arg-type]
        dry_run=False,
        out_path=tmp_path,
    )

    profiles = [item for item in session.added if isinstance(item, SeoCategoryProfile)]
    derive_runs = [item for item in session.added if isinstance(item, SeoCategoryProfileDeriveRun)]

    assert result.profile_id == 202
    assert result.derive_run_db_id == 101
    assert result.self_check.status == "passed"
    assert len(profiles) == 1
    assert profiles[0].is_active is False
    assert profiles[0].payload["self_check"]["status"] == "passed"
    assert profiles[0].payload["subject"]["primary"] == "alphabox"
    assert len(profiles[0].payload["hard_conflicts"]) == 0
    assert len(derive_runs) == 1
    assert derive_runs[0].status == "succeeded"
    assert derive_runs[0].profile_id == 202
    assert derive_runs[0].self_check_json["status"] == "passed"
    assert derive_runs[0].diff_summary["persistence"]["activated"] is False
    assert result.snapshot_path.exists()

    snapshot = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["self_check"]["status"] == "passed"
    assert snapshot["source_note"]
