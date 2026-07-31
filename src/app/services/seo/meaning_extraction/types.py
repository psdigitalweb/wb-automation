"""Canonical meaning objects for Meaning Extraction MVP.

Constraints:
- Deterministic, explainability-friendly shapes
- JSON-serializable via `to_dict()`
- No embeddings/LLM dependencies
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal


MeaningLayerVersion = Literal["v1_mvp"]


def _serialize_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


@dataclass(frozen=True)
class CategoryFunctionalMeaning:
    product_types: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)

    def normalized(self) -> CategoryFunctionalMeaning:
        return CategoryFunctionalMeaning(
            product_types=_dedupe_ordered(self.product_types),
            use_cases=_dedupe_ordered(self.use_cases),
            attributes=_dedupe_ordered(self.attributes),
        )


@dataclass(frozen=True)
class CategoryExpressiveMeaning:
    vibes: list[str] = field(default_factory=list)
    llm: dict[str, Any] | None = None

    def normalized(self) -> CategoryExpressiveMeaning:
        return CategoryExpressiveMeaning(vibes=_dedupe_ordered(self.vibes), llm=self.llm)


@dataclass(frozen=True)
class CategoryMeaning:
    """Product-side semantic space (per project × category)."""

    project_id: int
    category_id: int
    version: MeaningLayerVersion = "v1_mvp"
    functional: CategoryFunctionalMeaning = field(default_factory=CategoryFunctionalMeaning)
    expressive: CategoryExpressiveMeaning = field(default_factory=CategoryExpressiveMeaning)

    def normalized(self) -> CategoryMeaning:
        return CategoryMeaning(
            project_id=int(self.project_id),
            category_id=int(self.category_id),
            version=self.version,
            functional=self.functional.normalized(),
            expressive=self.expressive.normalized(),
        )

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self.normalized())


@dataclass(frozen=True)
class ProductFunctionalProfile:
    product_type: str | None = None
    use_cases: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)

    def normalized(self) -> ProductFunctionalProfile:
        return ProductFunctionalProfile(
            product_type=str(self.product_type).strip() if self.product_type else None,
            use_cases=_dedupe_ordered(self.use_cases),
            attributes=_dedupe_ordered(self.attributes),
        )


@dataclass(frozen=True)
class ProductExpressiveProfile:
    vibes: list[str] = field(default_factory=list)

    def normalized(self) -> ProductExpressiveProfile:
        return ProductExpressiveProfile(vibes=_dedupe_ordered(self.vibes))


@dataclass(frozen=True)
class ProductProjection:
    """SKU-level meaning projection into category space (per project × SKU)."""

    project_id: int
    category_id: int
    nm_id: int
    version: MeaningLayerVersion = "v1_mvp"
    functional: ProductFunctionalProfile = field(default_factory=ProductFunctionalProfile)
    expressive: ProductExpressiveProfile = field(default_factory=ProductExpressiveProfile)

    def normalized(self) -> ProductProjection:
        return ProductProjection(
            project_id=int(self.project_id),
            category_id=int(self.category_id),
            nm_id=int(self.nm_id),
            version=self.version,
            functional=self.functional.normalized(),
            expressive=self.expressive.normalized(),
        )

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self.normalized())


@dataclass(frozen=True)
class QueryFunctionalIntent:
    product_type: str | None = None
    use_cases: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)

    def normalized(self) -> QueryFunctionalIntent:
        return QueryFunctionalIntent(
            product_type=str(self.product_type).strip() if self.product_type else None,
            use_cases=_dedupe_ordered(self.use_cases),
            attributes=_dedupe_ordered(self.attributes),
        )


@dataclass(frozen=True)
class QueryExpressiveIntent:
    vibes: list[str] = field(default_factory=list)

    def normalized(self) -> QueryExpressiveIntent:
        return QueryExpressiveIntent(vibes=_dedupe_ordered(self.vibes))


@dataclass(frozen=True)
class QueryMeaning:
    """Query-side semantic representation (per project × category × query/cluster)."""

    project_id: int
    category_id: int
    cluster_key: str
    version: MeaningLayerVersion = "v1_mvp"
    functional: QueryFunctionalIntent = field(default_factory=QueryFunctionalIntent)
    expressive: QueryExpressiveIntent = field(default_factory=QueryExpressiveIntent)

    def normalized(self) -> QueryMeaning:
        return QueryMeaning(
            project_id=int(self.project_id),
            category_id=int(self.category_id),
            cluster_key=str(self.cluster_key),
            version=self.version,
            functional=self.functional.normalized(),
            expressive=self.expressive.normalized(),
        )

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self.normalized())
