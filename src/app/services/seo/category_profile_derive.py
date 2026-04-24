"""Skeleton derive flow for category profiles (Phase 0 Step 3)."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMeaningAxes,
    SeoCategoryProfile,
    SeoCategoryProfileDeriveRun,
    SeoQueryNormalized,
)
from app.schemas.seo_category_profile import CategoryProfileSelfCheckReport
from app.services.seo.category_profile_snapshot import (
    resolve_category_profile_snapshot_path,
    write_category_profile_snapshot,
)
from app.services.seo.category_profile_validator import validate_category_profile_payload
from app.services.seo.global_vocabulary import load_global_vocabulary


_SKELETON_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "config" / "seo" / "category_profiles" / "templates"


class CategoryProfileDeriveError(Exception):
    """Raised when the category-profile derive foundation cannot run."""


@dataclass(frozen=True)
class DeriveResult:
    """Outcome of one derive attempt."""

    run_id: str
    profile_version: str
    profile_payload: Mapping[str, Any]
    self_check: CategoryProfileSelfCheckReport
    snapshot_path: Path
    source_note: str
    profile_id: int | None = None
    derive_run_db_id: int | None = None
    status: str = "succeeded"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(value: Any) -> str:
    return str(value or "").lower().replace("ё", "е")


def _load_skeleton_template(category_id: int) -> dict[str, Any]:
    template_path = _SKELETON_TEMPLATE_DIR / f"{int(category_id)}_skeleton_v1.json"
    if not template_path.exists():
        raise NotImplementedError("skeleton only supports 812")
    return json.loads(template_path.read_text(encoding="utf-8"))


def _latest_ready_axes(session: Session, *, project_id: int, category_id: int) -> SeoCategoryMeaningAxes | None:
    return session.scalars(
        select(SeoCategoryMeaningAxes)
        .where(
            SeoCategoryMeaningAxes.project_id == int(project_id),
            SeoCategoryMeaningAxes.category_id == int(category_id),
            SeoCategoryMeaningAxes.status == "ready",
        )
        .order_by(desc(SeoCategoryMeaningAxes.updated_at), desc(SeoCategoryMeaningAxes.id))
    ).first()


def _count_queries_for_category(session: Session, *, project_id: int, category_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SeoQueryNormalized)
            .where(
                SeoQueryNormalized.project_id == int(project_id),
                SeoQueryNormalized.category_id == int(category_id),
            )
        )
        or 0
    )


def _compute_subject_match_share(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    payload: Mapping[str, Any],
) -> float | None:
    subject = payload.get("subject") if isinstance(payload.get("subject"), Mapping) else {}
    primary_aliases = [str(item) for item in subject.get("primary_aliases", []) if isinstance(item, str)]
    related = [
        str(alias)
        for item in subject.get("related_but_different", [])
        if isinstance(item, Mapping)
        for alias in item.get("aliases", [])
        if isinstance(alias, str)
    ]
    token_prefixes = [
        str(item)
        for item in (subject.get("detection_hints") if isinstance(subject.get("detection_hints"), Mapping) else {}).get(
            "token_prefixes",
            [],
        )
        if isinstance(item, str)
    ]
    probes = [_normalize_text(item) for item in [*primary_aliases, *related, *token_prefixes] if str(item).strip()]
    if not probes:
        return None

    rows = session.execute(
        select(SeoQueryNormalized.normalized_query, SeoQueryNormalized.display_query).where(
            SeoQueryNormalized.project_id == int(project_id),
            SeoQueryNormalized.category_id == int(category_id),
        )
    ).all()
    if not rows:
        return None

    matched = 0
    total = 0
    for normalized_query, display_query in rows:
        total += 1
        haystack = _normalize_text(normalized_query or display_query)
        if any(probe and probe in haystack for probe in probes):
            matched += 1
    if total == 0:
        return None
    return matched / total


def _build_evidence_hash(
    *,
    category_id: int,
    axes: SeoCategoryMeaningAxes | None,
    query_count: int,
    vocabulary_schema_version: str,
) -> str:
    blob = {
        "category_id": int(category_id),
        "axes_evidence_hash": getattr(axes, "evidence_hash", None),
        "axes_payload": dict(getattr(axes, "axes_payload", {}) or {}),
        "query_count": int(query_count),
        "vocabulary_schema_version": vocabulary_schema_version,
        "method": "skeleton_v0",
    }
    return hashlib.sha256(
        json.dumps(blob, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_profile_version(*, category_id: int, evidence_hash: str) -> str:
    return f"v1.{int(category_id)}.skeleton.{evidence_hash[:8]}"


def derive_category_profile(
    *,
    project_id: int,
    category_id: int,
    session: Session,
    activate: bool = False,
    dry_run: bool = False,
    out_path: Path | None = None,
) -> DeriveResult:
    """Build a skeleton category profile and optionally persist it inactive."""

    if activate:
        raise NotImplementedError("Activation is intentionally disabled in Phase 0 Step 3")

    if int(category_id) != 812:
        raise NotImplementedError("skeleton only supports 812")

    vocabulary = load_global_vocabulary()
    skeleton_payload = copy.deepcopy(_load_skeleton_template(category_id))
    axes = _latest_ready_axes(session, project_id=project_id, category_id=category_id)
    query_count = _count_queries_for_category(session, project_id=project_id, category_id=category_id)
    evidence_hash = _build_evidence_hash(
        category_id=category_id,
        axes=axes,
        query_count=query_count,
        vocabulary_schema_version=vocabulary.schema_version,
    )
    profile_version = _build_profile_version(category_id=category_id, evidence_hash=evidence_hash)
    subject_match_share = _compute_subject_match_share(
        session,
        project_id=project_id,
        category_id=category_id,
        payload=skeleton_payload,
    )
    generated_at = _utcnow()
    generated_by = {
        "method": "skeleton_v0",
        "llm_model": None,
        "prompt_version": None,
        "evidence_hash": f"sha256:{evidence_hash}",
        "generated_at": _isoformat(generated_at),
        "corpus_signals": {
            "queries_sampled": query_count,
            "product_type_axes_count": len(
                (dict(getattr(axes, "axes_payload", {}) or {})).get("product_type_axes", []) if axes is not None else []
            ),
            "csv_subject_match_share": subject_match_share,
        },
    }
    skeleton_payload["generated_by"] = generated_by
    self_check = validate_category_profile_payload(
        skeleton_payload,
        vocabulary=vocabulary,
        subject_match_share=subject_match_share,
    )
    skeleton_payload["self_check"] = self_check.model_dump(mode="json")
    snapshot_path = resolve_category_profile_snapshot_path(
        project_id=project_id,
        category_id=category_id,
        version=profile_version,
        out_path=out_path,
    )
    source_note = (
        "Phase 0 Step 3 skeleton derive. Payload comes from the committed 812 template, "
        "while generated_by/self_check are refreshed from current category evidence."
    )
    run_id = str(uuid4())

    if dry_run:
        return DeriveResult(
            run_id=run_id,
            profile_version=profile_version,
            profile_payload=skeleton_payload,
            self_check=self_check,
            snapshot_path=snapshot_path,
            source_note=source_note,
            profile_id=None,
            derive_run_db_id=None,
            status="succeeded",
        )

    derive_run = SeoCategoryProfileDeriveRun(
        project_id=int(project_id),
        category_id=int(category_id),
        run_id=run_id,
        started_at=generated_at,
        status="running",
        method="skeleton_v0",
        llm_model=None,
        prompt_version=None,
        evidence_hash=evidence_hash,
        self_check_json={},
    )
    session.add(derive_run)
    session.flush()

    try:
        existing = session.scalars(
            select(SeoCategoryProfile).where(
                SeoCategoryProfile.project_id == int(project_id),
                SeoCategoryProfile.category_id == int(category_id),
                SeoCategoryProfile.version == profile_version,
            )
        ).first()

        if existing is None:
            existing = SeoCategoryProfile(
                project_id=int(project_id),
                category_id=int(category_id),
                version=profile_version,
                is_active=False,
                payload=skeleton_payload,
                source_note=source_note,
            )
            session.add(existing)
        else:
            existing.payload = skeleton_payload
            existing.source_note = source_note
            existing.is_active = False
        session.flush()

        write_category_profile_snapshot(path=snapshot_path, payload=skeleton_payload, source_note=source_note)

        derive_run.status = "succeeded"
        derive_run.finished_at = _utcnow()
        derive_run.profile_version = profile_version
        derive_run.profile_id = int(existing.id)
        derive_run.self_check_json = self_check.model_dump(mode="json")
        derive_run.diff_summary = {
            "snapshot_path": str(snapshot_path),
            "query_count": query_count,
            "axes_source": getattr(axes, "source", None),
            "mode": "skeleton_v0",
        }
        session.flush()
    except Exception as exc:
        derive_run.status = "failed"
        derive_run.finished_at = _utcnow()
        derive_run.error_message = str(exc)
        session.flush()
        raise

    return DeriveResult(
        run_id=run_id,
        profile_version=profile_version,
        profile_payload=skeleton_payload,
        self_check=self_check,
        snapshot_path=snapshot_path,
        source_note=source_note,
        profile_id=int(existing.id),
        derive_run_db_id=int(derive_run.id),
        status="succeeded",
    )
