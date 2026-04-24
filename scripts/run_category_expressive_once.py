#!/usr/bin/env python3
"""
Run ONE LLM call for category expressive extraction (no retries, no repair).

This script is intentionally minimal and audit-friendly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.services.seo.providers.base import ChatMessage  # noqa: E402
from app.services.seo.providers.openrouter import OpenRouterProvider  # noqa: E402


SYSTEM_PROMPT = (
    "Ты извлекаешь expressive meaning (vibes) категории из отзывов покупателей.\n"
    "Работай строго по evidence.\n"
    "Запрещено:\n"
    "- возвращать generic labels: \"positive\", \"good\", \"quality\"\n"
    "- возвращать функциональные признаки (тип товара, материал, объём и т.п.)\n"
    "Если сигналов нет — верни пустой список.\n"
    "Ответ только валидный JSON.\n"
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_json_object(content: str) -> dict[str, Any]:
    text_value = str(content or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value)
        text_value = re.sub(r"\s*```$", "", text_value)
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model response does not contain JSON object")
    return json.loads(text_value[start : end + 1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-call category expressive extraction (reviews-only).")
    parser.add_argument("--payload", required=True, help="Path to payload JSON with {category_name, reviews[]}.")
    parser.add_argument("--model", default="openai/gpt-4o-mini")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--out-dir", default="/data/internal_data/expressive_llm_eval/single_runs/markers_reviews_only")
    args = parser.parse_args()

    payload_path = Path(args.payload)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    category_name = str(payload.get("category_name") or "").strip()
    reviews = payload.get("reviews") or []
    if not isinstance(reviews, list):
        raise SystemExit("payload.reviews must be a list")

    # One category, one call: keep user prompt strict and compact.
    user_prompt = (
        "Вход:\n"
        "- category_name\n"
        "- reviews[] (основной источник)\n\n"
        "Задача:\n"
        "Верни 3–5 выразительных (perceptual) vibes категории.\n\n"
        "Требования:\n"
        "- Используй только тексты отзывов как источник\n"
        "- Каждый vibe должен иметь:\n"
        "  - label (короткое имя)\n"
        "  - confidence (0–1)\n"
        "  - evidence_spans (РОВНО 2–3 короткие цитаты из отзывов, ≤80 символов)\n"
        "- Не более 5 vibes\n"
        "- Если недостаточно данных — возвращай меньше vibes или пустой список\n\n"
        "Схема ответа:\n"
        "{\n"
        '  "version": "v1",\n'
        '  "task": "category",\n'
        '  "category_name": "<CATEGORY_NAME>",\n'
        '  "vibes": [\n'
        "    {\n"
        '      "label": "...",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_spans": ["...", "..."]\n'
        "    }\n"
        "  ],\n"
        '  "summary": ""\n'
        "}\n\n"
        "INPUT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    provider = OpenRouterProvider(chat_model=str(args.model), timeout_seconds=60.0)
    t0 = _now_ms()
    resp = provider.generate_chat(
        [ChatMessage(role="system", content=SYSTEM_PROMPT), ChatMessage(role="user", content=user_prompt)],
        temperature=float(args.temperature),
        top_p=float(args.top_p),
        max_tokens=max(16, int(args.max_tokens)),
    )
    latency_ms = _now_ms() - t0
    raw_response = dict(resp.raw_response or {})
    content = str(resp.content or "")

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)
    _write_json(
        out_dir / "raw_response.json",
        {"model": str(resp.model), "latency_ms": int(latency_ms), "raw_response": raw_response, "content": content},
    )

    try:
        parsed = _extract_json_object(content)
    except Exception as exc:  # noqa: BLE001
        _write_json(out_dir / "parse_error.json", {"error": str(exc), "content": content})
        print(json.dumps({"status": "parse_failed", "error": str(exc), "out_dir": str(out_dir)}, ensure_ascii=False))
        return 2

    _write_json(out_dir / "parsed.json", parsed)

    # Extract vibes + validate evidence spans against reviews text
    haystack = "\n".join(str(r or "") for r in reviews)

    vibes = parsed.get("vibes") if isinstance(parsed, dict) else None
    if not isinstance(vibes, list):
        vibes = []

    extracted = []
    for vibe in vibes:
        if not isinstance(vibe, dict):
            continue
        spans = vibe.get("evidence_spans") or []
        if not isinstance(spans, list):
            spans = []
        span_checks = []
        for s in spans[:8]:
            span = str(s or "").strip()
            if not span:
                continue
            ok = span in haystack
            span_checks.append({"span": span, "found_in_reviews": bool(ok)})
        extracted.append(
            {
                "label": str(vibe.get("label") or "").strip(),
                "confidence": float(vibe.get("confidence") or 0.0),
                "evidence_spans": span_checks,
            }
        )

    _write_json(
        out_dir / "extracted_vibes.json",
        {
            "category_name": category_name,
            "reviews_count": len(reviews),
            "model": str(resp.model),
            "latency_ms": int(latency_ms),
            "vibes": extracted,
        },
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "model": str(resp.model),
                "latency_ms": int(latency_ms),
                "out_dir": str(out_dir),
                "vibes_count": len(extracted),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
