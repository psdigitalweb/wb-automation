"""Runtime loader and typed wrapper for active category profiles."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import SeoCategoryProfile


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else MappingProxyType({})


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if isinstance(item, str))


def _string_mapping(value: Any) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    return MappingProxyType({str(key): str(item) for key, item in value.items() if isinstance(key, str) and isinstance(item, str)})


def _float_mapping(value: Any) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    result: dict[str, float] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, (int, float)):
            result[str(key)] = float(item)
    return MappingProxyType(result)


def _int_mapping(value: Any) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        return MappingProxyType({})
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, (int, float)):
            result[str(key)] = int(item)
    return MappingProxyType(result)


class CategoryProfileError(Exception):
    """Base error for category profile lookup/parsing."""


class ProfileMissingError(CategoryProfileError):
    """Raised by future runtime paths that require an active category profile."""


@dataclass(frozen=True)
class SubjectDetectionHints:
    token_prefixes: tuple[str, ...]
    negative_token_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class RelatedSubject:
    subject: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class SubjectProfile:
    primary: str
    primary_aliases: tuple[str, ...]
    related_but_different: tuple[RelatedSubject, ...]
    detection_hints: SubjectDetectionHints


@dataclass(frozen=True)
class ProductTypeAliasRule:
    match_any_prefix: tuple[str, ...]
    score_bonus: float | None = None


@dataclass(frozen=True)
class HardConflictRule:
    name: str
    when_query_has: Mapping[str, Any]
    requires_sku_any: tuple[Mapping[str, Any], ...]
    message: str | None = None


@dataclass(frozen=True)
class ScoringProfile:
    weights: Mapping[str, float]
    bucket_cutoffs: Mapping[str, float]
    bucket_caps: Mapping[str, int]
    materials_relevant: tuple[str, ...]


@dataclass(frozen=True)
class CategoryProfile:
    """Frozen runtime view of one active category profile row."""

    profile_id: int
    project_id: int
    category_id: int
    version: str
    payload: Mapping[str, Any]
    source_note: str | None = None

    def __post_init__(self) -> None:
        frozen_payload = _freeze_json(dict(self.payload or {}))
        schema_version = frozen_payload.get("schema_version") if isinstance(frozen_payload, Mapping) else None
        if schema_version != "category_profile_v1":
            raise CategoryProfileError(f"Unsupported category profile schema_version: {schema_version!r}")
        object.__setattr__(self, "payload", frozen_payload)

    @classmethod
    def from_payload(
        cls,
        *,
        profile_id: int,
        project_id: int,
        category_id: int,
        version: str,
        payload: Mapping[str, Any],
        source_note: str | None = None,
    ) -> "CategoryProfile":
        """Construct a typed profile wrapper from a raw JSON payload."""

        return cls(
            profile_id=int(profile_id),
            project_id=int(project_id),
            category_id=int(category_id),
            version=str(version),
            payload=dict(payload or {}),
            source_note=source_note,
        )

    @property
    def schema_version(self) -> str:
        return str(self.payload["schema_version"])

    @property
    def subject(self) -> SubjectProfile:
        raw = _mapping(self.payload.get("subject"))
        related = tuple(
            RelatedSubject(
                subject=str(item.get("subject") or ""),
                aliases=_string_tuple(item.get("aliases")),
            )
            for item in _sequence(raw.get("related_but_different"))
            if isinstance(item, Mapping)
        )
        detection_hints = _mapping(raw.get("detection_hints"))
        return SubjectProfile(
            primary=str(raw.get("primary") or ""),
            primary_aliases=_string_tuple(raw.get("primary_aliases")),
            related_but_different=related,
            detection_hints=SubjectDetectionHints(
                token_prefixes=_string_tuple(detection_hints.get("token_prefixes")),
                negative_token_prefixes=_string_tuple(detection_hints.get("negative_token_prefixes")),
            ),
        )

    @property
    def subject_primary(self) -> str:
        return self.subject.primary

    @property
    def subject_primary_aliases(self) -> tuple[str, ...]:
        return self.subject.primary_aliases

    @property
    def subject_related(self) -> tuple[RelatedSubject, ...]:
        return self.subject.related_but_different

    @property
    def product_type_aliases(self) -> Mapping[str, ProductTypeAliasRule]:
        raw = _mapping(self.payload.get("product_type_aliases"))
        result: dict[str, ProductTypeAliasRule] = {}
        for canonical, item in raw.items():
            if not isinstance(canonical, str) or not isinstance(item, Mapping):
                continue
            score_bonus = item.get("score_bonus")
            result[canonical] = ProductTypeAliasRule(
                match_any_prefix=_string_tuple(item.get("match_any_prefix")),
                score_bonus=float(score_bonus) if isinstance(score_bonus, (int, float)) else None,
            )
        return MappingProxyType(result)

    @property
    def constraints(self) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        raw = _mapping(self.payload.get("constraints"))
        result: dict[str, tuple[Mapping[str, Any], ...]] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                continue
            result[key] = tuple(_mapping(item) for item in _sequence(value) if isinstance(item, Mapping))
        return MappingProxyType(result)

    @property
    def hard_conflicts(self) -> tuple[HardConflictRule, ...]:
        return tuple(
            HardConflictRule(
                name=str(item.get("name") or ""),
                when_query_has=_mapping(item.get("when_query_has")),
                requires_sku_any=tuple(_mapping(rule) for rule in _sequence(item.get("requires_sku_any")) if isinstance(rule, Mapping)),
                message=str(item.get("message")) if isinstance(item.get("message"), str) else None,
            )
            for item in _sequence(self.payload.get("hard_conflicts"))
            if isinstance(item, Mapping)
        )

    @property
    def hard_conflicts_list(self) -> tuple[HardConflictRule, ...]:
        return self.hard_conflicts

    @property
    def conflict_rules(self) -> Mapping[str, Mapping[str, Any]]:
        legacy = _mapping(self.payload.get("conflict_rules"))
        if legacy:
            return legacy
        return MappingProxyType(
            {
                rule.name: MappingProxyType(
                    {
                        "when_query_has": rule.when_query_has,
                        "requires_sku_any": rule.requires_sku_any,
                        "message": rule.message,
                    }
                )
                for rule in self.hard_conflicts
                if rule.name
            }
        )

    @property
    def scoring(self) -> ScoringProfile:
        raw = _mapping(self.payload.get("scoring"))
        return ScoringProfile(
            weights=_float_mapping(raw.get("weights")),
            bucket_cutoffs=_float_mapping(raw.get("bucket_cutoffs")),
            bucket_caps=_int_mapping(raw.get("bucket_caps")),
            materials_relevant=_string_tuple(raw.get("materials_relevant")),
        )

    @property
    def scoring_weights(self) -> Mapping[str, float]:
        return self.scoring.weights

    @property
    def bucket_cutoffs(self) -> Mapping[str, float]:
        return self.scoring.bucket_cutoffs

    @property
    def bucket_cutoffs_map(self) -> Mapping[str, float]:
        return self.scoring.bucket_cutoffs

    @property
    def user_bucket_labels(self) -> Mapping[str, str]:
        return _string_mapping(self.payload.get("user_bucket_labels"))

    @property
    def sku_guards(self) -> Mapping[str, Any]:
        return _mapping(self.payload.get("sku_guards"))

    @property
    def query_guards(self) -> Mapping[str, Any]:
        return _mapping(self.payload.get("query_guards"))

    @property
    def generated_by(self) -> Mapping[str, Any]:
        return _mapping(self.payload.get("generated_by"))

    @property
    def self_check(self) -> Mapping[str, Any]:
        return _mapping(self.payload.get("self_check"))

    @property
    def term_groups(self) -> Mapping[str, Mapping[str, Any]]:
        groups = self.payload.get("term_groups")
        return _mapping(groups)


def load_active_profile(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> CategoryProfile | None:
    """Return the active v1 profile for ``(project_id, category_id)`` if present."""

    row = session.scalars(
        select(SeoCategoryProfile)
        .where(
            SeoCategoryProfile.project_id == int(project_id),
            SeoCategoryProfile.category_id == int(category_id),
            SeoCategoryProfile.is_active.is_(True),
        )
        .order_by(desc(SeoCategoryProfile.updated_at), desc(SeoCategoryProfile.id))
    ).first()
    if row is None:
        return None
    try:
        return CategoryProfile.from_payload(
            profile_id=int(row.id),
            project_id=int(row.project_id),
            category_id=int(row.category_id),
            version=str(row.version),
            payload=dict(row.payload or {}),
            source_note=row.source_note,
        )
    except CategoryProfileError:
        # Step 4 stays pass-through: unknown/legacy payloads keep the runtime on
        # the existing fallback path until Step 8 activates a v1 profile.
        return None


def get_active_profile_version(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    fallback: str = "default_iter1",
) -> str:
    """Return the active profile version if a valid v1 profile exists, else fallback."""

    profile = load_active_profile(session, project_id=project_id, category_id=category_id)
    if profile is None:
        return fallback
    return profile.version


__all__ = [
    "CategoryProfile",
    "CategoryProfileError",
    "HardConflictRule",
    "ProductTypeAliasRule",
    "ProfileMissingError",
    "RelatedSubject",
    "ScoringProfile",
    "SubjectDetectionHints",
    "SubjectProfile",
    "get_active_profile_version",
    "load_active_profile",
]
