"""Derive flow for category profiles."""

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
from app.services.seo.category_profile_derive_builder import build_category_profile_draft
from app.services.seo.category_profile_derive_evidence import read_category_profile_derive_evidence
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


def _build_generic_profile_version(*, category_id: int, evidence_hash: str) -> str:
    clean_hash = str(evidence_hash).removeprefix("sha256:")
    return f"v1.{int(category_id)}.generic.{clean_hash[:8]}"


def _write_dry_run_artifacts(
    *,
    snapshot_path: Path,
    payload: Mapping[str, Any],
    source_note: str,
    evidence_input: Mapping[str, Any],
    self_check: CategoryProfileSelfCheckReport,
    diagnostics: Mapping[str, Any],
    profile_diff_vs_812: Mapping[str, Any] | None = None,
) -> None:
    write_category_profile_snapshot(path=snapshot_path, payload=payload, source_note=source_note)
    artifact_dir = snapshot_path.parent
    (artifact_dir / "profile_self_check.json").write_text(
        json.dumps(self_check.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    corpus = evidence_input.get("corpus") if isinstance(evidence_input.get("corpus"), Mapping) else {}
    (artifact_dir / "corpus_health.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    axes = evidence_input.get("axes") if isinstance(evidence_input.get("axes"), Mapping) else {}
    (artifact_dir / "category_axes_snapshot.json").write_text(
        json.dumps(axes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "derive_diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if profile_diff_vs_812 is not None:
        (artifact_dir / "profile_diff_vs_812.json").write_text(
            json.dumps(profile_diff_vs_812, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _build_profile_diff_vs_812(
    session: Session,
    *,
    project_id: int,
    profile_payload: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    if session is None:
        return None
    baseline = session.scalars(
        select(SeoCategoryProfile).where(
            SeoCategoryProfile.project_id == int(project_id),
            SeoCategoryProfile.category_id == 812,
            SeoCategoryProfile.is_active.is_(True),
        )
    ).first()
    if baseline is None:
        return None
    baseline_payload = dict(baseline.payload or {})
    current_subject = profile_payload.get("subject") if isinstance(profile_payload.get("subject"), Mapping) else {}
    baseline_subject = baseline_payload.get("subject") if isinstance(baseline_payload.get("subject"), Mapping) else {}
    return {
        "baseline_category_id": 812,
        "baseline_profile_version": str(baseline.version),
        "current_schema_version": profile_payload.get("schema_version"),
        "baseline_schema_version": baseline_payload.get("schema_version"),
        "subject": {
            "current_primary": current_subject.get("primary"),
            "baseline_primary": baseline_subject.get("primary"),
            "primary_changed": current_subject.get("primary") != baseline_subject.get("primary"),
            "current_aliases_count": len(current_subject.get("primary_aliases", []))
            if isinstance(current_subject.get("primary_aliases"), list)
            else 0,
            "baseline_aliases_count": len(baseline_subject.get("primary_aliases", []))
            if isinstance(baseline_subject.get("primary_aliases"), list)
            else 0,
            "current_related_count": len(current_subject.get("related_but_different", []))
            if isinstance(current_subject.get("related_but_different"), list)
            else 0,
            "baseline_related_count": len(baseline_subject.get("related_but_different", []))
            if isinstance(baseline_subject.get("related_but_different"), list)
            else 0,
        },
        "hard_conflicts": {
            "current_count": len(profile_payload.get("hard_conflicts", []))
            if isinstance(profile_payload.get("hard_conflicts"), list)
            else 0,
            "baseline_count": len(baseline_payload.get("hard_conflicts", []))
            if isinstance(baseline_payload.get("hard_conflicts"), list)
            else 0,
        },
        "scoring_cutoffs_equal": (
            (profile_payload.get("scoring") if isinstance(profile_payload.get("scoring"), Mapping) else {}).get(
                "bucket_cutoffs"
            )
            == (baseline_payload.get("scoring") if isinstance(baseline_payload.get("scoring"), Mapping) else {}).get(
                "bucket_cutoffs"
            )
        ),
    }


def _derive_generic_dry_run(
    *,
    project_id: int,
    category_id: int,
    session: Session,
    out_path: Path | None,
) -> DeriveResult:
    vocabulary = load_global_vocabulary()
    evidence = read_category_profile_derive_evidence(
        session,
        project_id=project_id,
        category_id=category_id,
    )
    evidence_input = evidence.to_builder_input()
    draft = build_category_profile_draft(evidence_input, generated_at=_utcnow())
    profile_payload = copy.deepcopy(dict(draft.profile_payload))
    subject_match_share = _compute_subject_match_share(
        session,
        project_id=project_id,
        category_id=category_id,
        payload=profile_payload,
    )
    generated_by = profile_payload.get("generated_by")
    if isinstance(generated_by, dict):
        corpus_signals = generated_by.setdefault("corpus_signals", {})
        if isinstance(corpus_signals, dict):
            corpus_signals["csv_subject_match_share"] = subject_match_share

    self_check = validate_category_profile_payload(
        profile_payload,
        vocabulary=vocabulary,
        subject_match_share=subject_match_share,
    )
    profile_payload["self_check"] = self_check.model_dump(mode="json")
    profile_version = _build_generic_profile_version(
        category_id=category_id,
        evidence_hash=str(evidence.evidence_hash),
    )
    snapshot_path = resolve_category_profile_snapshot_path(
        project_id=project_id,
        category_id=category_id,
        version=profile_version,
        out_path=out_path,
    )
    source_note = (
        "Phase 1 Step 6 generic dry-run derive. Payload was built from existing corpus and ready "
        "category meaning axes only; no DB profile row was persisted or activated."
    )
    diagnostics = {
        "status": "succeeded",
        "mode": "generic_dry_run",
        "project_id": int(project_id),
        "category_id": int(category_id),
        "profile_version": profile_version,
        "evidence": dict(evidence_input.get("diagnostics") or {}),
        "builder": dict(draft.diagnostics),
        "self_check_status": self_check.status,
        "snapshot_path": str(snapshot_path),
        "persistence": {
            "profile_row_written": False,
            "derive_run_row_written": False,
            "activated": False,
        },
    }
    if out_path is not None:
        _write_dry_run_artifacts(
            snapshot_path=snapshot_path,
            payload=profile_payload,
            source_note=source_note,
            evidence_input=evidence_input,
            self_check=self_check,
            diagnostics=diagnostics,
            profile_diff_vs_812=_build_profile_diff_vs_812(
                session,
                project_id=project_id,
                profile_payload=profile_payload,
            ),
        )
    return DeriveResult(
        run_id=str(uuid4()),
        profile_version=profile_version,
        profile_payload=profile_payload,
        self_check=self_check,
        snapshot_path=snapshot_path,
        source_note=source_note,
        profile_id=None,
        derive_run_db_id=None,
        status="succeeded",
    )


def _persist_generic_profile(
    *,
    project_id: int,
    category_id: int,
    session: Session,
    out_path: Path | None,
) -> DeriveResult:
    vocabulary = load_global_vocabulary()
    evidence = read_category_profile_derive_evidence(
        session,
        project_id=project_id,
        category_id=category_id,
    )
    evidence_input = evidence.to_builder_input()
    draft = build_category_profile_draft(evidence_input, generated_at=_utcnow())
    profile_payload = copy.deepcopy(dict(draft.profile_payload))
    subject_match_share = _compute_subject_match_share(
        session,
        project_id=project_id,
        category_id=category_id,
        payload=profile_payload,
    )
    generated_by = profile_payload.get("generated_by")
    if isinstance(generated_by, dict):
        corpus_signals = generated_by.setdefault("corpus_signals", {})
        if isinstance(corpus_signals, dict):
            corpus_signals["csv_subject_match_share"] = subject_match_share

    self_check = validate_category_profile_payload(
        profile_payload,
        vocabulary=vocabulary,
        subject_match_share=subject_match_share,
    )
    if self_check.status != "passed":
        raise CategoryProfileDeriveError(
            f"Cannot persist category profile because self_check.status={self_check.status!r}"
        )
    profile_payload["self_check"] = self_check.model_dump(mode="json")
    profile_version = _build_generic_profile_version(
        category_id=category_id,
        evidence_hash=str(evidence.evidence_hash),
    )
    snapshot_path = resolve_category_profile_snapshot_path(
        project_id=project_id,
        category_id=category_id,
        version=profile_version,
        out_path=out_path,
    )
    source_note = (
        "Phase 1 Step 7 generic derive persist. Payload was built from existing corpus and ready "
        "category meaning axes only; profile row was saved as inactive candidate and not activated."
    )
    generated_at = _utcnow()
    run_id = str(uuid4())
    derive_run = SeoCategoryProfileDeriveRun(
        project_id=int(project_id),
        category_id=int(category_id),
        run_id=run_id,
        started_at=generated_at,
        status="running",
        method=str(generated_by.get("method")) if isinstance(generated_by, Mapping) else "generic_heuristic_profile_builder_v1",
        llm_model=None,
        prompt_version=None,
        evidence_hash=str(evidence.evidence_hash).removeprefix("sha256:"),
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
                payload=profile_payload,
                source_note=source_note,
            )
            session.add(existing)
        else:
            existing.payload = profile_payload
            existing.source_note = source_note
            existing.is_active = False
        session.flush()

        write_category_profile_snapshot(path=snapshot_path, payload=profile_payload, source_note=source_note)

        derive_run.status = "succeeded"
        derive_run.finished_at = _utcnow()
        derive_run.profile_version = profile_version
        derive_run.profile_id = int(existing.id)
        derive_run.self_check_json = self_check.model_dump(mode="json")
        derive_run.diff_summary = {
            "snapshot_path": str(snapshot_path),
            "mode": "generic_heuristic_profile_builder_v1",
            "evidence": dict(evidence_input.get("diagnostics") or {}),
            "builder": dict(draft.diagnostics),
            "persistence": {
                "profile_row_written": True,
                "derive_run_row_written": True,
                "activated": False,
            },
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
        profile_payload=profile_payload,
        self_check=self_check,
        snapshot_path=snapshot_path,
        source_note=source_note,
        profile_id=int(existing.id),
        derive_run_db_id=int(derive_run.id),
        status="succeeded",
    )


def derive_category_profile(
    *,
    project_id: int,
    category_id: int,
    session: Session,
    activate: bool = False,
    dry_run: bool = False,
    out_path: Path | None = None,
) -> DeriveResult:
    """Build a category profile and optionally persist it inactive."""

    if activate:
        raise NotImplementedError("Activation is intentionally disabled in Phase 0 Step 3")

    if int(category_id) != 812:
        if not dry_run:
            return _persist_generic_profile(
                project_id=project_id,
                category_id=category_id,
                session=session,
                out_path=out_path,
            )
        return _derive_generic_dry_run(
            project_id=project_id,
            category_id=category_id,
            session=session,
            out_path=out_path,
        )

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
