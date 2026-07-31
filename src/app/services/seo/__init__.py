"""SEO foundation services package.

Iteration 1 dead-schema freeze (see
``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
§4.1 E) blocks new production imports of ``clustering/*`` and
``scoring.service``. Those legacy helpers are NO LONGER re-exported from
this package root — callers that need them must import them directly from
their frozen submodule, where :func:`app.services.seo._freeze.guard_frozen_module`
can see the real caller. The attribute accessor below keeps existing
diagnostic / test code working by lazily forwarding; any attempt reads
that eventually flow through the per-module guard.
"""

from typing import Any

from app.services.seo.query_pipeline.diagnostics import (
    ImportDiagnostics,
    QueryClusteringDiagnostics,
    QueryPruningDiagnostics,
    UnifiedQueryDatasetDiagnostics,
)
from app.services.seo.query_pipeline.clustering import (
    PersistedQueryClusterView,
    QueryClusteringResult,
    get_query_clusters,
    run_query_clustering,
)
from app.services.seo.query_pipeline.hybrid import get_persisted_hybrid_projection
from app.services.seo.query_pipeline.ingestion import CsvImportError, import_queries_from_csv
from app.services.seo.query_pipeline.normalization import normalize_query_text
from app.services.seo.query_pipeline.profiles import QueryProfileExtractionResult, run_query_profile_extraction
from app.services.seo.query_pipeline.pruning import (
    AnnotatedCanonicalQueryRow,
    QueryPruningResult,
    get_clean_query_set,
    get_pruning_slice,
    run_query_pruning_and_basic_annotation,
)
from app.services.seo.query_pipeline.unified_dataset import UnifiedQueryDatasetResult, assemble_unified_query_dataset
from app.services.seo.scoring.config import ScoreWeights, get_default_score_weights

# Lazy forwarders for frozen legacy helpers. Importing these names triggers
# the per-module guard in the frozen submodule, so production callers are
# rejected at the point of first use (not at package import).
_FROZEN_FORWARDS = {
    "cluster_skus_placeholder": ("app.services.seo.clustering.service", "cluster_skus_placeholder"),
    "create_score_run": ("app.services.seo.scoring.service", "create_score_run"),
    "persist_query_score": ("app.services.seo.scoring.service", "persist_query_score"),
    "PersistedScoreResult": ("app.services.seo.scoring.service", "PersistedScoreResult"),
    "ScoreComponents": ("app.services.seo.scoring.service", "ScoreComponents"),
    # Diagnostic scoring modules that internally import the frozen service.
    "QueryActualScoringDiagnostics": ("app.services.seo.scoring.actual", "QueryActualScoringDiagnostics"),
    "QueryActualScoringItem": ("app.services.seo.scoring.actual", "QueryActualScoringItem"),
    "QueryActualScoringModifiers": ("app.services.seo.scoring.actual", "QueryActualScoringModifiers"),
    "QueryActualScoringPenalty": ("app.services.seo.scoring.actual", "QueryActualScoringPenalty"),
    "QueryActualScoringResult": ("app.services.seo.scoring.actual", "QueryActualScoringResult"),
    "run_query_actual_scoring": ("app.services.seo.scoring.actual", "run_query_actual_scoring"),
    "AttributeMatchResult": ("app.services.seo.scoring.preparation", "AttributeMatchResult"),
    "ClusterScoringPreparation": ("app.services.seo.scoring.preparation", "ClusterScoringPreparation"),
    "PreparationFlags": ("app.services.seo.scoring.preparation", "PreparationFlags"),
    "ProductTypeMatchResult": ("app.services.seo.scoring.preparation", "ProductTypeMatchResult"),
    "QueryScoringPreparationDiagnostics": ("app.services.seo.scoring.preparation", "QueryScoringPreparationDiagnostics"),
    "QueryScoringPreparationResult": ("app.services.seo.scoring.preparation", "QueryScoringPreparationResult"),
    "ScoringPreparationMarkerEvaluation": ("app.services.seo.scoring.preparation", "ScoringPreparationMarkerEvaluation"),
    "SkuEvidenceSummary": ("app.services.seo.scoring.preparation", "SkuEvidenceSummary"),
    "UseCaseMatchResult": ("app.services.seo.scoring.preparation", "UseCaseMatchResult"),
    "run_query_scoring_preparation": ("app.services.seo.scoring.preparation", "run_query_scoring_preparation"),
}


def __getattr__(name: str) -> Any:
    entry = _FROZEN_FORWARDS.get(name)
    if entry is None:
        raise AttributeError(f"module 'app.services.seo' has no attribute {name!r}")
    module_path, attr_name = entry
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


__all__ = [
    "AnnotatedCanonicalQueryRow",
    "AttributeMatchResult",
    "ClusterScoringPreparation",
    "CsvImportError",
    "ImportDiagnostics",
    "PreparationFlags",
    "PersistedQueryClusterView",
    "PersistedScoreResult",
    "ProductTypeMatchResult",
    "QueryActualScoringDiagnostics",
    "QueryActualScoringItem",
    "QueryActualScoringModifiers",
    "QueryActualScoringPenalty",
    "QueryActualScoringResult",
    "QueryClusteringDiagnostics",
    "QueryClusteringResult",
    "QueryProfileExtractionResult",
    "QueryPruningDiagnostics",
    "QueryPruningResult",
    "QueryScoringPreparationDiagnostics",
    "QueryScoringPreparationResult",
    "ScoringPreparationMarkerEvaluation",
    "ScoreComponents",
    "ScoreWeights",
    "SkuEvidenceSummary",
    "UnifiedQueryDatasetDiagnostics",
    "UnifiedQueryDatasetResult",
    "UseCaseMatchResult",
    "assemble_unified_query_dataset",
    "cluster_skus_placeholder",
    "create_score_run",
    "get_query_clusters",
    "get_clean_query_set",
    "get_default_score_weights",
    "get_persisted_hybrid_projection",
    "get_pruning_slice",
    "import_queries_from_csv",
    "normalize_query_text",
    "persist_query_score",
    "run_query_actual_scoring",
    "run_query_clustering",
    "run_query_profile_extraction",
    "run_query_pruning_and_basic_annotation",
    "run_query_scoring_preparation",
]
