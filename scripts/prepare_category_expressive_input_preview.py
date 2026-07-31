#!/usr/bin/env python3
"""
Prepare category expressive evaluation inputs (NO LLM CALLS).

Outputs:
  - raw_reviews_preview.json
  - review_truncation_preview.json
  - title_preview.json
  - category_input_reviews_only.json
  - category_input_reviews_plus_titles.json

And a human preview doc:
  - docs/seo-module/16_category_expressive_input_preview.md
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import SessionLocal


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = Path("/data/internal_data/expressive_llm_eval")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _truncate(value: str, limit: int) -> str:
    text_value = str(value or "").strip()
    if limit <= 0:
        return ""
    if len(text_value) <= limit:
        return text_value
    return text_value[: max(0, limit - 1)].rstrip() + "…"


def _norm_key(value: str) -> str:
    text_value = str(value or "").lower().replace("ё", "е")
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value


def _approx_tokens(chars: int) -> int:
    return int(math.ceil(max(0, int(chars)) / 4.0))


@dataclass(frozen=True)
class SelectedCategory:
    category_id: int
    category_name: str
    sku_total: int
    sku_with_reviews: int
    reviews_total: int
    reviews_rating_ge_4: int


def _discover_top_category(*, project_id: int) -> SelectedCategory:
    sql = text(
        """
        WITH prod AS (
            SELECT
                p.project_id,
                p.nm_id::bigint AS nm_id,
                p.subject_id::int AS category_id,
                COALESCE(p.subject_name, '')::text AS category_name
            FROM products p
            WHERE p.project_id = :project_id
              AND p.subject_id IS NOT NULL
              AND p.nm_id IS NOT NULL
        ),
        review_texts AS (
            SELECT
                pr.category_id,
                pr.category_name,
                pr.nm_id,
                fs.product_valuation::int AS rating,
                NULLIF(btrim(COALESCE(fs.raw->>'text','') || ' ' || COALESCE(fs.raw->>'pros','') || ' ' || COALESCE(fs.raw->>'cons','')), '') AS review_text
            FROM prod pr
            JOIN wb_feedback_snapshots fs
              ON fs.project_id = pr.project_id
             AND fs.nm_id = pr.nm_id
        )
        SELECT
            category_id,
            MAX(category_name) AS category_name,
            (SELECT COUNT(DISTINCT p2.nm_id)::int FROM prod p2 WHERE p2.category_id = review_texts.category_id) AS sku_total,
            COUNT(DISTINCT nm_id)::int AS sku_with_reviews,
            COUNT(*)::int AS reviews_total,
            COUNT(*) FILTER (WHERE rating >= 4 AND review_text IS NOT NULL)::int AS reviews_rating_ge_4
        FROM review_texts
        GROUP BY category_id
        ORDER BY reviews_rating_ge_4 DESC, reviews_total DESC
        LIMIT 1
        """
    )
    with SessionLocal() as session:
        row = session.execute(sql, {"project_id": int(project_id)}).mappings().first()
        if not row:
            raise RuntimeError("No category with reviews found for this project_id.")
        return SelectedCategory(
            category_id=int(row["category_id"]),
            category_name=str(row.get("category_name") or "").strip() or f"subject_id={int(row['category_id'])}",
            sku_total=int(row.get("sku_total") or 0),
            sku_with_reviews=int(row.get("sku_with_reviews") or 0),
            reviews_total=int(row.get("reviews_total") or 0),
            reviews_rating_ge_4=int(row.get("reviews_rating_ge_4") or 0),
        )


def _load_category_stats(*, project_id: int, category_id: int) -> SelectedCategory:
    sql = text(
        """
        WITH prod AS (
            SELECT
                p.project_id,
                p.nm_id::bigint AS nm_id,
                p.subject_id::int AS category_id,
                COALESCE(p.subject_name, '')::text AS category_name
            FROM products p
            WHERE p.project_id = :project_id
              AND p.subject_id = :category_id
              AND p.nm_id IS NOT NULL
        ),
        review_texts AS (
            SELECT
                pr.category_id,
                pr.category_name,
                pr.nm_id,
                fs.product_valuation::int AS rating,
                NULLIF(btrim(COALESCE(fs.raw->>'text','') || ' ' || COALESCE(fs.raw->>'pros','') || ' ' || COALESCE(fs.raw->>'cons','')), '') AS review_text
            FROM prod pr
            LEFT JOIN wb_feedback_snapshots fs
              ON fs.project_id = pr.project_id
             AND fs.nm_id = pr.nm_id
        )
        SELECT
            category_id,
            MAX(category_name) AS category_name,
            (SELECT COUNT(DISTINCT p2.nm_id)::int FROM prod p2) AS sku_total,
            COUNT(DISTINCT nm_id) FILTER (WHERE rating IS NOT NULL)::int AS sku_with_reviews,
            COUNT(*) FILTER (WHERE rating IS NOT NULL)::int AS reviews_total,
            COUNT(*) FILTER (WHERE rating >= 4 AND review_text IS NOT NULL)::int AS reviews_rating_ge_4
        FROM review_texts
        GROUP BY category_id
        """
    )
    with SessionLocal() as session:
        row = session.execute(sql, {"project_id": int(project_id), "category_id": int(category_id)}).mappings().first()
        if not row:
            raise RuntimeError("Category not found or no products for this category.")
        return SelectedCategory(
            category_id=int(row["category_id"]),
            category_name=str(row.get("category_name") or "").strip() or f"subject_id={int(row['category_id'])}",
            sku_total=int(row.get("sku_total") or 0),
            sku_with_reviews=int(row.get("sku_with_reviews") or 0),
            reviews_total=int(row.get("reviews_total") or 0),
            reviews_rating_ge_4=int(row.get("reviews_rating_ge_4") or 0),
        )


def _select_reviews(
    *,
    project_id: int,
    category_id: int,
    max_reviews: int,
    min_rating: int,
) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT
            fs.id::bigint AS id,
            fs.external_id::text AS external_id,
            fs.nm_id::bigint AS nm_id,
            fs.product_valuation::int AS rating,
            fs.created_date AS created_date,
            p.subject_id::int AS category_id,
            COALESCE(p.subject_name, '')::text AS category_name,
            COALESCE(p.title, '')::text AS product_title,
            COALESCE(fs.raw->>'text','')::text AS raw_text,
            COALESCE(fs.raw->>'pros','')::text AS raw_pros,
            COALESCE(fs.raw->>'cons','')::text AS raw_cons
        FROM wb_feedback_snapshots fs
        JOIN products p
          ON p.project_id = fs.project_id
         AND p.nm_id = fs.nm_id
        WHERE fs.project_id = :project_id
          AND p.subject_id = :category_id
          AND fs.product_valuation >= :min_rating
          AND NULLIF(btrim(COALESCE(fs.raw->>'text','') || ' ' || COALESCE(fs.raw->>'pros','') || ' ' || COALESCE(fs.raw->>'cons','')), '') IS NOT NULL
        ORDER BY fs.created_date DESC NULLS LAST, fs.id DESC
        LIMIT :limit
        """
    )
    with SessionLocal() as session:
        rows = (
            session.execute(
                sql,
                {
                    "project_id": int(project_id),
                    "category_id": int(category_id),
                    "min_rating": int(min_rating),
                    "limit": int(max(1, max_reviews)),
                },
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


def _review_compose_text(row: dict[str, Any]) -> str:
    parts = [str(row.get("raw_text") or ""), str(row.get("raw_pros") or ""), str(row.get("raw_cons") or "")]
    parts = [p.strip() for p in parts if str(p or "").strip()]
    return "\n".join(parts).strip()


def _dedup_texts(items: list[dict[str, Any]], *, text_key: str, norm_key: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        key = str(item.get(norm_key) or "")
        if not key:
            continue
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(item)
    meta = {"input_count": len(items), "dedup_count": len(out), "dropped_duplicates": int(dropped), "text_key": text_key, "norm_key": norm_key}
    return out, meta


def _build_prompts(*, category_name: str) -> tuple[str, str]:
    safe_category_name = _truncate(category_name, 120).replace('"', "'")
    prompt_a = (
        "TASK=category_expressive_from_reviews\n"
        "You will receive JSON payload with:\n"
        "- category_name\n"
        "- reviews[] (primary evidence)\n\n"
        "Rules:\n"
        "- Do not invent. If no signals, return empty vibes.\n"
        "- Every vibe MUST have evidence_spans (exact substrings from reviews).\n"
        "- evidence_spans must be <= 80 chars and contain no newlines.\n"
        "- Return JSON only.\n\n"
        "Return schema:\n"
        "{\n"
        '  "version": "v1",\n'
        '  "task": "category",\n'
        f'  "category_name": "{safe_category_name}",\n'
        '  "vibes": [\n'
        "    {\n"
        '      "label": "other",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_spans": ["..."],\n'
        '      "notes": ""\n'
        "    }\n"
        "  ],\n"
        '  "summary": "",\n'
        '  "warnings": []\n'
        "}\n"
    )

    prompt_b = (
        "TASK=category_expressive_from_reviews_plus_titles\n"
        "You will receive JSON payload with:\n"
        "- category_name\n"
        "- reviews[] (PRIMARY evidence)\n"
        "- titles[] (SECONDARY support)\n\n"
        "Rules:\n"
        "- Reviews are PRIMARY evidence.\n"
        "- Titles are SECONDARY support only.\n"
        "- No conclusion may rely on titles alone if unsupported by reviews.\n"
        "- Do not invent. If no signals, return empty vibes.\n"
        "- Every vibe MUST have evidence_spans (exact substrings from reviews).\n"
        "- evidence_spans must be <= 80 chars and contain no newlines.\n"
        "- Return JSON only.\n\n"
        "Return schema:\n"
        "{\n"
        '  "version": "v1",\n'
        '  "task": "category",\n'
        f'  "category_name": "{safe_category_name}",\n'
        '  "vibes": [\n'
        "    {\n"
        '      "label": "other",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_spans": ["..."],\n'
        '      "notes": ""\n'
        "    }\n"
        "  ],\n"
        '  "summary": "",\n'
        '  "warnings": []\n'
        "}\n"
    )
    return prompt_a, prompt_b


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare category expressive inputs (reviews-only vs reviews+titles).")
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--category-id", type=int, default=None)
    parser.add_argument("--max-reviews", type=int, default=100)
    parser.add_argument("--min-rating", type=int, default=4)
    parser.add_argument("--review-truncate", type=int, default=220)
    parser.add_argument("--title-truncate", type=int, default=120)
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--preview-md",
        type=str,
        default=str(PROJECT_ROOT / "docs" / "seo-module" / "16_category_expressive_input_preview.md"),
        help="Where to write the preview markdown (inside container when running in docker).",
    )
    args = parser.parse_args()

    project_id = int(args.project_id)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    if args.category_id is None:
        selected = _discover_top_category(project_id=project_id)
    else:
        selected = _load_category_stats(project_id=project_id, category_id=int(args.category_id))

    # --- Reviews preview (raw selection + technical normalization + dedup) ---
    selected_rows = _select_reviews(
        project_id=project_id,
        category_id=selected.category_id,
        max_reviews=int(args.max_reviews),
        min_rating=int(args.min_rating),
    )

    raw_preview_rows: list[dict[str, Any]] = []
    trunc_preview_rows: list[dict[str, Any]] = []
    for row in selected_rows:
        composed = _review_compose_text(row)
        trimmed = composed.strip()
        truncated = _truncate(trimmed, int(args.review_truncate))
        norm = _norm_key(truncated)
        raw_preview_rows.append(
            {
                "external_id": str(row.get("external_id") or ""),
                "nm_id": int(row.get("nm_id") or 0),
                "rating": int(row.get("rating") or 0),
                "created_date": row.get("created_date").isoformat() if getattr(row.get("created_date"), "isoformat", None) else None,
                "raw": {
                    "text": str(row.get("raw_text") or ""),
                    "pros": str(row.get("raw_pros") or ""),
                    "cons": str(row.get("raw_cons") or ""),
                },
                "composed_text_trimmed": trimmed,
                "composed_text_truncated_220": truncated,
                "normalized_key": norm,
            }
        )
        trunc_preview_rows.append(
            {
                "external_id": str(row.get("external_id") or ""),
                "nm_id": int(row.get("nm_id") or 0),
                "rating": int(row.get("rating") or 0),
                "text_trimmed": trimmed,
                "text_truncated": truncated,
                "trimmed_len": len(trimmed),
                "truncated_len": len(truncated),
            }
        )

    # Dedup on normalized_key
    dedup_reviews, dedup_meta = _dedup_texts(raw_preview_rows, text_key="composed_text_truncated_220", norm_key="normalized_key")
    # Build final review strings list for payloads
    reviews_list = [str(r["composed_text_truncated_220"]) for r in dedup_reviews][: int(args.max_reviews)]

    _write_json(
        out_dir / "raw_reviews_preview.json",
        {
            "project_id": project_id,
            "category": asdict(selected),
            "filters": {"min_rating": int(args.min_rating), "limit": int(args.max_reviews)},
            "raw_selected_count": len(raw_preview_rows),
            "dedup": dedup_meta,
            "rows": dedup_reviews,
        },
    )
    _write_json(
        out_dir / "review_truncation_preview.json",
        {
            "project_id": project_id,
            "category": asdict(selected),
            "truncate_limit": int(args.review_truncate),
            "raw_selected_count": len(trunc_preview_rows),
            "dedup": dedup_meta,
            "rows": [r for r in trunc_preview_rows if r.get("external_id") in {d.get("external_id") for d in dedup_reviews}],
        },
    )

    # --- Titles preview (same SKU scope as selected reviews) ---
    nm_ids = sorted({int(r["nm_id"]) for r in dedup_reviews if int(r.get("nm_id") or 0) > 0})
    titles_raw: list[dict[str, Any]] = []
    if nm_ids:
        sql_titles = text(
            """
            SELECT p.nm_id::bigint AS nm_id, COALESCE(p.title,'')::text AS title
            FROM products p
            WHERE p.project_id = :project_id
              AND p.subject_id = :category_id
              AND p.nm_id = ANY(:nm_ids)
            ORDER BY p.nm_id ASC
            """
        )
        with SessionLocal() as session:
            rows = session.execute(
                sql_titles,
                {"project_id": project_id, "category_id": selected.category_id, "nm_ids": nm_ids},
            ).mappings().all()
            for row in rows:
                title = str(row.get("title") or "").strip()
                title_trunc = _truncate(title, int(args.title_truncate))
                titles_raw.append(
                    {
                        "nm_id": int(row.get("nm_id") or 0),
                        "title_trimmed": title,
                        "title_truncated_120": title_trunc,
                        "normalized_key": _norm_key(title_trunc),
                    }
                )

    dedup_titles, titles_meta = _dedup_texts(titles_raw, text_key="title_truncated_120", norm_key="normalized_key")
    titles_list = [str(t["title_truncated_120"]) for t in dedup_titles if str(t.get("title_truncated_120") or "").strip()]

    _write_json(
        out_dir / "title_preview.json",
        {
            "project_id": project_id,
            "category": asdict(selected),
            "nm_ids_scope": nm_ids,
            "truncate_limit": int(args.title_truncate),
            "dedup": titles_meta,
            "rows": dedup_titles,
            "titles_unique": titles_list,
        },
    )

    payload_a = {"category_name": selected.category_name, "reviews": reviews_list}
    payload_b = {"category_name": selected.category_name, "reviews": reviews_list, "titles": titles_list}
    _write_json(out_dir / "category_input_reviews_only.json", payload_a)
    _write_json(out_dir / "category_input_reviews_plus_titles.json", payload_b)

    # --- Prompts + preview markdown ---
    prompt_a, prompt_b = _build_prompts(category_name=selected.category_name)

    payload_a_json = json.dumps(payload_a, ensure_ascii=False, indent=2)
    payload_b_json = json.dumps(payload_b, ensure_ascii=False, indent=2)

    samples_reviews = reviews_list[:10]
    samples_titles = titles_list[:10]

    md = []
    md.append("# Category expressive input preview (reviews-only vs reviews+titles)")
    md.append("")
    md.append(f"Date: 2026-04-21")
    md.append("")
    md.append("## 1) Category selection")
    md.append(f"- project_id: `{project_id}`")
    md.append(f"- category_id: `{selected.category_id}`")
    md.append(f"- category_name: `{selected.category_name}`")
    md.append(f"- sku_total (products in category): `{selected.sku_total}`")
    md.append(f"- sku_with_reviews (any rating): `{selected.sku_with_reviews}`")
    md.append(f"- reviews_total (all ratings): `{selected.reviews_total}`")
    md.append(f"- reviews_rating>=4 (non-empty text/pros/cons): `{selected.reviews_rating_ge_4}`")
    md.append("")
    md.append("## 2) Preview counts (after truncation + dedup)")
    md.append(f"- reviews count after dedup: `{len(reviews_list)}`")
    md.append(f"- titles count after dedup: `{len(titles_list)}`")
    md.append("")
    md.append("## 3) 10 sample reviews")
    md.append("```")
    for r in samples_reviews:
        md.append(r)
        md.append("")
    md.append("```")
    md.append("")
    md.append("## 4) 10 sample titles")
    md.append("```")
    for t in samples_titles:
        md.append(t)
    md.append("```")
    md.append("")
    md.append("## 5) Payload A (reviews-only) — exact")
    md.append("```json")
    md.append(payload_a_json)
    md.append("```")
    md.append("")
    md.append("## 6) Payload B (reviews + titles) — exact")
    md.append("```json")
    md.append(payload_b_json)
    md.append("```")
    md.append("")
    md.append("## 7) Prompt A (reviews-only) — exact")
    md.append("```")
    md.append(prompt_a)
    md.append("```")
    md.append("")
    md.append("## 8) Prompt B (reviews + titles) — exact")
    md.append("```")
    md.append(prompt_b)
    md.append("```")
    md.append("")
    md.append("## 9) Size estimates")
    md.append("")
    md.append("| Item | chars | approx_tokens |")
    md.append("| --- | ---: | ---: |")
    md.append(f"| payload A JSON | {len(payload_a_json)} | {_approx_tokens(len(payload_a_json))} |")
    md.append(f"| payload B JSON | {len(payload_b_json)} | {_approx_tokens(len(payload_b_json))} |")
    md.append(f"| prompt A | {len(prompt_a)} | {_approx_tokens(len(prompt_a))} |")
    md.append(f"| prompt B | {len(prompt_b)} | {_approx_tokens(len(prompt_b))} |")

    md_text = "\n".join(md).rstrip() + "\n"
    preview_md_path = Path(str(args.preview_md))
    _ensure_dir(preview_md_path.parent)
    preview_md_path.write_text(md_text, encoding="utf-8")

    # Print a short summary (no secrets, no LLM calls)
    print(
        json.dumps(
            {
                "status": "ok",
                "project_id": project_id,
                "category_id": selected.category_id,
                "category_name": selected.category_name,
                "reviews_selected_dedup": len(reviews_list),
                "titles_selected_dedup": len(titles_list),
                "out_dir": str(out_dir),
                "preview_md": str(preview_md_path),
            },
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
