from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import settings
from app.services.review_opinion.contracts import review_opinion_json_schema
from app.services.review_opinion.input_builder import normalize_text
from app.services.review_opinion.openrouter_client import OpenRouterOpinionClient
from app.services.review_opinion.validation import (
    ReviewOpinionOutputError,
    parse_strict_json,
    validate_and_normalize_output,
)
from app.schemas.wb_review_opinion import ReviewOpinionGenerateRequest


def _finding(*, review_ids: list[str], quote: str = "очень удобный") -> dict:
    return {
        "label": "Удобство",
        "category": "product",
        "summary": "Покупатели считают товар удобным.",
        "confidence": "high",
        "supporting_review_ids": review_ids,
        "evidence": [{"review_id": review_ids[0], "quote": quote}],
    }


def _output(finding: dict) -> dict:
    return {
        "schema_version": "wb_customer_opinion_v1",
        "overall_conclusion": "Покупатели отмечают удобство товара.",
        "strengths": [finding],
        "weaknesses": [],
        "isolated_observations": [],
        "conflicts": [],
    }


def test_strict_parser_rejects_markdown_fences() -> None:
    with pytest.raises(ReviewOpinionOutputError, match="invalid_json"):
        parse_strict_json('```json\n{"schema_version":"wb_customer_opinion_v1"}\n```')


def test_validation_checks_exact_quote_and_calculates_support() -> None:
    result, validation = validate_and_normalize_output(
        _output(_finding(review_ids=["r_0001", "r_0002"])),
        review_fields={
            "r_0001": ("Товар очень удобный в дороге",),
            "r_0002": ("Пользоваться удобно каждый день",),
        },
    )

    assert result["strengths"][0]["support_count"] == 2
    assert result["strengths"][0]["evidence"][0]["quote"] == "очень удобный"
    assert validation["evidence_quotes_valid"] is True


def test_single_review_theme_is_moved_to_isolated_observations() -> None:
    result, _ = validate_and_normalize_output(
        _output(_finding(review_ids=["r_0001"])),
        review_fields={"r_0001": ("Товар очень удобный в дороге",)},
    )

    assert result["strengths"] == []
    assert result["isolated_observations"][0]["sentiment"] == "positive"


def test_validation_rejects_unknown_review_and_invented_quote() -> None:
    with pytest.raises(ReviewOpinionOutputError) as caught:
        validate_and_normalize_output(
            _output(_finding(review_ids=["r_unknown"], quote="выдуманная цитата")),
            review_fields={"r_0001": ("Настоящий текст",)},
        )

    assert "unknown_supporting_review_ids" in str(caught.value)
    assert "unknown_evidence_review_id" in str(caught.value)


def test_normalize_text_redacts_contacts() -> None:
    value = normalize_text(
        "Пишите  test@example.com  или +7 (999) 123-45-67, всё отлично"
    )

    assert "test@example.com" not in value
    assert "999" not in value
    assert "[email удалён]" in value
    assert "[телефон удалён]" in value


def test_openrouter_payload_requires_strict_json_schema(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-only-key")
    client = OpenRouterOpinionClient(
        model="openai/gpt-5.6-terra",
        reasoning_effort="medium",
    )

    payload = client._payload(  # noqa: SLF001 - contract-level payload test
        {"reviews": []},
        retry_errors=None,
    )

    assert payload["model"] == "openai/gpt-5.6-terra"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["provider"] == {"require_parameters": True}
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_model_schema_forbids_unknown_fields() -> None:
    schema = review_opinion_json_schema()

    assert schema["additionalProperties"] is False
    finding_schema = schema["$defs"]["ReviewOpinionFinding"]
    assert finding_schema["additionalProperties"] is False
    assert "support_count" not in json.dumps(schema)


def test_persistence_signatures_keep_operator_id_only_on_create() -> None:
    from app.db_wb_review_opinion import (
        create_review_opinion_run,
        find_cached_review_opinion_run,
    )

    cached_parameters = inspect.signature(
        find_cached_review_opinion_run
    ).parameters
    create_parameters = inspect.signature(create_review_opinion_run).parameters

    assert list(cached_parameters)[:2] == ["project_id", "nm_id"]
    assert "requested_by_user_id" not in cached_parameters
    assert "requested_by_user_id" in create_parameters


def test_state_read_does_not_enqueue_model_request(monkeypatch) -> None:
    from app.routers import wb_review_opinion as api

    analysis_input = SimpleNamespace(
        reviews_total=5,
        reviews_with_text=3,
        reviews_sent=3,
        input_hash="hash",
    )
    delay_calls: list[int] = []
    monkeypatch.setattr(api, "build_review_opinion_input", lambda *_: analysis_input)
    monkeypatch.setattr(
        api,
        "get_latest_review_opinion_runs",
        lambda *_: {"latest": None, "latest_ready": None},
    )
    monkeypatch.setattr(
        api.execute_review_opinion_task,
        "delay",
        lambda run_id: delay_calls.append(run_id),
    )

    state = asyncio.run(
        api.get_customer_opinion(
            project_id=1,
            nm_id=291945877,
            membership={"role": "member"},
        )
    )

    assert state.reviews_with_text == 3
    assert state.can_generate is True
    assert delay_calls == []


def test_generate_enqueues_only_after_explicit_command(monkeypatch) -> None:
    from app.routers import wb_review_opinion as api

    analysis_input = SimpleNamespace(
        reviews_total=5,
        reviews_with_text=3,
        reviews_sent=3,
        input_hash="hash",
    )
    now = datetime.now(timezone.utc)
    run = {
        "id": 42,
        "status": "queued",
        "reviews_total": 5,
        "reviews_with_text": 3,
        "reviews_sent": 3,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "error_code": None,
        "error_message": None,
    }
    delay_calls: list[int] = []
    monkeypatch.setattr(settings, "WB_REVIEW_OPINION_ENABLED", True)
    monkeypatch.setattr(api, "build_review_opinion_input", lambda *_: analysis_input)
    monkeypatch.setattr(api, "find_active_review_opinion_run", lambda *_: None)
    monkeypatch.setattr(api, "find_cached_review_opinion_run", lambda *_, **__: None)
    monkeypatch.setattr(api, "create_review_opinion_run", lambda **_: run)
    monkeypatch.setattr(
        api.execute_review_opinion_task,
        "delay",
        lambda run_id: delay_calls.append(run_id),
    )

    response = asyncio.run(
        api.generate_customer_opinion(
            ReviewOpinionGenerateRequest(refresh=False),
            project_id=1,
            nm_id=291945877,
            membership={"role": "member", "user_id": 7},
        )
    )

    assert response.run.id == 42
    assert delay_calls == [42]
