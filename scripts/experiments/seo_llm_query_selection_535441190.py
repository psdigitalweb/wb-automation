"""One-off OpenRouter query-selection experiment for SKU 535441190.

Reads product evidence, cached vision evidence, and category 812 cluster
representatives, then asks an LLM to select a small SEO query set. This script
does not write to the database.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx
from sqlalchemy import text

from app.db import SessionLocal


ROOT = Path(__file__).resolve().parents[2]
NM_ID = 535441190
PROJECT_ID = 1
CATEGORY_ID = 812
MODEL = os.getenv("SEO_QUERY_SELECTION_MODEL", "openai/gpt-4o")

REPRESENTATIVES_PATH = (
    ROOT
    / "tests"
    / "seo"
    / "phase1q"
    / "category_812"
    / "dedupe_cluster_representatives"
    / "representatives_after.json"
)
OUT_DIR = (
    ROOT
    / "tests"
    / "seo"
    / "phase1q"
    / "category_812"
    / "query_selection_535441190"
)
VISION_CACHE_DIR = Path("/data/internal_data/seo_meaning_atoms_cache/vision_atoms")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text_value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_value, encoding="utf-8")


def _extract_json_object(text_value: str) -> dict[str, Any]:
    stripped = str(text_value or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("{"):
        first = candidate.find("{")
        last = candidate.rfind("}")
        if first >= 0 and last > first:
            candidate = candidate[first : last + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def _product_from_db() -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT title, description, subject_name, characteristics
                FROM products
                WHERE project_id = :project_id AND nm_id = :nm_id
                LIMIT 1
                """
            ),
            {"project_id": PROJECT_ID, "nm_id": NM_ID},
        ).mappings().first()
    if row is None:
        raise RuntimeError(f"Product {NM_ID} not found")
    return {
        "nm_id": NM_ID,
        "title": row["title"],
        "description": row["description"],
        "subject_name": row["subject_name"],
        "characteristics": row["characteristics"],
    }


def _category_expressive_axes() -> list[str]:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT axes_payload
                FROM seo_category_meaning_axes
                WHERE project_id = :project_id
                  AND category_id = :category_id
                  AND status = 'ready'
                ORDER BY updated_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ),
            {"project_id": PROJECT_ID, "category_id": CATEGORY_ID},
        ).mappings().first()
    if row is None:
        return []
    payload = row["axes_payload"] or {}
    axes = payload.get("expressive_axes") or []
    return [str(item).strip() for item in axes if str(item).strip()]


def _vision_summary() -> dict[str, Any]:
    matches: list[tuple[float, Path, Mapping[str, Any]]] = []
    if VISION_CACHE_DIR.exists():
        for path in VISION_CACHE_DIR.glob("*.json"):
            try:
                payload = _read_json(path)
            except Exception:
                continue
            text_blob = json.dumps(payload, ensure_ascii=False)
            if str(NM_ID) not in text_blob:
                continue
            matches.append((path.stat().st_mtime, path, payload))
    if not matches:
        return {"status": "missing", "source": "cache_not_found"}
    _, path, payload = sorted(matches, key=lambda item: item[0])[-1]
    atoms = dict(payload.get("atoms") or {})
    facts = atoms.get("facts") or []
    positives = atoms.get("positive_atoms") or []
    negatives = atoms.get("negative_fit_atoms") or []
    return {
        "status": "cached_unvalidated_vision",
        "source_file": str(path),
        "model": payload.get("model"),
        "prompt_version": payload.get("prompt_version"),
        "image_urls": payload.get("image_urls") or [],
        "visible_facts": [
            {"field": item.get("field"), "value": item.get("value"), "confidence": item.get("confidence")}
            for item in facts
            if isinstance(item, Mapping)
        ],
        "positive_visual_meanings": [
            {
                "type": item.get("type"),
                "field": item.get("field"),
                "value": item.get("value"),
                "confidence": item.get("confidence"),
            }
            for item in positives
            if isinstance(item, Mapping)
        ],
        "negative_visual_fit": [
            {"field": item.get("field"), "value": item.get("value"), "confidence": item.get("confidence")}
            for item in negatives
            if isinstance(item, Mapping)
        ],
    }


def _query_candidates() -> list[dict[str, Any]]:
    rows = _read_json(REPRESENTATIVES_PATH)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        cluster_id = row.get("kept_cluster_id")
        query = str(row.get("kept_query") or "").strip()
        frequency = row.get("ranking_value_used")
        if cluster_id is None or not query:
            continue
        candidates.append(
            {
                "cluster_id": int(cluster_id),
                "query": query,
                "frequency": int(frequency or 0),
            }
        )
    return candidates


def _compact_characteristics(characteristics: Any) -> list[dict[str, Any]]:
    if not isinstance(characteristics, list):
        return []
    allowed_names = {
        "Цвет",
        "Тип кружки",
        "Объем (мл)",
        "Материал посуды",
        "Рисунок",
        "Декоративные элементы",
        "Упаковка",
        "Повод",
        "Назначение подарка",
        "Назначение посуды",
        "Особенности кружки",
        "Назначение",
    }
    result: list[dict[str, Any]] = []
    for item in characteristics:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if name in allowed_names:
            result.append({"name": name, "value": item.get("value")})
    return result


def _prompt_text(evidence: Mapping[str, Any], candidates: list[dict[str, Any]]) -> str:
    product = evidence["product"]
    input_payload = {
        "product": {
            "title": product["title"],
            "description": product["description"],
            "key_characteristics": product["key_characteristics"],
        },
        "brand_level_style_hint": {
            "label": "Кружки этого бренда обычно характеризуются как",
            "values": evidence["brand_level_style_hint"],
        },
        "photo_analysis": evidence["photo_analysis"],
        "query_candidates": candidates,
    }
    return (
        "Ты помогаешь выбрать SEO-запросы для карточки товара на маркетплейсе.\n\n"
        "Цель:\n"
        "Выбрать из списка запросов только те, которые реально подходят этому конкретному товару "
        "по смыслу, внешнему виду, назначению и покупательскому контексту.\n\n"
        "Важно:\n"
        "- Не выбирай запрос только потому, что он частотный.\n"
        "- Не выбирай запрос только потому, что в нём есть слово \"кружка\".\n"
        "- Не выбирай слишком общие запросы, если есть более точные.\n"
        "- Не выдумывай свойства товара.\n"
        "- Если запрос обещает то, чего у товара нет или не видно, отклоняй.\n"
        "- Если запрос содержит конкретный атрибут, который противоречит товару, отправляй его в reject, "
        "а не в secondary. Примеры конфликтов для этого товара: 500 мл, большая кружка, белая/белые, "
        "мальчику, 23 февраля, мужской подарок, крышка, подогрев, хамелеон, пивная, двойное дно.\n"
        "- Максимум 40 запросов всего.\n"
        "- Лучше выбрать меньше, но точнее.\n\n"
        "Группы ответа:\n"
        "1. primary — самые точные запросы, максимум 15.\n"
        "2. secondary — хорошие, но шире или менее точные запросы, максимум 15.\n"
        "3. gift_style — запросы про подарок, стиль, эмоцию, аудиторию, максимум 10.\n"
        "4. reject — только явно неподходящие или опасные запросы; не обязательно возвращать все отклонённые.\n\n"
        "Для каждого выбранного запроса верни cluster_id, query, reason, confidence от 0 до 1.\n\n"
        "Верни только JSON строго такого формата:\n"
        "{\n"
        "  \"primary\": [],\n"
        "  \"secondary\": [],\n"
        "  \"gift_style\": [],\n"
        "  \"reject\": []\n"
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(input_payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def _call_openrouter(prompt: str, *, max_tokens: int = 12000) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    request_payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict SEO query selection editor. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ecomcore.local",
                "X-Title": "EcomCore SEO Query Selection Experiment",
            },
            json=request_payload,
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("OpenRouter returned non-object response")
    return data


def _selected_summary(parsed: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for bucket in ["primary", "secondary", "gift_style", "reject"]:
        rows = parsed.get(bucket) or []
        if not isinstance(rows, list):
            rows = []
        result[bucket] = {
            "count": len(rows),
            "queries": [
                {
                    "cluster_id": item.get("cluster_id"),
                    "query": item.get("query"),
                    "confidence": item.get("confidence"),
                    "reason": item.get("reason"),
                }
                for item in rows
                if isinstance(item, Mapping)
            ],
        }
    result["selected_total_without_reject"] = (
        result["primary"]["count"] + result["secondary"]["count"] + result["gift_style"]["count"]
    )
    return result


def main() -> None:
    product = _product_from_db()
    candidates = _query_candidates()
    evidence = {
        "product": {
            "nm_id": NM_ID,
            "title": product["title"],
            "description": product["description"],
            "subject_name": product["subject_name"],
            "key_characteristics": _compact_characteristics(product["characteristics"]),
        },
        "brand_level_style_hint": _category_expressive_axes(),
        "photo_analysis": _vision_summary(),
    }
    prompt = _prompt_text(evidence, candidates)
    _write_json(OUT_DIR / "input_evidence.json", evidence)
    _write_json(OUT_DIR / "query_candidates.json", candidates)
    _write_text(OUT_DIR / "prompt.txt", prompt)

    raw = _call_openrouter(prompt)
    _write_json(OUT_DIR / "raw_response.json", raw)
    content = raw["choices"][0]["message"]["content"]
    parsed = _extract_json_object(content)
    summary = _selected_summary(parsed)
    usage = raw.get("usage") or {}
    summary.update(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "candidate_count": len(candidates),
            "usage": usage,
            "finish_reason": raw.get("choices", [{}])[0].get("finish_reason"),
        }
    )
    _write_json(OUT_DIR / "parsed_selection.json", parsed)
    _write_json(OUT_DIR / "selection_summary.json", summary)

    report_lines = [
        "# Query Selection 535441190",
        "",
        f"- model: `{MODEL}`",
        f"- candidates: `{len(candidates)}`",
        f"- finish_reason: `{summary.get('finish_reason')}`",
        f"- selected_total_without_reject: `{summary.get('selected_total_without_reject')}`",
        f"- usage: `{json.dumps(usage, ensure_ascii=False)}`",
        "",
    ]
    for bucket in ["primary", "secondary", "gift_style", "reject"]:
        report_lines.append(f"## {bucket}")
        for item in summary[bucket]["queries"]:
            report_lines.append(
                f"- `{item.get('cluster_id')}` {item.get('query')} "
                f"(confidence={item.get('confidence')}): {item.get('reason')}"
            )
        report_lines.append("")
    _write_text(OUT_DIR / "selection_report.md", "\n".join(report_lines))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
