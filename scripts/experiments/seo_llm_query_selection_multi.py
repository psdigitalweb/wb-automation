"""One-off multi-category OpenRouter query-selection experiment.

For each configured SKU, reads product evidence and one top query per demand
cluster, then asks an LLM to return only selected queries. No DB writes.
"""

from __future__ import annotations

import argparse
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
PROJECT_ID = 1
MODEL = os.getenv("SEO_QUERY_SELECTION_MODEL", "openai/gpt-4o")
OUT_ROOT = ROOT / "tests" / "seo" / "phase1q" / "multi_category_query_selection"
VISION_CACHE_DIR = Path("/data/internal_data/seo_meaning_atoms_cache/vision_atoms")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _extract_json_object(value: str) -> dict[str, Any]:
    stripped = str(value or "").strip()
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


def _product_from_db(category_id: int, nm_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT title, description, subject_name, characteristics
                FROM products
                WHERE project_id = :project_id
                  AND subject_id = :category_id
                  AND nm_id = :nm_id
                LIMIT 1
                """
            ),
            {"project_id": PROJECT_ID, "category_id": category_id, "nm_id": nm_id},
        ).mappings().first()
    if row is None:
        raise RuntimeError(f"Product not found: category_id={category_id}, nm_id={nm_id}")
    return {
        "nm_id": nm_id,
        "title": row["title"],
        "description": row["description"],
        "subject_name": row["subject_name"],
        "characteristics": row["characteristics"],
    }


def _category_expressive_axes(category_id: int) -> list[str]:
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
            {"project_id": PROJECT_ID, "category_id": category_id},
        ).mappings().first()
    if row is None:
        return []
    payload = row["axes_payload"] or {}
    axes = payload.get("expressive_axes") or []
    return [str(item).strip() for item in axes if str(item).strip()]


def _query_candidates(category_id: int, *, min_frequency: int) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                WITH ranked AS (
                    SELECT cluster_id,
                           normalized_query_text,
                           ranking_value_used,
                           row_number() OVER (
                               PARTITION BY cluster_id
                               ORDER BY ranking_value_used DESC NULLS LAST, normalized_query_text
                           ) AS rn
                    FROM seo_query_cluster_memberships
                    WHERE project_id = :project_id
                      AND category_id = :category_id
                      AND ranking_value_used > :min_frequency
                )
                SELECT cluster_id, normalized_query_text, ranking_value_used
                FROM ranked
                WHERE rn = 1
                ORDER BY ranking_value_used DESC NULLS LAST, normalized_query_text
                """
            ),
            {"project_id": PROJECT_ID, "category_id": category_id, "min_frequency": min_frequency},
        ).mappings().all()
    return [
        {
            "cluster_id": int(row["cluster_id"]),
            "query": row["normalized_query_text"],
            "frequency": int(row["ranking_value_used"] or 0),
        }
        for row in rows
    ]


def _compact_characteristics(characteristics: Any) -> list[dict[str, Any]]:
    if not isinstance(characteristics, list):
        return []
    skip_prefixes = (
        "Дата ",
        "Номер декларации",
        "Ставка НДС",
        "Страна производства",
    )
    result: list[dict[str, Any]] = []
    for item in characteristics:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if not name or any(name.startswith(prefix) for prefix in skip_prefixes):
            continue
        result.append({"name": name, "value": item.get("value")})
        if len(result) >= 24:
            break
    return result


def _vision_summary(nm_id: int) -> dict[str, Any]:
    matches: list[tuple[float, Path, Mapping[str, Any]]] = []
    if VISION_CACHE_DIR.exists():
        for path in VISION_CACHE_DIR.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(nm_id) in json.dumps(payload, ensure_ascii=False):
                matches.append((path.stat().st_mtime, path, payload))
    if not matches:
        return {"status": "missing"}
    _, path, payload = sorted(matches, key=lambda item: item[0])[-1]
    atoms = dict(payload.get("atoms") or {})
    return {
        "status": "cached_unvalidated_vision",
        "source_file": str(path),
        "model": payload.get("model"),
        "prompt_version": payload.get("prompt_version"),
        "image_urls": payload.get("image_urls") or [],
        "visible_facts": atoms.get("facts") or [],
        "positive_visual_meanings": atoms.get("positive_atoms") or [],
        "negative_visual_fit": atoms.get("negative_fit_atoms") or [],
    }


def _prompt_text(evidence: Mapping[str, Any], candidates: list[dict[str, Any]]) -> str:
    product = evidence["product"]
    subject_name = str(product.get("subject_name") or "Товары")
    style_hint = evidence["brand_level_style_hint"]
    input_payload = {
        "product": {
            "title": product["title"],
            "description": product["description"],
            "key_characteristics": product["key_characteristics"],
        },
        "brand_level_style_hint": {
            "label": f"{subject_name} этого бренда обычно характеризуются как",
            "values": style_hint,
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
        "- Не выбирай запрос только потому, что в нём есть родовое название товара.\n"
        "- Не выбирай слишком общие запросы, если есть более точные.\n"
        "- Не выдумывай свойства товара.\n"
        "- Если запрос содержит конкретный атрибут, который противоречит товару, не включай его ни в одну группу.\n"
        "- Не возвращай rejected: всё, что не выбрано, считается rejected by omission.\n"
        "- Максимум 40 запросов всего.\n"
        "- Лучше выбрать меньше, но точнее.\n\n"
        "Группы ответа:\n"
        "1. primary — самые точные запросы, максимум 15.\n"
        "2. secondary — хорошие, но шире или менее точные запросы, максимум 15.\n"
        "3. gift_style — запросы про подарок, стиль, эмоцию, аудиторию, максимум 10.\n\n"
        "Для каждого выбранного запроса верни cluster_id, query, reason, confidence от 0 до 1.\n\n"
        "Верни только JSON строго такого формата:\n"
        "{\n"
        "  \"primary\": [],\n"
        "  \"secondary\": [],\n"
        "  \"gift_style\": []\n"
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(input_payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def _call_openrouter(prompt: str, *, max_tokens: int) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict SEO query selection editor. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": int(max_tokens),
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ecomcore.local",
                "X-Title": "EcomCore SEO Multi Query Selection Experiment",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("OpenRouter returned non-object response")
    return data


def _summary(parsed: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    total = 0
    for bucket in ["primary", "secondary", "gift_style"]:
        rows = parsed.get(bucket) or []
        if not isinstance(rows, list):
            rows = []
        total += len(rows)
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
    result["selected_total"] = total
    return result


def run_one(category_id: int, nm_id: int, *, min_frequency: int, max_tokens: int) -> dict[str, Any]:
    product = _product_from_db(category_id, nm_id)
    candidates = _query_candidates(category_id, min_frequency=min_frequency)
    evidence = {
        "product": {
            "nm_id": nm_id,
            "title": product["title"],
            "description": product["description"],
            "subject_name": product["subject_name"],
            "key_characteristics": _compact_characteristics(product["characteristics"]),
        },
        "brand_level_style_hint": _category_expressive_axes(category_id),
        "photo_analysis": _vision_summary(nm_id),
    }
    out_dir = OUT_ROOT / f"category_{category_id}" / f"nm_{nm_id}"
    prompt = _prompt_text(evidence, candidates)
    _write_json(out_dir / "input_evidence.json", evidence)
    _write_json(out_dir / "query_candidates.json", candidates)
    _write_text(out_dir / "prompt.txt", prompt)

    raw = _call_openrouter(prompt, max_tokens=max_tokens)
    _write_json(out_dir / "raw_response.json", raw)
    parsed = _extract_json_object(raw["choices"][0]["message"]["content"])
    summary = _summary(parsed)
    summary.update(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "category_id": category_id,
            "nm_id": nm_id,
            "subject_name": product["subject_name"],
            "candidate_count": len(candidates),
            "usage": raw.get("usage") or {},
            "finish_reason": raw.get("choices", [{}])[0].get("finish_reason"),
        }
    )
    _write_json(out_dir / "parsed_selection.json", parsed)
    _write_json(out_dir / "selection_summary.json", summary)

    lines = [
        f"# Query Selection {category_id} / {nm_id}",
        "",
        f"- subject: `{product['subject_name']}`",
        f"- title: `{product['title']}`",
        f"- model: `{MODEL}`",
        f"- candidates: `{len(candidates)}`",
        f"- selected_total: `{summary['selected_total']}`",
        f"- finish_reason: `{summary.get('finish_reason')}`",
        f"- usage: `{json.dumps(summary['usage'], ensure_ascii=False)}`",
        "",
    ]
    for bucket in ["primary", "secondary", "gift_style"]:
        lines.append(f"## {bucket}")
        for item in summary[bucket]["queries"]:
            lines.append(
                f"- `{item.get('cluster_id')}` {item.get('query')} "
                f"(confidence={item.get('confidence')}): {item.get('reason')}"
            )
        lines.append("")
    _write_text(out_dir / "selection_report.md", "\n".join(lines))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--item", action="append", required=True, help="category_id:nm_id")
    parser.add_argument("--min-frequency", type=int, default=500)
    parser.add_argument("--max-tokens", type=int, default=9000)
    args = parser.parse_args()

    summaries: list[dict[str, Any]] = []
    for raw_item in args.item:
        category_raw, nm_raw = raw_item.split(":", 1)
        summaries.append(
            run_one(
                int(category_raw),
                int(nm_raw),
                min_frequency=args.min_frequency,
                max_tokens=args.max_tokens,
            )
        )
    _write_json(OUT_ROOT / "multi_run_summary.json", summaries)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
