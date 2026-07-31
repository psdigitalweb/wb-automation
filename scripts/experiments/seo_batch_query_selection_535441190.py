"""Batch query-selection experiment for SKU 535441190.

Runs the current production query-selection prompt over category 812 candidates
in fixed-size batches. This script is read-only for the database: it builds the
same preview input used by production, calls the LLM directly, and writes
artifacts under tests/seo/phase1q/.
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
    _candidate_lookup_by_id,
    _input_payload_from_parts,
    _parse_json_object,
    _selection_from_line_payload,
    _system_prompt,
    _user_prompt,
    build_production_query_selection_preview,
)
from app.services.seo.providers.base import ChatMessage
from app.services.seo.providers.openrouter import OpenRouterProvider


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = 1
CATEGORY_ID = 812
NM_ID = 535441190
OUT_DIR = ROOT / "tests" / "seo" / "phase1q" / "category_812" / "batch_200_query_selection_535441190"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _chunks(items: Sequence[Any], size: int) -> list[list[Any]]:
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def _query_key(item: Mapping[str, Any]) -> int | str:
    cluster_id = item.get("cluster_id")
    if cluster_id is not None:
        return int(cluster_id)
    return str(item.get("query") or "")


def _merge_unique(rows: Sequence[Mapping[str, Any]], *, seen: set[int | str]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in rows:
        key = _query_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(row))
    return merged


def _flatten_operators(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line, items in groups.items():
        for item in items:
            payload = dict(item)
            payload["meaning_line"] = payload.get("meaning_line") or line
            rows.append(payload)
    return rows


def run(*, batch_size: int, max_tokens: int) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        preview = build_production_query_selection_preview(
            session,
            project_id=PROJECT_ID,
            nm_id=NM_ID,
            category_id=CATEGORY_ID,
            preview_limit=2300,
        )

    if not preview.readiness.can_run:
        raise RuntimeError("; ".join(preview.readiness.blocking_reasons))

    all_candidates = list(preview.candidates.items)
    batches = _chunks(all_candidates, batch_size)
    provider = OpenRouterProvider(
        chat_model=PRODUCTION_QUERY_SELECTION_MODEL,
        timeout_seconds=180.0,
        response_format={"type": "json_object"},
    )

    selected_seen: set[int | str] = set()
    operator_seen: set[int | str] = set()
    selected_unified: list[dict[str, Any]] = []
    operator_unified: list[dict[str, Any]] = []
    batch_summaries: list[dict[str, Any]] = []

    for batch_index, candidates in enumerate(batches, start=1):
        input_payload = _input_payload_from_parts(
            product=preview.product,
            category=preview.category,
            ai_vision=preview.ai_vision,
            candidates=candidates,
            total_candidate_count=preview.candidates.total_candidate_count or preview.candidates.candidate_count,
        )
        messages = [
            ChatMessage(role="system", content=_system_prompt()),
            ChatMessage(role="user", content=_user_prompt(input_payload)),
        ]
        batch_dir = OUT_DIR / f"batch_{batch_index:02d}"
        _write_json(batch_dir / "input.json", input_payload)
        _write_text(batch_dir / "prompt.txt", messages[1].content)

        response = provider.generate_chat(messages, temperature=0.1, top_p=0.9, max_tokens=max_tokens)
        raw_payload = dict(response.raw_response or {}) or {"model": response.model, "content": response.content}
        _write_json(batch_dir / "raw_response.json", raw_payload)

        parsed = _parse_json_object(response.content)
        _write_json(batch_dir / "parsed.json", parsed)

        candidates_by_id = _candidate_lookup_by_id(input_payload)
        meaning_lines, selected, operators = _selection_from_line_payload(
            parsed.get("lines"),
            candidates_by_id=candidates_by_id,
        )
        selected_rows = [item.model_dump(mode="json") for item in selected]
        operator_rows = _flatten_operators(
            {
                key: [item.model_dump(mode="json") for item in value]
                for key, value in operators.items()
            }
        )
        selected_new = _merge_unique(selected_rows, seen=selected_seen)
        operator_new = [
            row
            for row in _merge_unique(operator_rows, seen=operator_seen)
            if _query_key(row) not in selected_seen
        ]
        selected_unified.extend(selected_new)
        operator_unified.extend(operator_new)

        batch_summary = {
            "batch_index": batch_index,
            "candidate_count": len(candidates),
            "first_candidate": candidates[0].model_dump(mode="json") if candidates else None,
            "last_candidate": candidates[-1].model_dump(mode="json") if candidates else None,
            "finish_reason": (raw_payload.get("choices") or [{}])[0].get("finish_reason")
            if isinstance(raw_payload.get("choices"), list)
            else None,
            "usage": raw_payload.get("usage") or {},
            "meaning_lines": [item.model_dump(mode="json") for item in meaning_lines],
            "selected_count": len(selected_rows),
            "operator_count": len(operator_rows),
            "selected_new_count": len(selected_new),
            "operator_new_count": len(operator_new),
            "selected": selected_rows,
            "operator_candidates": operator_rows,
        }
        _write_json(batch_dir / "summary.json", batch_summary)
        batch_summaries.append(batch_summary)
        print(
            json.dumps(
                {
                    "batch": batch_index,
                    "candidates": len(candidates),
                    "selected": len(selected_rows),
                    "operator": len(operator_rows),
                    "selected_unified": len(selected_unified),
                    "operator_unified": len(operator_unified),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "category_id": CATEGORY_ID,
        "nm_id": NM_ID,
        "model": PRODUCTION_QUERY_SELECTION_MODEL,
        "prompt_version": PRODUCTION_QUERY_SELECTION_PROMPT_VERSION,
        "batch_size": batch_size,
        "batch_count": len(batches),
        "candidate_count": len(all_candidates),
        "selected_unified_count": len(selected_unified),
        "operator_unified_count": len(operator_unified),
        "selected_unified": selected_unified,
        "operator_unified": operator_unified,
        "batches": batch_summaries,
    }
    _write_json(OUT_DIR / "summary.json", summary)

    report_lines = [
        "# Batch 200 Query Selection 535441190",
        "",
        f"- model: `{PRODUCTION_QUERY_SELECTION_MODEL}`",
        f"- prompt_version: `{PRODUCTION_QUERY_SELECTION_PROMPT_VERSION}`",
        f"- candidates: `{len(all_candidates)}`",
        f"- batch_size: `{batch_size}`",
        f"- batches: `{len(batches)}`",
        f"- selected_unified: `{len(selected_unified)}`",
        f"- operator_unified: `{len(operator_unified)}`",
        "",
        "## Selected Unified",
    ]
    for item in selected_unified:
        report_lines.append(
            f"- `{item.get('cluster_id')}` {item.get('query')} "
            f"[{item.get('meaning_line')}] freq={item.get('frequency')}"
        )
    report_lines.append("")
    report_lines.append("## Operator Unified")
    for item in operator_unified:
        report_lines.append(
            f"- `{item.get('cluster_id')}` {item.get('query')} "
            f"[{item.get('meaning_line')}] freq={item.get('frequency')}"
        )
    _write_text(OUT_DIR / "report.md", "\n".join(report_lines) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--max-tokens", type=int, default=1800)
    args = parser.parse_args()
    summary = run(batch_size=args.batch_size, max_tokens=args.max_tokens)
    print(
        json.dumps(
            {
                "status": "closed",
                "artifact_dir": str(OUT_DIR),
                "candidate_count": summary["candidate_count"],
                "batch_count": summary["batch_count"],
                "selected_unified_count": summary["selected_unified_count"],
                "operator_unified_count": summary["operator_unified_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
