"""Run a bounded A/B/C review-insight experiment against collected competitors.

This is an operator-only script. It never retries semantically invalid output and
stops scheduling new paid calls when the configured USD budget would be at risk.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.review_opinion.input_builder import normalize_text
from app.services.review_opinion.openrouter_client import OpenRouterOpinionClient
from app.services.review_opinion.prompt import SYSTEM_PROMPT
from app.services.review_opinion.validation import (
    ReviewOpinionOutputError,
    parse_strict_json,
    validate_and_normalize_output,
)


TERRA_MODEL = "openai/gpt-5.6-terra"
NANO_MODEL = "openai/gpt-5-nano"
MAX_COMPLETION_TOKENS = 5000
CALL_RESERVES_USD = {
    "terra_full": 0.30,
    "nano_full": 0.03,
    "nano_terra": 0.20,
}
HYBRID_INSTRUCTION = """

Режим synthesize_from_candidate_analysis:
- source_analysis создан дешёвой моделью по полному корпусу отзывов;
- перепроверь, объедини и приоритизируй его темы;
- используй только review_id из source_analysis;
- дословные цитаты бери только из evidence_reviews;
- не добавляй факты и темы, которых нет в source_analysis;
- верни результат в той же JSON Schema.
""".strip()


class ExperimentClient(OpenRouterOpinionClient):
    def __init__(self, *, system_prompt: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.system_prompt = system_prompt

    def _payload(
        self,
        input_payload: dict[str, Any],
        *,
        retry_errors: list[str] | None,
    ) -> dict[str, Any]:
        payload = super()._payload(input_payload, retry_errors=retry_errors)
        payload["messages"][0]["content"] = self.system_prompt
        payload["max_completion_tokens"] = MAX_COMPLETION_TOKENS
        return payload


def _load_products(project_id: int) -> list[dict[str, Any]]:
    product_sql = text(
        """
        SELECT id AS target_id, nm_id, title, category_name, text_reviews_count
        FROM wb_competitor_review_targets
        WHERE project_id = :project_id AND status = 'ready'
        ORDER BY nm_id
        """
    )
    review_sql = text(
        """
        SELECT external_id, rating, review_created_at, text, pros, cons
        FROM wb_competitor_reviews
        WHERE target_id = :target_id
        ORDER BY review_created_at ASC NULLS LAST, external_id ASC
        """
    )
    products: list[dict[str, Any]] = []
    with engine.connect() as conn:
        targets = conn.execute(
            product_sql,
            {"project_id": int(project_id)},
        ).mappings().all()
        for target in targets:
            rows = conn.execute(
                review_sql,
                {"target_id": int(target["target_id"])},
            ).mappings().all()
            reviews: list[dict[str, Any]] = []
            review_fields: dict[str, tuple[str, ...]] = {}
            seen_content: set[str] = set()
            for row in rows:
                fields = {
                    "text": normalize_text(row.get("text")),
                    "pros": normalize_text(row.get("pros")),
                    "cons": normalize_text(row.get("cons")),
                }
                if not any(fields.values()):
                    continue
                content_key = json.dumps(fields, ensure_ascii=False, sort_keys=True)
                if content_key in seen_content:
                    continue
                seen_content.add(content_key)
                review_id = f"r_{len(reviews) + 1:04d}"
                reviews.append(
                    {
                        "review_id": review_id,
                        "rating": int(row["rating"]) if row.get("rating") is not None else None,
                        "created_date": (
                            row["review_created_at"].date().isoformat()
                            if row.get("review_created_at") is not None
                            else None
                        ),
                        **{key: value or None for key, value in fields.items()},
                    }
                )
                review_fields[review_id] = tuple(
                    value for value in fields.values() if value
                )
            products.append(
                {
                    "nm_id": int(target["nm_id"]),
                    "title": str(target.get("title") or ""),
                    "category_name": target.get("category_name"),
                    "reviews": reviews,
                    "review_fields": review_fields,
                }
            )
    return products


def _full_payload(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "extract_competitor_customer_opinion",
        "language": "ru",
        "product": {
            "nm_id": product["nm_id"],
            "title": product["title"],
            "category_name": product["category_name"],
        },
        "analysis_scope": {
            "type": "all_time",
            "reviews_with_text": len(product["reviews"]),
            "reviews_sent": len(product["reviews"]),
        },
        "reviews": product["reviews"],
    }


def _hybrid_payload(
    product: dict[str, Any],
    nano_output: dict[str, Any],
) -> dict[str, Any]:
    evidence_ids: set[str] = set()
    for section in ("strengths", "weaknesses", "isolated_observations"):
        for finding in nano_output.get(section) or []:
            for evidence in finding.get("evidence") or []:
                review_id = evidence.get("review_id")
                if isinstance(review_id, str):
                    evidence_ids.add(review_id)
    evidence_reviews = [
        review for review in product["reviews"] if review["review_id"] in evidence_ids
    ]
    return {
        "task": "synthesize_from_candidate_analysis",
        "language": "ru",
        "product": {
            "nm_id": product["nm_id"],
            "title": product["title"],
            "category_name": product["category_name"],
        },
        "analysis_scope": {
            "type": "all_time",
            "reviews_with_text": len(product["reviews"]),
            "evidence_reviews_sent": len(evidence_reviews),
        },
        "source_analysis": nano_output,
        "evidence_reviews": evidence_reviews,
        "reviews": evidence_reviews,
    }


def _cost(usage: dict[str, Any]) -> float:
    try:
        return max(0.0, float(usage.get("cost") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _topics(result: dict[str, Any] | None) -> dict[str, list[str]]:
    value = result or {}
    return {
        section: [
            str(item.get("label") or "")
            for item in value.get(section, [])
            if isinstance(item, dict)
        ]
        for section in ("strengths", "weaknesses", "isolated_observations", "conflicts")
    }


def _run_call(
    *,
    variant: str,
    model: str,
    reasoning_effort: str,
    system_prompt: str,
    payload: dict[str, Any],
    review_fields: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    started = time.monotonic()
    client = ExperimentClient(
        model=model,
        reasoning_effort=reasoning_effort,
        system_prompt=system_prompt,
    )
    response = client.generate(payload)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    parsed: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    error: str | None = None
    try:
        parsed = parse_strict_json(response.content)
        result, validation = validate_and_normalize_output(
            parsed,
            review_fields=review_fields,
        )
    except ReviewOpinionOutputError as exc:
        error = "; ".join(exc.errors)
        if parsed is None:
            try:
                parsed = parse_strict_json(response.content)
            except ReviewOpinionOutputError:
                parsed = None
    return {
        "variant": variant,
        "requested_model": model,
        "resolved_model": response.model,
        "reasoning_effort": reasoning_effort,
        "elapsed_ms": elapsed_ms,
        "usage": response.usage,
        "cost_usd": _cost(response.usage),
        "valid": error is None,
        "validation_error": error,
        "result": result,
        "parsed_output": parsed,
        "topics": _topics(result or parsed),
    }


def _write(path: Path, report: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--budget-usd", type=float, default=3.0)
    parser.add_argument("--output", type=Path, default=Path("/tmp/competitor-review-ab.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.budget_usd <= 0 or args.budget_usd > 3:
        raise ValueError("budget-usd must be greater than 0 and at most 3")

    products = _load_products(args.project_id)
    if not products:
        raise LookupError("no_ready_competitor_products")
    report: dict[str, Any] = {
        "project_id": args.project_id,
        "budget_usd": args.budget_usd,
        "spent_usd": 0.0,
        "stopped_for_budget": False,
        "products": [
            {
                "nm_id": product["nm_id"],
                "title": product["title"],
                "reviews_sent": len(product["reviews"]),
                "variants": {},
            }
            for product in products
        ],
    }
    if args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if int(existing.get("project_id", -1)) != args.project_id:
            raise ValueError("existing report belongs to another project")
        existing_products = {
            int(item["nm_id"]): item
            for item in existing.get("products", [])
            if isinstance(item, dict) and item.get("nm_id") is not None
        }
        for item in report["products"]:
            previous = existing_products.get(int(item["nm_id"]))
            if previous:
                item["variants"] = dict(previous.get("variants") or {})
        report["spent_usd"] = float(existing.get("spent_usd") or 0.0)
        report["stopped_for_budget"] = False
    print(
        json.dumps(
            {
                "products": len(products),
                "reviews": [len(product["reviews"]) for product in products],
                "planned_calls": len(products) * 3,
                "budget_usd": args.budget_usd,
                "dry_run": args.dry_run,
            }
        ),
        flush=True,
    )
    if args.dry_run:
        return 0

    def can_call(variant: str) -> bool:
        reserve = CALL_RESERVES_USD[variant]
        return float(report["spent_usd"]) + reserve <= args.budget_usd

    for product, product_report in zip(products, report["products"], strict=True):
        payload = _full_payload(product)
        calls = (
            (
                "terra_full",
                TERRA_MODEL,
                "medium",
                SYSTEM_PROMPT,
                payload,
            ),
            (
                "nano_full",
                NANO_MODEL,
                "low",
                SYSTEM_PROMPT,
                payload,
            ),
        )
        nano_output: dict[str, Any] | None = None
        for variant, model, effort, system_prompt, call_payload in calls:
            existing_variant = product_report["variants"].get(variant)
            if existing_variant:
                if variant == "nano_full" and isinstance(
                    existing_variant.get("parsed_output"),
                    dict,
                ):
                    nano_output = existing_variant["parsed_output"]
                continue
            if not can_call(variant):
                report["stopped_for_budget"] = True
                _write(args.output, report)
                return 2
            try:
                value = _run_call(
                    variant=variant,
                    model=model,
                    reasoning_effort=effort,
                    system_prompt=system_prompt,
                    payload=call_payload,
                    review_fields=product["review_fields"],
                )
            except Exception as exc:  # noqa: BLE001
                value = {
                    "variant": variant,
                    "requested_model": model,
                    "reasoning_effort": effort,
                    "valid": False,
                    "call_error": f"{type(exc).__name__}:{exc}",
                    "cost_usd": 0.0,
                    "topics": {},
                }
            product_report["variants"][variant] = value
            report["spent_usd"] = round(
                float(report["spent_usd"]) + float(value["cost_usd"]),
                8,
            )
            _write(args.output, report)
            print(
                json.dumps(
                    {
                        "nm_id": product["nm_id"],
                        "variant": variant,
                        "valid": value["valid"],
                        "cost_usd": value["cost_usd"],
                        "spent_usd": report["spent_usd"],
                    }
                ),
                flush=True,
            )
            if variant == "nano_full" and isinstance(value.get("parsed_output"), dict):
                nano_output = value["parsed_output"]

        if nano_output is None:
            continue
        if product_report["variants"].get("nano_terra"):
            continue
        if not can_call("nano_terra"):
            report["stopped_for_budget"] = True
            _write(args.output, report)
            return 2
        hybrid = _run_call(
            variant="nano_terra",
            model=TERRA_MODEL,
            reasoning_effort="medium",
            system_prompt=f"{SYSTEM_PROMPT}\n\n{HYBRID_INSTRUCTION}",
            payload=_hybrid_payload(product, nano_output),
            review_fields=product["review_fields"],
        )
        product_report["variants"]["nano_terra"] = hybrid
        report["spent_usd"] = round(
            float(report["spent_usd"]) + float(hybrid["cost_usd"]),
            8,
        )
        _write(args.output, report)
        print(
            json.dumps(
                {
                    "nm_id": product["nm_id"],
                    "variant": "nano_terra",
                    "valid": hybrid["valid"],
                    "cost_usd": hybrid["cost_usd"],
                    "spent_usd": report["spent_usd"],
                }
            ),
            flush=True,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
