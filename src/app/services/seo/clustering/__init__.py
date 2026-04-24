"""[FROZEN iter-1] Clustering skeletons for SEO foundation.

DEPRECATED as of SEO iteration 1 (see
``docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md``
§4.1 E). Production matching/scoring is owned by
``app.services.seo.matcher_v2``. This package is kept only so that the
clustering ORM rows and legacy scripts keep importing; new production
imports are blocked at load time via ``guard_frozen_module``.
"""

from app.services.seo._freeze import guard_frozen_module

guard_frozen_module(__name__)

from app.services.seo.clustering.service import cluster_skus_placeholder  # noqa: E402

__all__ = ["cluster_skus_placeholder"]
