"""One-off LLM dedupe experiment for category 812 cluster representatives.

Reads the deterministic-deduped representatives artifact, asks a cheap LLM to
propose additional same-intent merges, and writes reviewable artifacts. No DB
reads or writes are performed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    ROOT
    / "tests"
    / "seo"
    / "phase1q"
    / "category_812"
    / "dedupe_cluster_representatives"
    / "representatives_after.json"
)
DEFAULT_OUT_DIR = (
    ROOT
    / "tests"
    / "seo"
    / "phase1q"
    / "category_812"
    / "llm_dedupe_cluster_representatives"
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
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


def _representatives(path: Path) -> list[dict[str, Any]]:
    rows = _read_json(path)
    if not isinstance(rows, list):
        raise ValueError("representatives artifact must be a list")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        cluster_id = row.get("kept_cluster_id")
        query = str(row.get("kept_query") or "").strip()
        if cluster_id is None or not query:
            continue
        result.append(
            {
                "cluster_id": int(cluster_id),
                "query": query,
            }
        )
    return result


def _prompt_payload(representatives: list[dict[str, Any]], *, max_merge_groups: int) -> dict[str, Any]:
    queries = [[item["cluster_id"], item["query"]] for item in representatives]
    return {
        "task": "deduplicate_search_query_cluster_representatives",
        "category": "WB search queries for one product category",
        "goal": "Propose extra merges only when queries express the same buyer intent.",
        "rules": [
            "Return JSON only.",
            "Do not classify relevance to any SKU.",
            "Do not rank queries.",
            "Do not merge broad category queries with specific attribute/use-case queries.",
            "Do not merge different product types.",
            "Do not merge different recipients, occasions, materials, sizes, colors, visual motifs, or use cases.",
            "Do not merge queries merely because they share the category product noun.",
            "Do not use numeric/id adjacency as a signal.",
            "A merge is allowed only when the query wording is nearly interchangeable for a buyer.",
            "When unsure, keep separate.",
            "Output only proposed merges; do not list every kept query.",
            f"Return at most {int(max_merge_groups)} highest-confidence merge groups.",
            "Each merge group may contain at most 8 ids in merge.",
            "Prefer precision over recall: it is acceptable to miss duplicates.",
            "Use cluster_id values exactly as provided.",
        ],
        "output_schema": {
            "merge_groups": [
                {
                    "keep": "cluster_id to keep",
                    "merge": ["cluster_id values to merge into keep"],
                    "reason_code": "same_intent | morphology | word_order | minor_preposition | other",
                    "confidence": "high | medium | low",
                }
            ],
            "warnings": [],
        },
        "queries": queries,
    }


def _call_openrouter(*, payload: dict[str, Any], model: str, max_tokens: int, timeout_seconds: float) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    messages = [
        {
            "role": "system",
            "content": (
                "You are a conservative search-query deduplication assistant. "
                "You merge only true same-intent duplicates and preserve distinct buyer intent."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]
    request_payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "top_p": 1,
        "max_tokens": int(max_tokens),
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ecomcore.local",
                "X-Title": "EcomCore SEO LLM Dedupe Experiment",
            },
            json=request_payload,
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("OpenRouter returned a non-object response")
    return data


def _validate(parsed: Mapping[str, Any], representatives: list[dict[str, Any]]) -> dict[str, Any]:
    valid_ids = {int(item["cluster_id"]) for item in representatives}
    query_by_id = {int(item["cluster_id"]): str(item["query"]) for item in representatives}
    groups = parsed.get("merge_groups") or []
    if not isinstance(groups, list):
        groups = []

    normalized_groups: list[dict[str, Any]] = []
    invalid_ids: list[int] = []
    duplicate_removed_ids: list[int] = []
    seen_removed: set[int] = set()
    seen_kept: set[int] = set()

    for index, raw_group in enumerate(groups):
        if not isinstance(raw_group, Mapping):
            continue
        try:
            keep = int(raw_group.get("keep"))
        except Exception:
            continue
        raw_merge = raw_group.get("merge") or []
        if not isinstance(raw_merge, list):
            raw_merge = []
        merge: list[int] = []
        for raw_id in raw_merge:
            try:
                cluster_id = int(raw_id)
            except Exception:
                continue
            if cluster_id == keep:
                continue
            merge.append(cluster_id)
        ids = [keep, *merge]
        for cluster_id in ids:
            if cluster_id not in valid_ids:
                invalid_ids.append(cluster_id)
        for cluster_id in merge:
            if cluster_id in seen_removed:
                duplicate_removed_ids.append(cluster_id)
            seen_removed.add(cluster_id)
        seen_kept.add(keep)
        normalized_groups.append(
            {
                "group_id": f"llm-merge-{index + 1:04d}",
                "keep": keep,
                "keep_query": query_by_id.get(keep),
                "merge": merge,
                "merge_queries": [{"cluster_id": item, "query": query_by_id.get(item)} for item in merge],
                "reason_code": str(raw_group.get("reason_code") or "other"),
                "confidence": str(raw_group.get("confidence") or "unknown"),
            }
        )

    removed_ids = sorted(seen_removed)
    return {
        "input_count": len(representatives),
        "merge_group_count": len(normalized_groups),
        "removed_count": len(removed_ids),
        "deduped_count": len(representatives) - len(removed_ids),
        "invalid_ids": sorted(set(invalid_ids)),
        "duplicate_removed_ids": sorted(set(duplicate_removed_ids)),
        "kept_also_removed_ids": sorted(seen_kept.intersection(seen_removed)),
        "merge_groups": normalized_groups,
    }


def _write_report(path: Path, *, summary: Mapping[str, Any], sample_groups: list[Mapping[str, Any]]) -> None:
    lines = [
        "# LLM Dedupe Cluster Representatives 812",
        "",
        f"- created_at: `{summary.get('created_at')}`",
        f"- model: `{summary.get('model')}`",
        f"- input_count: `{summary.get('input_count')}`",
        f"- merge_group_count: `{summary.get('merge_group_count')}`",
        f"- removed_count: `{summary.get('removed_count')}`",
        f"- deduped_count: `{summary.get('deduped_count')}`",
        f"- invalid_ids: `{len(summary.get('invalid_ids') or [])}`",
        f"- duplicate_removed_ids: `{len(summary.get('duplicate_removed_ids') or [])}`",
        f"- kept_also_removed_ids: `{len(summary.get('kept_also_removed_ids') or [])}`",
        "",
        "## Sample Merge Groups",
        "",
    ]
    for group in sample_groups[:30]:
        lines.append(f"### {group.get('group_id')} — {group.get('reason_code')} / {group.get('confidence')}")
        lines.append(f"- keep: `{group.get('keep')}` — {group.get('keep_query')}")
        for item in group.get("merge_queries") or []:
            if isinstance(item, Mapping):
                lines.append(f"- merge: `{item.get('cluster_id')}` — {item.get('query')}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--model", default=os.getenv("OPENROUTER_CHAT_MODEL", "openai/gpt-4.1-mini"))
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--max-merge-groups", type=int, default=300)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    representatives = _representatives(input_path)
    payload = _prompt_payload(representatives, max_merge_groups=int(args.max_merge_groups))
    _write_json(out_dir / "llm_dedupe_prompt_payload.json", payload)

    raw_response = _call_openrouter(
        payload=payload,
        model=str(args.model),
        max_tokens=int(args.max_tokens),
        timeout_seconds=float(args.timeout_seconds),
    )
    _write_json(out_dir / "llm_dedupe_raw_response.json", raw_response)

    choices = raw_response.get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], Mapping) else {}
    content = message.get("content") if isinstance(message, Mapping) else ""
    parsed = _extract_json_object(str(content or ""))
    _write_json(out_dir / "llm_dedupe_parsed.json", parsed)

    validation = _validate(parsed, representatives)
    groups = validation.pop("merge_groups")
    created_at = datetime.now(tz=timezone.utc).isoformat()
    summary = {
        "created_at": created_at,
        "input_path": str(input_path),
        "model": str(raw_response.get("model") or args.model),
        "usage": raw_response.get("usage") if isinstance(raw_response.get("usage"), Mapping) else {},
        **validation,
    }
    _write_json(out_dir / "llm_dedupe_summary.json", summary)
    _write_json(out_dir / "llm_dedupe_merge_groups.json", groups)
    _write_report(out_dir / "llm_dedupe_report.md", summary=summary, sample_groups=groups)

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
