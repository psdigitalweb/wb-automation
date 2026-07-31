"""Final cleanup pass for batched query-selection experiment.

Reads the unified candidates produced by seo_batch_query_selection_535441190.py,
asks the LLM to reduce them to a cleaner operator-sized list, and writes
artifacts only. No database writes.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.db import SessionLocal
from app.services.seo.production_query_selection import (
    PRODUCTION_QUERY_SELECTION_MODEL,
    PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
    _input_payload_from_parts,
    build_production_query_selection_preview,
)
from app.services.seo.providers.base import ChatMessage
from app.services.seo.providers.openrouter import OpenRouterProvider


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = 1
CATEGORY_ID = 812
NM_ID = 535441190
BATCH_DIR = ROOT / "tests" / "seo" / "phase1q" / "category_812" / "batch_200_query_selection_535441190"
OUT_DIR = ROOT / "tests" / "seo" / "phase1q" / "category_812" / "batch_200_query_selection_535441190_final"
FINAL_PROMPT_VERSION = f"{PRODUCTION_QUERY_SELECTION_PROMPT_VERSION}_final_cleanup_v1"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _candidate_key(item: Mapping[str, Any]) -> int | str:
    cluster_id = item.get("cluster_id")
    if cluster_id is not None:
        return int(cluster_id)
    return str(item.get("query") or "")


def _merge_sources(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int | str] = set()
    for source, source_rows in (
        ("selected", summary.get("selected_unified")),
        ("operator_candidate", summary.get("operator_unified")),
    ):
        if not isinstance(source_rows, Sequence) or isinstance(source_rows, (str, bytes)):
            continue
        for item in source_rows:
            if not isinstance(item, Mapping):
                continue
            key = _candidate_key(item)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "id": item.get("cluster_id"),
                    "query": item.get("query"),
                    "frequency": item.get("frequency"),
                    "line": item.get("meaning_line"),
                    "source": source,
                }
            )
    return rows


def _format_candidates_table(candidates: Sequence[Mapping[str, Any]]) -> str:
    lines = ["id | запрос | частотность | линия | источник"]
    for item in candidates:
        lines.append(
            f"{item.get('id')} | {item.get('query')} | {item.get('frequency') or ''} | "
            f"{item.get('line') or ''} | {item.get('source') or ''}"
        )
    return "\n".join(lines)


def _prompt(product_context: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    return (
        "Ты финальный редактор SEO-запросов для одного товара.\n\n"
        "У тебя уже есть широкий список кандидатов, найденный по батчам. "
        "Твоя задача - НЕ искать новые запросы, а вычистить этот список до финального operator shortlist.\n\n"
        "Цель:\n"
        "- вернуть около 40-50 запросов, если столько действительно подходит;\n"
        "- убрать мусор и несовпадающие конкретные атрибуты;\n"
        "- сохранить покрытие разных смысловых линий товара: точный товар, материал, напитки, принт/визуальный мотив, "
        "милота/эстетика, подарок, аудитория, но только когда это подтверждено товаром.\n\n"
        "Жёсткие правила:\n"
        "- Выбирай только из таблицы candidates ниже.\n"
        "- Не добавляй новые id и новые тексты запросов.\n"
        "- Если запрос содержит конкретный атрибут, которого нет в товаре, не выбирай его.\n"
        "- Не выбирай другой принт/персонажа/животное, если он не совпадает с фото или карточкой.\n"
        "- Не выбирай другой цвет, объем, размер, комплектность, крышку, ложку, блюдце, набор, подогрев, если это не подтверждено.\n"
        "- Не выбирай запрос только из-за высокой частотности.\n"
        "- Покупательский смысл товара важнее частотности.\n"
        "- Если запрос спорный, но может быть полезен оператору, положи его в operator_candidates.\n"
        "- rejected не возвращай: всё, что не выбрано, отклонено по умолчанию.\n\n"
        "Верни JSON строго такого вида:\n"
        "{\n"
        "  \"selected\": [58658, 58768],\n"
        "  \"operator_candidates\": [65927, 58648]\n"
        "}\n\n"
        "Контекст товара:\n"
        f"{product_context}\n\n"
        "Candidates:\n"
        f"{_format_candidates_table(candidates)}"
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    stripped = str(content or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start : end + 1]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object")
    return parsed


def _ids(value: Any) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    result: list[int] = []
    seen: set[int] = set()
    for raw in value:
        try:
            item = int(raw)
        except (TypeError, ValueError):
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def run(*, max_tokens: int) -> dict[str, Any]:
    summary = _read_json(BATCH_DIR / "summary.json")
    candidates = _merge_sources(summary)
    by_id = {int(item["id"]): item for item in candidates if item.get("id") is not None}

    with SessionLocal() as session:
        preview = build_production_query_selection_preview(
            session,
            project_id=PROJECT_ID,
            nm_id=NM_ID,
            category_id=CATEGORY_ID,
            preview_limit=12,
        )
    context_payload = _input_payload_from_parts(
        product=preview.product,
        category=preview.category,
        ai_vision=preview.ai_vision,
        candidates=[],
        total_candidate_count=summary.get("candidate_count") or 0,
    )
    product_context = (
        f"Тип товара: {preview.product.product_type or 'товар'}\n"
        f"Название: {preview.product.title or ''}\n\n"
        f"Описание:\n{preview.product.description or ''}\n\n"
        f"Подсказка по стилю и фото:\n"
        f"{json.dumps(context_payload.get('category'), ensure_ascii=False)}\n"
        f"{json.dumps(context_payload.get('ai_vision'), ensure_ascii=False)}"
    )
    prompt = _prompt(product_context, candidates)
    messages = [
        ChatMessage(
            role="system",
            content=(
                "Ты строгий SEO-редактор. Верни только JSON с selected и operator_candidates, "
                "оба значения - массивы числовых id."
            ),
        ),
        ChatMessage(role="user", content=prompt),
    ]
    provider = OpenRouterProvider(
        chat_model=PRODUCTION_QUERY_SELECTION_MODEL,
        timeout_seconds=180.0,
        response_format={"type": "json_object"},
    )
    response = provider.generate_chat(messages, temperature=0.0, top_p=1.0, max_tokens=max_tokens)
    raw_payload = dict(response.raw_response or {}) or {"model": response.model, "content": response.content}
    parsed = _parse_json_object(response.content)
    selected_ids = _ids(parsed.get("selected"))
    operator_ids = [item for item in _ids(parsed.get("operator_candidates")) if item not in set(selected_ids)]
    selected = [by_id[item] for item in selected_ids if item in by_id]
    operator = [by_id[item] for item in operator_ids if item in by_id]

    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "category_id": CATEGORY_ID,
        "nm_id": NM_ID,
        "model": response.model,
        "prompt_version": FINAL_PROMPT_VERSION,
        "input_candidate_count": len(candidates),
        "selected_count": len(selected),
        "operator_count": len(operator),
        "usage": raw_payload.get("usage") or {},
        "finish_reason": (raw_payload.get("choices") or [{}])[0].get("finish_reason")
        if isinstance(raw_payload.get("choices"), list)
        else None,
        "selected": selected,
        "operator_candidates": operator,
        "parsed": parsed,
    }
    _write_text(OUT_DIR / "prompt.txt", prompt)
    _write_json(OUT_DIR / "input_candidates.json", candidates)
    _write_json(OUT_DIR / "raw_response.json", raw_payload)
    _write_json(OUT_DIR / "summary.json", result)

    report_lines = [
        "# Final Cleanup Query Selection 535441190",
        "",
        f"- model: `{response.model}`",
        f"- prompt_version: `{FINAL_PROMPT_VERSION}`",
        f"- input_candidates: `{len(candidates)}`",
        f"- selected: `{len(selected)}`",
        f"- operator_candidates: `{len(operator)}`",
        "",
        "## Selected",
    ]
    for item in selected:
        report_lines.append(f"- `{item.get('id')}` {item.get('query')} [{item.get('line')}] freq={item.get('frequency')}")
    report_lines.append("")
    report_lines.append("## Operator Candidates")
    for item in operator:
        report_lines.append(f"- `{item.get('id')}` {item.get('query')} [{item.get('line')}] freq={item.get('frequency')}")
    _write_text(OUT_DIR / "report.md", "\n".join(report_lines) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tokens", type=int, default=1000)
    args = parser.parse_args()
    result = run(max_tokens=args.max_tokens)
    print(
        json.dumps(
            {
                "status": "closed",
                "artifact_dir": str(OUT_DIR),
                "input_candidate_count": result["input_candidate_count"],
                "selected_count": result["selected_count"],
                "operator_count": result["operator_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
