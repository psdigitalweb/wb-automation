"""Query meaning library and meaning-aware matcher services."""

__all__ = [
    "MeaningAwareMatcherError",
    "MissingQueryMeaningLibraryError",
    "QueryMeaningLibraryError",
    "build_query_meaning_library",
    "list_query_meanings",
    "run_meaning_aware_matcher",
]


def __getattr__(name: str):
    if name in {"QueryMeaningLibraryError", "build_query_meaning_library", "list_query_meanings"}:
        from app.services.seo.query_meaning_matcher import library

        return getattr(library, name)
    if name in {"MeaningAwareMatcherError", "MissingQueryMeaningLibraryError", "run_meaning_aware_matcher"}:
        from app.services.seo.query_meaning_matcher import matcher

        return getattr(matcher, name)
    raise AttributeError(name)
