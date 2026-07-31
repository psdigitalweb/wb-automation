"""Budget-bounded Nano -> Terra analysis for collected competitor reviews."""

from __future__ import annotations

import json
from typing import Any, Iterable

from app import settings
from app.db_wb_competitor_reviews import (
    finish_competitor_analysis_failed,
    finish_competitor_analysis_ready,
    get_competitor_analysis_run,
    mark_competitor_analysis_running,
)
from .client import StructuredOpenRouterClient, StructuredResponse
from .contracts import (
    PIPELINE_VERSION,
    SCHEMA_VERSION,
    ChunkAnalysis,
    CompetitorAnalysisModelOutput,
    chunk_json_schema,
    final_json_schema,
)
from .input_builder import build_competitor_analysis_input
from .normalization import normalize_text


CHUNK_PROMPT = """Ты анализируешь один пакет отзывов покупателей маркетплейса.
Сгруппируй только подтверждённые текстом свойства, проблемы и противоречия.
Каждый review_id можно использовать только если отзыв действительно подтверждает тему.
Не придумывай цитаты, числа и свойства. Не смешивай товар с упаковкой, доставкой
или обслуживанием. Возвращай только JSON по переданной схеме."""

FINAL_PROMPT = """Ты формируешь итоговые выводы по отзывам о товаре конкурента.
candidate_themes получены из полного корпуса отзывов небольшими пакетами.
Объедини синонимичные темы, сохрани важные частные проблемы и отделяй свойства
товара от упаковки, доставки и обслуживания.

Правила:
1. source_theme_ids должны существовать в candidate_themes.
2. Цитаты бери дословно только из evidence_reviews.
3. review_id цитаты должен входить в отзывы выбранных source_theme_ids.
4. Возможности улучшения должны следовать из подтверждённых слабых сторон.
5. Не придумывай частотность: она будет рассчитана приложением.
6. Верни только JSON по переданной схеме."""

NANO_CALL_RESERVE_USD = 0.01
TERRA_CALL_RESERVE_USD = 0.12


class CompetitorAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _parsed_object(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return dict(content)
    try:
        parsed = json.loads(str(content or ""))
    except json.JSONDecodeError as exc:
        raise CompetitorAnalysisError("invalid_model_json", "Model returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise CompetitorAnalysisError("invalid_model_json", "Model returned a non-object")
    return parsed


def _usage_cost(response: StructuredResponse) -> float:
    try:
        return max(0.0, float(response.usage.get("cost") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _union_review_ids(
    theme_ids: Iterable[str],
    themes: dict[str, dict[str, Any]],
) -> list[str]:
    values: list[str] = []
    for theme_id in theme_ids:
        theme = themes.get(theme_id)
        if theme:
            values.extend(str(value) for value in theme["review_ids"])
    return list(dict.fromkeys(values))


def _prevalence(support_count: int, reviews_count: int) -> str:
    ratio = support_count / max(1, reviews_count)
    if support_count >= 10 or ratio >= 0.15:
        return "frequent"
    if support_count >= 3:
        return "occasional"
    return "isolated"


def _validate_evidence(
    evidence: list[Any],
    *,
    allowed_review_ids: list[str],
    review_fields: dict[str, tuple[str, ...]],
    repair_stats: dict[str, int],
) -> list[dict[str, str]]:
    allowed_set = set(allowed_review_ids)
    normalized: list[dict[str, str]] = []
    seen_review_ids: set[str] = set()
    for item in evidence:
        review_id = item.review_id
        if review_id not in allowed_set:
            repair_stats["dropped"] += 1
            continue
        fields = review_fields.get(review_id)
        quote = normalize_text(item.quote)
        if not fields or not quote or not any(quote in field for field in fields):
            repair_stats["dropped"] += 1
            continue
        if review_id in seen_review_ids:
            continue
        seen_review_ids.add(review_id)
        normalized.append({"review_id": review_id, "quote": quote})
    if normalized:
        return normalized

    # Terra can choose a real quote but attach theme ids that do not contain
    # that review. Use a deterministic exact excerpt from a review that really
    # supports the selected themes instead of failing the complete analysis.
    for review_id in allowed_review_ids:
        fields = review_fields.get(review_id) or ()
        for field in fields:
            quote = normalize_text(field)
            if not quote:
                continue
            if len(quote) > 180:
                boundary = max(
                    quote.rfind(". ", 0, 180),
                    quote.rfind("! ", 0, 180),
                    quote.rfind("? ", 0, 180),
                )
                quote = quote[: boundary + 1 if boundary >= 39 else 180].rstrip()
            repair_stats["fallback_added"] += 1
            return [{"review_id": review_id, "quote": quote}]

    raise CompetitorAnalysisError(
        "missing_supported_evidence",
        "Selected themes do not contain a review with text",
    )


def _normalize_final(
    output: CompetitorAnalysisModelOutput,
    *,
    themes: dict[str, dict[str, Any]],
    review_fields: dict[str, tuple[str, ...]],
    reviews_count: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    seen_labels: set[str] = set()
    repair_stats = {"dropped": 0, "fallback_added": 0}

    def finding(item: Any, *, priority: str | None = None) -> dict[str, Any]:
        source_ids = list(dict.fromkeys(item.source_theme_ids))
        unknown = [value for value in source_ids if value not in themes]
        if unknown:
            raise CompetitorAnalysisError(
                "unknown_source_theme",
                f"Unknown source themes: {', '.join(unknown[:5])}",
            )
        label_key = normalize_text(item.label).casefold()
        if label_key in seen_labels:
            raise CompetitorAnalysisError("duplicate_analysis_theme", item.label)
        seen_labels.add(label_key)
        review_ids = _union_review_ids(source_ids, themes)
        result = {
            "label": item.label.strip(),
            "summary": item.summary.strip(),
            "support_count": len(review_ids),
            "prevalence": _prevalence(len(review_ids), reviews_count),
            "evidence": _validate_evidence(
                item.evidence,
                allowed_review_ids=review_ids,
                review_fields=review_fields,
                repair_stats=repair_stats,
            ),
        }
        if hasattr(item, "category"):
            result["category"] = item.category
        if hasattr(item, "confidence"):
            result["confidence"] = item.confidence
        if priority is not None:
            result["priority"] = priority
        return result

    strengths = [finding(item) for item in output.strengths]
    weaknesses = [finding(item) for item in output.weaknesses]
    opportunities = [
        finding(item, priority=item.priority)
        for item in output.opportunities
    ]
    conflicts: list[dict[str, Any]] = []
    for item in output.conflicts:
        source_ids = list(dict.fromkeys(item.source_theme_ids))
        unknown = [value for value in source_ids if value not in themes]
        if unknown:
            raise CompetitorAnalysisError("unknown_source_theme", unknown[0])
        review_ids = _union_review_ids(source_ids, themes)
        conflicts.append(
            {
                "label": item.label.strip(),
                "summary": item.summary.strip(),
                "support_count": len(review_ids),
                "prevalence": _prevalence(len(review_ids), reviews_count),
            }
        )
    result = {
        "schema_version": SCHEMA_VERSION,
        "overall_conclusion": output.overall_conclusion.strip(),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "opportunities": opportunities,
        "conflicts": conflicts,
    }
    validation = {
        "status": "passed",
        "reviews_available": reviews_count,
        "candidate_themes": len(themes),
        "evidence_quotes_valid": True,
        "evidence_items_dropped": repair_stats["dropped"],
        "fallback_evidence_added": repair_stats["fallback_added"],
    }
    return result, validation


def execute_competitor_analysis(
    run_id: int,
    *,
    nano_client: StructuredOpenRouterClient | None = None,
    terra_client: StructuredOpenRouterClient | None = None,
) -> dict[str, Any]:
    run = get_competitor_analysis_run(int(run_id))
    if run is None:
        raise LookupError("competitor_analysis_not_found")
    if run["status"] not in {"queued", "running"}:
        return {"run_id": int(run_id), "status": run["status"]}

    mark_competitor_analysis_running(int(run_id))
    usages: list[dict[str, Any]] = []
    spent = 0.0
    try:
        analysis_input = build_competitor_analysis_input(
            int(run["project_id"]),
            int(run["nm_id"]),
        )
        if analysis_input.input_hash != run["input_hash"]:
            raise CompetitorAnalysisError(
                "reviews_changed",
                "Reviews changed after analysis was queued; start it again",
            )
        if len(analysis_input.reviews) < 2:
            raise CompetitorAnalysisError(
                "insufficient_reviews",
                "At least two written reviews are required",
            )
        max_cost = float(run["max_cost_usd"])
        resolved_nano = nano_client or StructuredOpenRouterClient(
            model=settings.OPENROUTER_COMPETITOR_NANO_MODEL,
            reasoning_effort="low",
        )
        resolved_terra = terra_client or StructuredOpenRouterClient(
            model=settings.OPENROUTER_COMPETITOR_TERRA_MODEL,
            reasoning_effort="medium",
        )

        themes: dict[str, dict[str, Any]] = {}
        for chunk_index, reviews in enumerate(analysis_input.chunks, start=1):
            if spent + NANO_CALL_RESERVE_USD > max_cost:
                raise CompetitorAnalysisError(
                    "budget_exceeded",
                    "Analysis stopped before the next model call",
                )
            response = resolved_nano.generate(
                system_prompt=CHUNK_PROMPT,
                user_payload={
                    "product": {
                        "nm_id": analysis_input.nm_id,
                        "title": analysis_input.title,
                        "category_name": analysis_input.category_name,
                    },
                    "reviews": reviews,
                },
                schema_name="competitor_review_chunk",
                schema=chunk_json_schema(),
                max_completion_tokens=5000,
            )
            usages.append({"stage": "nano_chunk", "chunk": chunk_index, **response.usage})
            spent += _usage_cost(response)
            parsed = ChunkAnalysis.model_validate(_parsed_object(response.content))
            allowed_ids = {str(review["review_id"]) for review in reviews}
            for theme_index, item in enumerate(parsed.themes, start=1):
                review_ids = list(dict.fromkeys(item.review_ids))
                if any(review_id not in allowed_ids for review_id in review_ids):
                    raise CompetitorAnalysisError(
                        "unknown_chunk_review",
                        "Nano returned a review id outside its chunk",
                    )
                theme_id = f"t_{chunk_index:02d}_{theme_index:02d}"
                themes[theme_id] = {
                    "theme_id": theme_id,
                    "label": item.label.strip(),
                    "sentiment": item.sentiment,
                    "category": item.category,
                    "summary": item.summary.strip(),
                    "review_ids": review_ids,
                }

        if not themes:
            raise CompetitorAnalysisError(
                "no_confirmed_themes",
                "No confirmed review themes were found",
            )
        evidence_ids: list[str] = []
        for theme in themes.values():
            evidence_ids.extend(theme["review_ids"][:2])
        evidence_set = set(dict.fromkeys(evidence_ids))
        evidence_reviews = [
            review
            for review in analysis_input.reviews
            if review["review_id"] in evidence_set
        ][:120]

        if spent + TERRA_CALL_RESERVE_USD > max_cost:
            raise CompetitorAnalysisError(
                "budget_exceeded",
                "Analysis stopped before final synthesis",
            )
        final_response = resolved_terra.generate(
            system_prompt=FINAL_PROMPT,
            user_payload={
                "product": {
                    "nm_id": analysis_input.nm_id,
                    "title": analysis_input.title,
                    "category_name": analysis_input.category_name,
                },
                "reviews_count": len(analysis_input.reviews),
                "candidate_themes": list(themes.values()),
                "evidence_reviews": evidence_reviews,
            },
            schema_name="competitor_review_analysis",
            schema=final_json_schema(),
            max_completion_tokens=5000,
        )
        usages.append({"stage": "terra_synthesis", **final_response.usage})
        spent += _usage_cost(final_response)
        output = CompetitorAnalysisModelOutput.model_validate(
            _parsed_object(final_response.content)
        )
        result, validation = _normalize_final(
            output,
            themes=themes,
            review_fields=analysis_input.review_fields,
            reviews_count=len(analysis_input.reviews),
        )
        finish_competitor_analysis_ready(
            int(run_id),
            result=result,
            validation=validation,
            usage={"attempts": usages, "pipeline_version": PIPELINE_VERSION},
            actual_cost_usd=spent,
        )
        return {"run_id": int(run_id), "status": "ready", "cost_usd": spent}
    except CompetitorAnalysisError as exc:
        finish_competitor_analysis_failed(
            int(run_id),
            error_code=exc.code,
            error_message=str(exc),
            usage={"attempts": usages},
            actual_cost_usd=spent,
        )
        return {"run_id": int(run_id), "status": "failed", "error_code": exc.code}
    except Exception as exc:  # noqa: BLE001
        finish_competitor_analysis_failed(
            int(run_id),
            error_code=type(exc).__name__,
            error_message=str(exc),
            usage={"attempts": usages},
            actual_cost_usd=spent,
        )
        return {
            "run_id": int(run_id),
            "status": "failed",
            "error_code": type(exc).__name__,
        }
