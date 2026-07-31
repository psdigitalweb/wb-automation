"""Parity check: matcher_v2 vs legacy matcher for category 812 (D1).

Runs both matchers against the same DB snapshot for a small set of SKUs in
category 812, diffs their per-query bucket assignments, and writes an
artifact to
``docs/seo-module/implementation-plan/iteration_2/PARITY_SAMPLE_812.md``.

D1 bar:

* <= 10% bucket changes per SKU
* no ``primary <-> rejected`` flips (unless operator explicitly allows via
  ``--allow-flip <nm_id>``)

Usage:

    python -m scripts.parity_matcher_v2_812 --project-id 1
    python -m scripts.parity_matcher_v2_812 --project-id 1 --nm-ids 12345 67890
    python -m scripts.parity_matcher_v2_812 --project-id 1 \
        --allow-flip 12345 --allow-flip 67890

Exit code is non-zero if the D1 bar is breached (useful for CI dry-runs).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import desc, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    SeoSkuMeaningAnnotation,
    SeoMatcherRun,
    SeoMatcherResult,
)
from app.services.seo.matcher_v2 import run_matcher_v2  # noqa: E402
from app.services.seo.query_meaning_matcher.matcher import (  # noqa: E402
    run_meaning_aware_matcher,
)
from app.services.seo.query_pipeline import normalize_query_text  # noqa: E402


CATEGORY_ID = 812
DEFAULT_ARTIFACT = (
    ROOT
    / "docs"
    / "seo-module"
    / "implementation-plan"
    / "iteration_2"
    / "PARITY_SAMPLE_812.md"
)


@dataclass
class SkuParityRow:
    nm_id: int
    total_queries: int
    bucket_changes: int
    ratio: float
    flips: list[dict]
    breach_reason: str | None


def _legacy_bucket_map(session, *, project_id: int, nm_id: int) -> dict[str, str]:
    resp = run_meaning_aware_matcher(
        session,
        project_id=project_id,
        category_id=CATEGORY_ID,
        nm_id=nm_id,
        limit=400,
        include_rejected=True,
    )
    out: dict[str, str] = {}
    for bucket, items in resp.buckets.items():
        for item in items:
            out[normalize_query_text(item.query)] = str(bucket)
    return out


def _candidate_bucket_map(session, *, project_id: int, nm_id: int) -> dict[str, str]:
    bundle = run_matcher_v2(
        session,
        project_id=project_id,
        category_id=CATEGORY_ID,
        nm_id=nm_id,
        limit=400,
        include_rejected=True,
    )
    out: dict[str, str] = {}
    rows = session.scalars(
        select(SeoMatcherResult).where(SeoMatcherResult.run_id == int(bundle.run_id))
    ).all()
    for row in rows:
        out[normalize_query_text(str(row.normalized_query_text or ""))] = str(row.bucket)
    return out


def _pick_default_nm_ids(session, *, project_id: int, limit: int) -> list[int]:
    rows = session.scalars(
        select(SeoSkuMeaningAnnotation.nm_id)
        .where(
            SeoSkuMeaningAnnotation.project_id == int(project_id),
            SeoSkuMeaningAnnotation.category_id == CATEGORY_ID,
        )
        .order_by(desc(SeoSkuMeaningAnnotation.updated_at))
        .distinct()
        .limit(limit * 2)
    ).all()
    seen: list[int] = []
    for nm in rows:
        nm_int = int(nm)
        if nm_int not in seen:
            seen.append(nm_int)
        if len(seen) >= limit:
            break
    return seen


def _diff_for_sku(
    legacy: dict[str, str], candidate: dict[str, str], *, allow_flip: bool
) -> SkuParityRow:
    keys = set(legacy) | set(candidate)
    total = len(keys) or 1
    bucket_changes = 0
    flips: list[dict] = []
    breach: str | None = None

    for key in keys:
        lb = legacy.get(key)
        cb = candidate.get(key)
        if lb is None or cb is None:
            bucket_changes += 1
            continue
        if lb != cb:
            bucket_changes += 1
            if {lb, cb} == {"primary", "rejected"}:
                flips.append(
                    {"normalized_query_text": key, "legacy": lb, "candidate": cb}
                )

    ratio = bucket_changes / total
    if ratio > 0.10:
        breach = f"bucket_change_ratio={ratio:.2%} > 10%"
    if flips and not allow_flip:
        breach = (breach + "; " if breach else "") + f"primary<->rejected flips={len(flips)}"

    return SkuParityRow(
        nm_id=0,  # caller fills this in
        total_queries=total,
        bucket_changes=bucket_changes,
        ratio=ratio,
        flips=flips,
        breach_reason=breach,
    )


def _render_markdown(
    *,
    project_id: int,
    rows: list[SkuParityRow],
    allowed_flips: set[int],
    verdict: str,
    generated_at: datetime,
) -> str:
    lines: list[str] = []
    lines.append("# Parity Sample — Category 812 (D1)")
    lines.append("")
    lines.append(f"- Generated at: `{generated_at.isoformat()}`")
    lines.append(f"- Project: `{project_id}`")
    lines.append(f"- Category: `{CATEGORY_ID}`")
    lines.append(f"- SKUs compared: `{len(rows)}`")
    lines.append(f"- Flip overrides allowed for: `{sorted(allowed_flips) or 'none'}`")
    lines.append(f"- D1 verdict: **{verdict}**")
    lines.append("")
    lines.append("## Thresholds (from pre-kickoff decision D1)")
    lines.append("")
    lines.append("- <= 10% bucket changes per SKU")
    lines.append("- no `primary <-> rejected` flips (operator may explicitly allow "
                 "per nm_id with `--allow-flip`)")
    lines.append("")
    lines.append("## Per-SKU results")
    lines.append("")
    lines.append("| nm_id | queries | bucket changes | ratio | flips | verdict |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        verdict_cell = "OK" if row.breach_reason is None else f"BREACH: {row.breach_reason}"
        lines.append(
            f"| {row.nm_id} | {row.total_queries} | {row.bucket_changes} | "
            f"{row.ratio:.2%} | {len(row.flips)} | {verdict_cell} |"
        )
    lines.append("")
    flips_present = [r for r in rows if r.flips]
    if flips_present:
        lines.append("## `primary <-> rejected` flips (full list)")
        lines.append("")
        for row in flips_present:
            lines.append(f"### nm_id={row.nm_id}")
            for flip in row.flips:
                lines.append(
                    f"- `{flip['normalized_query_text']}`: legacy=`{flip['legacy']}`, "
                    f"candidate=`{flip['candidate']}`"
                )
            lines.append("")
    lines.append("## How this was generated")
    lines.append("")
    lines.append("```bash")
    lines.append(f"python -m scripts.parity_matcher_v2_812 --project-id {project_id}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Parity check for category 812 (D1).")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--nm-ids", type=int, nargs="*", default=None)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument(
        "--allow-flip",
        type=int,
        action="append",
        default=[],
        help="Allow primary<->rejected flip for this nm_id (may be repeated).",
    )
    parser.add_argument("--artifact", type=str, default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    allowed_flips = set(int(x) for x in args.allow_flip or [])
    artifact_path = Path(args.artifact)

    session = SessionLocal()
    try:
        if args.nm_ids:
            nm_ids = [int(x) for x in args.nm_ids]
        else:
            nm_ids = _pick_default_nm_ids(
                session, project_id=int(args.project_id), limit=int(args.sample_size)
            )

        rows: list[SkuParityRow] = []
        for nm_id in nm_ids:
            try:
                legacy = _legacy_bucket_map(
                    session, project_id=int(args.project_id), nm_id=nm_id
                )
                candidate = _candidate_bucket_map(
                    session, project_id=int(args.project_id), nm_id=nm_id
                )
            except Exception as exc:  # pragma: no cover - surfaced in artifact
                row = SkuParityRow(
                    nm_id=nm_id,
                    total_queries=0,
                    bucket_changes=0,
                    ratio=0.0,
                    flips=[],
                    breach_reason=f"error: {exc!s}",
                )
                rows.append(row)
                continue
            diff = _diff_for_sku(
                legacy,
                candidate,
                allow_flip=nm_id in allowed_flips,
            )
            diff.nm_id = nm_id
            rows.append(diff)

        breaches = [r for r in rows if r.breach_reason]
        verdict = "PASS" if not breaches else "FAIL"

        md = _render_markdown(
            project_id=int(args.project_id),
            rows=rows,
            allowed_flips=allowed_flips,
            verdict=verdict,
            generated_at=datetime.now(tz=timezone.utc),
        )

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(md, encoding="utf-8")

        print(
            json.dumps(
                {
                    "verdict": verdict,
                    "nm_ids": nm_ids,
                    "breaches": [
                        {"nm_id": r.nm_id, "reason": r.breach_reason}
                        for r in breaches
                    ],
                    "artifact": str(artifact_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
        return 0 if verdict == "PASS" else 2
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
