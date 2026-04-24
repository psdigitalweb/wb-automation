"""Meaning Extraction (MVP) canonical types and builders.

This package defines structured meaning objects (CategoryMeaning, ProductProjection, QueryMeaning)
to keep query-side pipeline artifacts separate from product-side meaning representations.
"""

from app.services.seo.meaning_extraction.types import (
    CategoryExpressiveMeaning,
    CategoryFunctionalMeaning,
    CategoryMeaning,
    ProductExpressiveProfile,
    ProductFunctionalProfile,
    ProductProjection,
    QueryExpressiveIntent,
    QueryFunctionalIntent,
    QueryMeaning,
)
from app.services.seo.meaning_extraction.category_meaning import CategoryMeaningThresholds, build_category_meaning
from app.services.seo.meaning_extraction.product_projection import ProductProjectionBuildFlags, build_product_projection
from app.services.seo.meaning_extraction.query_meaning import QueryMeaningBuildFlags, formalize_query_meaning

__all__ = [
    "CategoryExpressiveMeaning",
    "CategoryFunctionalMeaning",
    "CategoryMeaning",
    "ProductExpressiveProfile",
    "ProductFunctionalProfile",
    "ProductProjection",
    "QueryExpressiveIntent",
    "QueryFunctionalIntent",
    "QueryMeaning",
    "CategoryMeaningThresholds",
    "build_category_meaning",
    "ProductProjectionBuildFlags",
    "build_product_projection",
    "QueryMeaningBuildFlags",
    "formalize_query_meaning",
]
