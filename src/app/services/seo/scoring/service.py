"""[FROZEN iter-1] Scoring skeleton with explainability persistence helpers.

DEPRECATED as of SEO iteration 1 (see
``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
§4.1 E). Production scoring moved to ``app.services.seo.matcher_v2``. The
legacy ``create_score_run``/``persist_query_score`` helpers are kept
diagnostic-only: the deterministic preparation/actual scoring scripts
(under ``scoring.preparation`` / ``scoring.actual``) still use them for
audit, but no production router/service is allowed to import them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app import settings
from app.models import SeoQueryScore, SeoScoreExplanation, SeoScoreRun
from app.services.seo._freeze import guard_frozen_module
from app.services.seo.scoring.config import ScoreWeights, get_default_score_weights

guard_frozen_module(
    __name__,
    # Diagnostic scorers still call into this module. They are not on the
    # production path; see P1 scoring move.
    allowed_caller_prefixes=(
        "app.services.seo.scoring.preparation",
        "app.services.seo.scoring.actual",
    ),
)


PENALTY_COMPONENTS = {"product_type_mismatch", "attribute_mismatch", "cluster_mismatch", "competition_penalty"}


@dataclass(frozen=True)
class ScoreComponents:
    """Score components persisted for explainability."""

    semantic_similarity: float = 0.0
    product_type_match: float = 0.0
    attribute_match: float = 0.0
    use_case_match: float = 0.0
    behavior_score: float = 0.0
    frequency_score: float = 0.0
    product_type_mismatch: float = 0.0
    attribute_mismatch: float = 0.0
    cluster_mismatch: float = 0.0
    competition_penalty: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class PersistedScoreResult:
    """Persisted score ids and computed total."""

    score_run_id: int
    query_score_id: int
    total_score: float
    contributions: dict[str, float]


def _to_decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value))


def _calculate_contributions(components: ScoreComponents, weights: ScoreWeights) -> tuple[Decimal, dict[str, Decimal]]:
    contributions: dict[str, Decimal] = {}
    total = Decimal("0")
    for component_name, raw_value in components.to_dict().items():
        contribution = _to_decimal(raw_value) * _to_decimal(weights.to_dict()[component_name])
        if component_name in PENALTY_COMPONENTS:
            contribution *= Decimal("-1")
        contributions[component_name] = contribution
        total += contribution
    return total, contributions


def create_score_run(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    config: Mapping[str, Any] | None = None,
    status: str = "placeholder",
    scoring_weights_version: str | None = None,
) -> SeoScoreRun:
    """Create a Phase 1 score run shell."""

    score_run = SeoScoreRun(
        project_id=project_id,
        category_id=category_id,
        config=dict(config or {}),
        status=status,
        scoring_weights_version=scoring_weights_version or settings.SEO_SCORING_WEIGHTS_VERSION,
    )
    session.add(score_run)
    session.flush()
    return score_run


def persist_query_score(
    session: Session,
    *,
    score_run: SeoScoreRun,
    components: ScoreComponents | None = None,
    weights: ScoreWeights | None = None,
    normalized_query_id: int | None = None,
    nm_id: int | None = None,
    cluster_id: int | None = None,
    decision: str = "candidate",
    details_by_component: Mapping[str, Mapping[str, Any]] | None = None,
) -> PersistedScoreResult:
    """Persist a score row plus explainability breakdown."""

    resolved_components = components or ScoreComponents()
    resolved_weights = weights or get_default_score_weights()
    total_score, contributions = _calculate_contributions(resolved_components, resolved_weights)
    details = details_by_component or {}

    query_score = SeoQueryScore(
        score_run_id=score_run.id,
        project_id=score_run.project_id,
        category_id=score_run.category_id,
        normalized_query_id=normalized_query_id,
        nm_id=nm_id,
        cluster_id=cluster_id,
        total_score=total_score,
        decision=decision,
        component_values=resolved_components.to_dict(),
    )
    session.add(query_score)
    session.flush()

    for component_name, component_value in resolved_components.to_dict().items():
        session.add(
            SeoScoreExplanation(
                query_score_id=query_score.id,
                component_name=component_name,
                component_value=_to_decimal(component_value),
                weight=_to_decimal(resolved_weights.to_dict()[component_name]),
                contribution=contributions[component_name],
                details=dict(details.get(component_name, {})),
            )
        )

    session.flush()
    return PersistedScoreResult(
        score_run_id=int(score_run.id),
        query_score_id=int(query_score.id),
        total_score=float(total_score),
        contributions={key: float(value) for key, value in contributions.items()},
    )
