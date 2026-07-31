"""Schemas for the LLM meaning atoms shadow experiment."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MEANING_ATOMS_SCHEMA_VERSION = "meaning_atoms_v0"
MEANING_ATOMS_PROMPT_VERSION = "meaning_atoms_shadow_v0"
ATOMS_MATCHER_VERSION = "atoms_matcher_shadow_v0"

AtomType = Literal[
    "product_type",
    "attribute",
    "numeric",
    "visual",
    "recipient",
    "occasion",
    "use_case",
    "compatibility",
    "expressive",
    "exclusion",
]
AtomImportance = Literal["hard", "soft"]
AtomOperator = Literal["equals", "close_to", "contains", "excludes", "compatible_with"]
MatcherBucket = Literal["primary", "secondary", "broad", "rejected"]


class MeaningAtom(BaseModel):
    type: AtomType
    field: str
    value: Any
    operator: AtomOperator = "equals"
    importance: AtomImportance = "soft"
    source: str = "llm"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class QueryAtoms(BaseModel):
    schema_version: str = MEANING_ATOMS_SCHEMA_VERSION
    cluster_key: str | None = None
    query: str | None = None
    source_query_examples: list[str] = Field(default_factory=list)
    product_type: str = ""
    buyer_intent: str = ""
    required_atoms: list[MeaningAtom] = Field(default_factory=list)
    preferred_atoms: list[MeaningAtom] = Field(default_factory=list)
    excluded_atoms: list[MeaningAtom] = Field(default_factory=list)
    negative_fit_atoms: list[MeaningAtom] = Field(default_factory=list)
    genericness: str = "specific"
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class SkuAtoms(BaseModel):
    schema_version: str = MEANING_ATOMS_SCHEMA_VERSION
    project_id: int | None = None
    category_id: int | None = None
    nm_id: int | None = None
    product_type: str = ""
    product_identity: str = ""
    facts: list[MeaningAtom] = Field(default_factory=list)
    positive_atoms: list[MeaningAtom] = Field(default_factory=list)
    negative_fit_atoms: list[MeaningAtom] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)


class QueryAtomsRecord(BaseModel):
    query: str
    cluster_key: str
    cluster_id: int | None = None
    query_meaning_id: int | None = None
    ranking_value_used: float | None = None
    current_genericness: str | None = None
    atoms: QueryAtoms


class AtomsMatchResult(BaseModel):
    query: str
    cluster_key: str | None = None
    bucket: MatcherBucket
    score: float
    ranking_value_used: float | None = None
    matched_atoms: list[str] = Field(default_factory=list)
    missing_atoms: list[str] = Field(default_factory=list)
    conflict_atoms: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    score_components: dict[str, float] = Field(default_factory=dict)


class ComparisonRow(BaseModel):
    nm_id: int
    query: str
    cluster_key: str | None = None
    ranking_value_used: float | None = None
    current_bucket: str | None = None
    current_score: float | None = None
    atoms_bucket: str | None = None
    atoms_score: float | None = None
    expected_bucket: str | None = None
    diff_type: str
    current_reasons: list[str] = Field(default_factory=list)
    atoms_reasons: list[str] = Field(default_factory=list)
    matched_atoms: list[str] = Field(default_factory=list)
    missing_atoms: list[str] = Field(default_factory=list)
    conflict_atoms: list[str] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    project_id: int
    category_id: int
    nm_ids: list[int]
    matcher_version: str = ATOMS_MATCHER_VERSION
    rows: list[ComparisonRow] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    output_dir: str | None = None

