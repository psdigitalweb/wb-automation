"""LLM-backed expressive layer (offline/precompute only).

Iteration 19 scope:
- Category expressive extraction inputs from reviews (primary) + titles (secondary)
- Strict parsing/validation + caching

This package must NOT introduce runtime hot-path dependency on LLM.
"""

