"""Atoms v1 — production namespace for meaning atoms matching.

Relocated from ``services/seo/experiments/meaning_atoms/`` in iteration 1.
The ``matcher_v1`` submodule carries the staged ``match_atoms_v1`` function
that production code consumes; the original experimental ``v1.py`` was
renamed on relocation to disambiguate the module name from the package.

Public API mirrors what production imports today:

- :func:`match_atoms_v1`, :data:`ATOMS_MATCHER_V1_VERSION`,
  :func:`normalize_query_atoms_v1`, :func:`normalize_sku_atoms_v1`
- :class:`MeaningAtom`, :class:`QueryAtoms`, :class:`SkuAtoms`,
  :class:`AtomsMatchResult`
- extractor and vision helpers consumed by
  ``services/seo/meaning_atoms/storage.py``.
"""

from __future__ import annotations

from app.services.seo.atoms.v1.guards import (
    append_atom_unique,
    apply_query_guards,
    apply_sku_guards,
    atom_label,
    atom_matches,
    canonical_value,
    field_family,
    normalize_text,
)
from app.services.seo.atoms.v1.llm_extractors import (
    extract_query_atoms,
    extract_sku_atoms,
    parse_query_atoms_response,
    parse_sku_atoms_response,
)
from app.services.seo.atoms.v1.matcher_v1 import (
    ATOMS_MATCHER_V1_VERSION,
    match_atoms_v1,
    normalize_query_atoms_v1,
    normalize_sku_atoms_v1,
)
from app.services.seo.atoms.v1.schemas import (
    AtomsMatchResult,
    MeaningAtom,
    QueryAtoms,
    SkuAtoms,
)
from app.services.seo.atoms.v1.vision import (
    extract_vision_sku_atoms,
    image_urls_from_evidence,
    merge_sku_atoms_with_vision,
    parse_vision_sku_atoms_response,
)


__all__ = [
    "ATOMS_MATCHER_V1_VERSION",
    "AtomsMatchResult",
    "MeaningAtom",
    "QueryAtoms",
    "SkuAtoms",
    "append_atom_unique",
    "apply_query_guards",
    "apply_sku_guards",
    "atom_label",
    "atom_matches",
    "canonical_value",
    "extract_query_atoms",
    "extract_sku_atoms",
    "extract_vision_sku_atoms",
    "field_family",
    "image_urls_from_evidence",
    "match_atoms_v1",
    "merge_sku_atoms_with_vision",
    "normalize_query_atoms_v1",
    "normalize_sku_atoms_v1",
    "normalize_text",
    "parse_query_atoms_response",
    "parse_sku_atoms_response",
    "parse_vision_sku_atoms_response",
]
