"""Orchestration for one operator-triggered review-opinion run."""

from __future__ import annotations

from typing import Any

from app.db_wb_review_opinion import (
    finish_review_opinion_failed,
    finish_review_opinion_ready,
    get_review_opinion_run,
    mark_review_opinion_running,
    update_review_opinion_input,
)

from .input_builder import build_review_opinion_input
from .openrouter_client import OpenRouterOpinionClient
from .validation import (
    ReviewOpinionOutputError,
    parse_strict_json,
    validate_and_normalize_output,
)


MIN_TEXT_REVIEWS = 2


def execute_review_opinion_run(
    run_id: int,
    *,
    client: OpenRouterOpinionClient | None = None,
) -> dict[str, Any]:
    """Execute a run created exclusively by an explicit operator API command."""

    run = get_review_opinion_run(int(run_id))
    if run is None:
        raise LookupError("review_opinion_run_not_found")
    if run.get("status") not in {"queued", "running"}:
        return {"run_id": int(run_id), "status": str(run.get("status"))}

    mark_review_opinion_running(int(run_id))
    raw_output = ""
    try:
        analysis_input = build_review_opinion_input(
            int(run["project_id"]),
            int(run["nm_id"]),
        )
        update_review_opinion_input(int(run_id), analysis_input)
        if analysis_input.reviews_sent < MIN_TEXT_REVIEWS:
            finish_review_opinion_failed(
                int(run_id),
                error_code="insufficient_text_reviews",
                error_message="At least two written reviews are required",
            )
            return {"run_id": int(run_id), "status": "failed"}

        resolved_client = client or OpenRouterOpinionClient(
            model=str(run["model"]),
            reasoning_effort=str(run["reasoning_effort"]),
        )
        response = resolved_client.generate(analysis_input.payload)
        raw_output = response.raw_output_text
        try:
            parsed = parse_strict_json(response.content)
            result, validation = validate_and_normalize_output(
                parsed,
                review_fields=analysis_input.review_fields,
            )
            total_usage: dict[str, Any] = {"attempts": [response.usage]}
            final_response = response
        except ReviewOpinionOutputError as first_error:
            repaired = resolved_client.generate(
                analysis_input.payload,
                retry_errors=first_error.errors,
            )
            raw_output = repaired.raw_output_text
            parsed = parse_strict_json(repaired.content)
            result, validation = validate_and_normalize_output(
                parsed,
                review_fields=analysis_input.review_fields,
            )
            total_usage = {"attempts": [response.usage, repaired.usage]}
            final_response = repaired
            validation["repair_attempt_used"] = True

        finish_review_opinion_ready(
            int(run_id),
            model=final_response.model,
            result=result,
            validation=validation,
            usage=total_usage,
            provider_request_id=final_response.provider_request_id,
            raw_output_text=raw_output,
        )
        return {"run_id": int(run_id), "status": "ready"}
    except ReviewOpinionOutputError as exc:
        finish_review_opinion_failed(
            int(run_id),
            error_code="invalid_model_output",
            error_message="; ".join(exc.errors),
            raw_output_text=exc.raw_output or raw_output,
        )
        return {"run_id": int(run_id), "status": "failed"}
    except Exception as exc:  # noqa: BLE001
        finish_review_opinion_failed(
            int(run_id),
            error_code=type(exc).__name__,
            error_message=str(exc),
            raw_output_text=raw_output or None,
        )
        return {"run_id": int(run_id), "status": "failed"}
