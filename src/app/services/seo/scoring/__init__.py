"""Scoring helpers for SEO foundation."""

from app.services.seo.scoring.actual import (
    QueryActualScoringDiagnostics,
    QueryActualScoringItem,
    QueryActualScoringModifiers,
    QueryActualScoringPenalty,
    QueryActualScoringResult,
    run_query_actual_scoring,
)
from app.services.seo.scoring.config import ScoreWeights, get_default_score_weights
from app.services.seo.scoring.preparation import (
    ClusterScoringPreparation,
    PreparationFlags,
    ProductTypeMatchResult,
    QueryScoringPreparationDiagnostics,
    QueryScoringPreparationError,
    QueryScoringPreparationNotFoundError,
    QueryScoringPreparationResult,
    QueryScoringPreparationScopeError,
    ScoringPreparationMarkerEvaluation,
    SkuEvidenceSummary,
    UseCaseMatchResult,
    AttributeMatchResult,
    run_query_scoring_preparation,
)
from app.services.seo.scoring.service import PersistedScoreResult, ScoreComponents, create_score_run, persist_query_score

__all__ = [
    "AttributeMatchResult",
    "ClusterScoringPreparation",
    "PreparationFlags",
    "PersistedScoreResult",
    "ProductTypeMatchResult",
    "QueryActualScoringDiagnostics",
    "QueryActualScoringItem",
    "QueryActualScoringModifiers",
    "QueryActualScoringPenalty",
    "QueryActualScoringResult",
    "QueryScoringPreparationDiagnostics",
    "QueryScoringPreparationError",
    "QueryScoringPreparationNotFoundError",
    "QueryScoringPreparationResult",
    "QueryScoringPreparationScopeError",
    "ScoringPreparationMarkerEvaluation",
    "ScoreComponents",
    "ScoreWeights",
    "SkuEvidenceSummary",
    "UseCaseMatchResult",
    "create_score_run",
    "get_default_score_weights",
    "persist_query_score",
    "run_query_actual_scoring",
    "run_query_scoring_preparation",
]
