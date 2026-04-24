"""Production meaning-atoms helpers for SEO matching."""

__all__ = [
    "ATOMS_SOURCE_VERSION",
    "build_query_atoms_for_category",
    "ensure_sku_atoms",
    "get_atoms_payload",
    "get_latest_atoms_record",
    "merge_sku_and_vision_atoms",
]


def __getattr__(name: str):
    if name in __all__:
        from app.services.seo.meaning_atoms import storage

        return getattr(storage, name)
    raise AttributeError(name)
