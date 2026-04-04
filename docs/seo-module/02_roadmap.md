# SEO Module — Roadmap

## Phase 1 — Foundation (CURRENT)
- DB schema
- SQLAlchemy models
- module structure
- LLM provider abstraction
- OpenRouter adapter (no usage yet)
- query ingestion (CSV)
- query normalization
- clustering skeleton (HDBSCAN hook)
- scoring skeleton
- explainability storage

---

## Phase 2 — Query Pipeline
- query clustering
- hybrid annotation:
  - top queries → individual
  - tail → cluster prior
- caching and incremental updates

---

## Phase 3 — SKU Clustering
- pre-segmentation rules
- full HDBSCAN integration
- noise assignment strategy
- cluster validation tools

---

## Phase 4 — Profiles & Scoring
- cluster profile extraction
- scoring refinement
- competition signal integration
- weight tuning

---

## Phase 5 — Generation
- generation constraints (from reviews)
- title/description generation
- prompt design
- human review workflow

---

## Phase 6 — Feedback Loop
- performance tracking
- weight updates
- semi-automatic tuning

---

## Important Rule

Each phase must be completed before moving to the next.

No premature implementation of later phases.
