"""Read-only compare layer (Iteration 2, WS-E compare).

This module is intentionally keyword-pure: it reads persisted rows
(``SeoSkuQuerySet``/``SeoSkuQuerySetItem``, ``SeoMatcherRun``/
``SeoMatcherResult``, ``SeoContentVersion``, ``SeoGenerationRun``) and
produces side-by-side payloads for the operator compare UI.

Contract:

* Must not import any matcher/generation service function that mutates
  matcher trace or content versions. The static check is enforced by
  ``tests/seo/test_seo_compare_read_only.py``.
* Must not compute its own bucket / score decisions — it's a differ, not a
  third decision engine.
* Verdict capture is handled by the compare router via
  :class:`app.models.SeoCompareVerdict`; this module never writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoContentVersion,
    SeoGenerationRun,
    SeoMatcherResult,
    SeoMatcherRun,
    SeoSkuQuerySet,
    SeoSkuQuerySetItem,
)


@dataclass
class MatcherCompareResult:
    current: dict[str, Any]
    candidate: dict[str, Any]
    diff: dict[str, Any]


@dataclass
class GenerationCompareResult:
    by_kind: dict[str, list[dict[str, Any]]]
    latest_preview_id: int | None
    latest_candidate_id: int | None
    latest_approved_id: int | None


def _serialize_query_set_item(row: SeoSkuQuerySetItem) -> dict[str, Any]:
    return {
        "normalized_query_text": str(row.normalized_query_text or ""),
        "display_query": str(row.display_query or ""),
        "bucket": str(row.bucket or ""),
        "score": float(row.score or 0),
        "selection_state": str(row.selection_state or "auto_selected"),
        "cluster_key": row.cluster_key,
        "reasons": list((row.reasons_payload or {}).get("user_reasons") or []),
    }


def _serialize_matcher_result(row: SeoMatcherResult) -> dict[str, Any]:
    return {
        "normalized_query_text": str(row.normalized_query_text or ""),
        "display_query": str(row.query_display or ""),
        "bucket": str(row.bucket or ""),
        "score": float(row.score or 0),
        "eligibility_verdict": str(row.eligibility_verdict or ""),
        "cluster_key": row.cluster_key,
        "reasons": list(row.reasons or []),
        "matched_atoms": list(row.matched_atoms or []),
        "missing_atoms": list(row.missing_atoms or []),
        "conflict_atoms": list(row.conflict_atoms or []),
    }


def _compute_matcher_diff(
    *,
    current: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> dict[str, Any]:
    by_current = {str(row["normalized_query_text"]): row for row in current}
    by_candidate = {str(row["normalized_query_text"]): row for row in candidate}
    keys = sorted(set(by_current) | set(by_candidate))
    per_query: list[dict[str, Any]] = []
    flips: list[dict[str, Any]] = []
    bucket_changes = 0
    only_in_current: list[str] = []
    only_in_candidate: list[str] = []

    for key in keys:
        cur = by_current.get(key)
        cand = by_candidate.get(key)
        if cur is None:
            only_in_candidate.append(key)
            per_query.append(
                {
                    "normalized_query_text": key,
                    "current_bucket": None,
                    "candidate_bucket": cand["bucket"],
                    "status": "only_in_candidate",
                }
            )
            continue
        if cand is None:
            only_in_current.append(key)
            per_query.append(
                {
                    "normalized_query_text": key,
                    "current_bucket": cur["bucket"],
                    "candidate_bucket": None,
                    "status": "only_in_current",
                }
            )
            continue

        cur_bucket = str(cur["bucket"])
        cand_bucket = str(cand["bucket"])
        status = "same"
        if cur_bucket != cand_bucket:
            bucket_changes += 1
            status = "bucket_changed"
            is_primary_reject_flip = {cur_bucket, cand_bucket} == {"primary", "rejected"}
            if is_primary_reject_flip:
                status = "primary_rejected_flip"
                flips.append(
                    {
                        "normalized_query_text": key,
                        "current_bucket": cur_bucket,
                        "candidate_bucket": cand_bucket,
                    }
                )
        per_query.append(
            {
                "normalized_query_text": key,
                "current_bucket": cur_bucket,
                "candidate_bucket": cand_bucket,
                "current_score": cur.get("score"),
                "candidate_score": cand.get("score"),
                "status": status,
            }
        )

    total = len(keys) or 1
    return {
        "per_query_bucket": per_query,
        "bucket_changes": bucket_changes,
        "bucket_change_ratio": round(bucket_changes / total, 4),
        "primary_rejected_flips": flips,
        "only_in_current": only_in_current,
        "only_in_candidate": only_in_candidate,
        "total_queries_compared": total,
    }


def _latest_legacy_query_set(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoSkuQuerySet | None:
    """Return the newest legacy (``draft`` or ``confirmed``) query set."""

    return session.scalars(
        select(SeoSkuQuerySet)
        .where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
            SeoSkuQuerySet.status.in_(("draft", "confirmed")),
        )
        .order_by(
            # Prefer confirmed over draft when both exist.
            desc(SeoSkuQuerySet.status == "confirmed"),
            desc(SeoSkuQuerySet.updated_at),
            desc(SeoSkuQuerySet.id),
        )
    ).first()


def _latest_candidate_matcher_run(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoMatcherRun | None:
    return session.scalars(
        select(SeoMatcherRun)
        .where(
            SeoMatcherRun.project_id == int(project_id),
            SeoMatcherRun.category_id == int(category_id),
            SeoMatcherRun.nm_id == int(nm_id),
        )
        .order_by(desc(SeoMatcherRun.started_at), desc(SeoMatcherRun.id))
    ).first()


def compare_matcher(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> MatcherCompareResult:
    """Compare the legacy persisted query-set against the candidate matcher_v2 run.

    ``current`` is sourced from the latest legacy ``SeoSkuQuerySet`` (status
    ``draft`` or ``confirmed``). ``candidate`` is sourced from the latest
    ``SeoMatcherRun`` trace. Both are read-only.
    """

    legacy_qs = _latest_legacy_query_set(
        session, project_id=project_id, category_id=category_id, nm_id=nm_id
    )
    current_items: list[dict[str, Any]] = []
    current_meta: dict[str, Any] = {}
    if legacy_qs is not None:
        rows = session.scalars(
            select(SeoSkuQuerySetItem).where(
                SeoSkuQuerySetItem.query_set_id == int(legacy_qs.id)
            )
        ).all()
        current_items = [_serialize_query_set_item(r) for r in rows]
        current_meta = {
            "query_set_id": int(legacy_qs.id),
            "status": str(legacy_qs.status),
            "matcher_version": legacy_qs.matcher_version,
            "atoms_version": legacy_qs.atoms_version,
            "quality_mode": getattr(legacy_qs, "quality_mode", None),
            "updated_at": legacy_qs.updated_at.isoformat() if legacy_qs.updated_at else None,
        }

    candidate_run = _latest_candidate_matcher_run(
        session, project_id=project_id, category_id=category_id, nm_id=nm_id
    )
    candidate_items: list[dict[str, Any]] = []
    candidate_meta: dict[str, Any] = {}
    if candidate_run is not None:
        rows = session.scalars(
            select(SeoMatcherResult).where(
                SeoMatcherResult.run_id == int(candidate_run.id)
            )
        ).all()
        candidate_items = [_serialize_matcher_result(r) for r in rows]
        candidate_meta = {
            "matcher_run_id": int(candidate_run.id),
            "matcher_version": str(candidate_run.matcher_version or ""),
            "policy_version": str(candidate_run.policy_version or ""),
            "category_profile_version": str(
                candidate_run.category_profile_version or ""
            ),
            "quality_mode": getattr(candidate_run, "quality_mode", None),
            "started_at": candidate_run.started_at.isoformat() if candidate_run.started_at else None,
        }

    diff = _compute_matcher_diff(current=current_items, candidate=candidate_items)

    return MatcherCompareResult(
        current={"meta": current_meta, "items": current_items},
        candidate={"meta": candidate_meta, "items": candidate_items},
        diff=diff,
    )


def _serialize_content_version(
    session: Session, row: SeoContentVersion
) -> dict[str, Any]:
    latest_run = session.scalars(
        select(SeoGenerationRun)
        .where(SeoGenerationRun.content_version_id == int(row.id))
        .order_by(desc(SeoGenerationRun.updated_at), desc(SeoGenerationRun.id))
    ).first()
    return {
        "id": int(row.id),
        "content_kind": str(row.content_kind or ""),
        "title": row.title,
        "description": row.description,
        "status": str(row.status or ""),
        "category_profile_version": getattr(row, "category_profile_version", None),
        "matcher_run_id": int(row.matcher_run_id) if row.matcher_run_id is not None else None,
        "quality_mode": getattr(row, "quality_mode", None),
        "publishable": bool(getattr(row, "publishable", False)),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "generation_run_id": int(latest_run.id) if latest_run is not None else None,
    }


def compare_generation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit_per_kind: int = 5,
) -> GenerationCompareResult:
    """Group the SKU's content versions by ``content_kind`` for side-by-side UI."""

    rows = session.scalars(
        select(SeoContentVersion)
        .where(
            SeoContentVersion.project_id == int(project_id),
            SeoContentVersion.category_id == int(category_id),
            SeoContentVersion.nm_id == int(nm_id),
        )
        .order_by(desc(SeoContentVersion.updated_at), desc(SeoContentVersion.id))
    ).all()

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        kind = str(row.content_kind or "")
        # Treat legacy llm_draft rows as preview for UI grouping.
        if kind == "llm_draft":
            kind = "preview"
        bucket = by_kind.setdefault(kind, [])
        if len(bucket) < int(limit_per_kind):
            bucket.append(_serialize_content_version(session, row))

    def _latest_id(kind: str) -> int | None:
        lst = by_kind.get(kind) or []
        return int(lst[0]["id"]) if lst else None

    return GenerationCompareResult(
        by_kind=by_kind,
        latest_preview_id=_latest_id("preview"),
        latest_candidate_id=_latest_id("candidate"),
        latest_approved_id=_latest_id("approved"),
    )


__all__ = [
    "GenerationCompareResult",
    "MatcherCompareResult",
    "compare_generation",
    "compare_matcher",
]
