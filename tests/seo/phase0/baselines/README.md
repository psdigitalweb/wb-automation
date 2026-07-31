# Phase 0 baseline snapshots

These files capture the observable SEO baseline before Phase 0 backend
unification starts.

- Treat every file under `812_pre_phase0/` as read-only.
- Regenerate only via `python -m scripts.phase0.capture_baseline ...`.
- If a later step changes one of these snapshots, the diff must be explained
  and intentionally accepted.
