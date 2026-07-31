from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.seo.category_profile_derive import derive_category_profile


class _Evidence:
    evidence_hash = "sha256:synthetic-2841"

    def to_builder_input(self) -> dict[str, object]:
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
                "economic_field_names_present": ["Заказали товаров", "Конверсия в заказ"],
                "notes": [],
            },
            "query_candidates": [
                {
                    "normalized_query": "alpha box compact",
                    "display_query": "Alpha box compact",
                    "frequency_total": "60",
                    "raw_row_count": 1,
                },
                {
                    "normalized_query": "beta case",
                    "display_query": "Beta case",
                    "frequency_total": "40",
                    "raw_row_count": 1,
                },
            ],
            "query_token_counts": {
                "alpha": 100,
                "alphabox": 60,
                "compact": 60,
                "beta": 40,
                "case": 40,
            },
            "axes": {
                "axes_id": 2841,
                "schema_version": "category_meaning_axes_v0",
                "source": "deterministic",
                "evidence_hash": "axes-hash",
                "input_hash": "input-hash",
                "axes_payload": {
                    "product_type_axes": ["alpha", "alphabox", "compact", "beta case"],
                    "audience_axes": ["compact"],
                    "synonym_groups": [{"label": "alphabox", "variants": ["alpha"]}],
                },
            },
            "diagnostics": {"status": "ready"},
        }


def test_category_2841_dry_run_writes_artifacts_without_persistence(
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
    out_path = tmp_path / "derive_dry_run.json"

    result = derive_category_profile(
        project_id=1,
        category_id=2841,
        session=None,  # type: ignore[arg-type]
        dry_run=True,
        out_path=out_path,
    )

    assert result.profile_id is None
    assert result.derive_run_db_id is None
    assert result.profile_payload["schema_version"] == "category_profile_v1"
    assert result.self_check.status == "passed"
    assert out_path.exists()
    assert (tmp_path / "profile_self_check.json").exists()
    assert (tmp_path / "corpus_health.json").exists()
    assert (tmp_path / "category_axes_snapshot.json").exists()
    assert (tmp_path / "derive_diagnostics.json").exists()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["self_check"]["status"] == "passed"
    assert payload["source_note"]
    assert payload["subject"]["primary"] == "alphabox"
    assert "alphabox" not in {
        item["subject"] for item in payload["subject"]["related_but_different"]
    }
    assert "alphabox" not in {
        rule["when_query_has"]["product_type"]
        for rule in payload["hard_conflicts"]
        if "product_type" in rule["when_query_has"]
    }
    assert "compact" not in {
        item["subject"] for item in payload["subject"]["related_but_different"]
    }
    skipped = {
        item["axis"]: item
        for item in payload["generated_by"]["builder_diagnostics"]["related_product_type_axes"]["skipped"]
    }
    assert skipped["compact"]["reason"] == "cooccurring_modifier_without_standalone_product_evidence"
    assert skipped["compact"]["evidence"]["standalone_phrase_count"] == 0
    assert payload["generated_by"]["builder_diagnostics"]["economic_fields_used_for_build_decisions"] is False
