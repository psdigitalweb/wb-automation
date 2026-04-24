# Task 04 — Query Pruning + Basic Annotation

## Read First

- docs/seo-module/00_master_context.md
- docs/seo-module/01_architecture.md
- docs/seo-module/02_roadmap.md
- docs/seo-module/tasks/task_01_foundation.md
- docs/seo-module/tasks/task_02_query_ingestion.md
- docs/seo-module/tasks/task_03_query_dataset_unification_and_pruning_prep.md

Treat these documents as the source of truth.

---

## Goal

Implement the first deterministic pruning and basic annotation layer on top of the unified query dataset.

This task is about:

- converting preparation flags into explicit pruning decisions
- assigning basic query labels needed for the next Query Pipeline step
- producing a clean and explainable query set for future query clustering

This is still NOT query clustering, NOT embeddings, NOT scoring, and NOT LLM work.

---

## Context

At this point we already have:

- local WB frequency CSV ingestion
- raw query persistence
- deterministic query normalization
- unified query dataset assembly
- deterministic preparation flags
- head / mid / tail split inputs

The next step is to turn this prepared dataset into a usable query layer for Phase 2 Query Pipeline.

This task must stay deterministic and explainable.

---

## In Scope

### 1. Deterministic pruning decisions

Implement explicit pruning decisions for canonical queries in the unified dataset.

Minimum output fields per canonical query:

- pruning_status
- pruning_reason_code
- is_kept_for_pipeline

Supported pruning_status values:

- keep
- drop
- review

Rules must be deterministic and explainable.

At minimum, use available preparation signals such as:

- empty candidate
- duplicate candidate
- garbage candidate
- informational candidate
- navigation candidate
- missing demand / weak source coverage if applicable

Do NOT introduce fuzzy logic.

---

### 2. Basic annotation

Implement a minimal annotation layer for kept/review queries.

Minimum annotation fields:

- query_type
- intent_type
- annotation_reason_code

Supported intent_type values:

- product
- category
- informational
- garbage
- unknown

Supported query_type values must be simple and useful for next steps.
At minimum, support:

- head
- mid
- tail

Reuse existing head / mid / tail assignment from Task 03 where appropriate.

Annotation must be rule-based only.

---

### 3. Rule set

Implement a readable rule set with explicit precedence.

Minimum rule groups:

- empty / malformed
- garbage / noise
- navigation / marketplace
- informational
- product-like
- category-like
- unknown fallback

First matched rule must win where precedence is required.

Rules must be easy to inspect and extend.

---

### 4. Persistence

Persist results in a dedicated annotation/pruning table.

Table requirements:

- link to canonical query / unified dataset entity
- project_id
- category_id
- pruning_status
- pruning_reason_code
- is_kept_for_pipeline
- query_type
- intent_type
- annotation_reason_code
- created_at

If versioning is already expected in current schema patterns, preserve compatibility.
Do not redesign the architecture without necessity.

---

### 5. Clean query set output

Provide a deterministic way to obtain the clean query set for the next pipeline step.

Need to support retrieval of:

- all kept queries
- kept queries by bucket (head / mid / tail)
- dropped queries with reasons
- review queries with reasons

This may be exposed via:

- service method
- script
- internal debug/admin endpoint

No UI required.

---

### 6. Diagnostics

Provide readable diagnostics for one run.

Minimum summary fields:

- total canonical queries processed
- keep / drop / review counts
- counts by pruning_reason_code
- counts by intent_type
- counts by head / mid / tail among kept queries
- top kept queries by ranking value
- sample dropped queries with reasons
- sample review queries with reasons
- sample unknown queries

Diagnostics must be usable for manual verification by developers/operators.

---

### 7. Tests

Add or extend tests to cover:

- deterministic pruning outcomes
- deterministic annotation outcomes
- rule precedence correctness
- persistence correctness
- correct clean query retrieval
- correct diagnostics output shape

Tests must include representative examples for:

- empty queries
- garbage queries
- navigation queries
- informational queries
- product-like queries
- category-like queries
- unknown fallback queries

---

## Out of Scope

Do NOT implement:

- query clustering
- hybrid cluster-prior annotation
- embeddings
- scoring
- generation
- LLM classification
- UI
- manual review workflow UI
- semantic matching

---

## Expected Output

At the end of this task, we should have:

1. Explicit pruning decisions for canonical queries
2. Deterministic basic annotation for queries kept in pipeline scope
3. A clean query set ready for future query clustering
4. Explainable reasons for keep / drop / review outcomes
5. Diagnostics proving the resulting dataset is usable

---

## Constraints

- Reuse existing foundation, ingestion, and unified dataset work
- Do not redesign existing architecture unless absolutely necessary
- Keep all logic deterministic
- Keep all decisions explainable
- Do not introduce advanced NLP or semantic models
- Keep implementation extensible for later Query Pipeline steps

---

## Process Requirement

First:

- provide implementation plan
- list files to create/modify
- specify persistence approach
- specify pruning rule precedence
- specify annotation rule precedence
- specify how clean query set will be retrieved

Only after approval:

- proceed with implementation

---

## Implementation Note (v1)

- Input remains the on-demand unified dataset from Task 03; no separate canonical query table is added.
- Persistence reuses:
  - `seo_query_annotations` as the current-state table keyed by `project_id × category_id × normalized_query_text`
  - `seo_query_annotation_versions` as the version-history table with full snapshot payloads
- `normalized_query_id` is now optional traceability to CSV-backed canonical rows and may be `NULL` for WB-only queries.
- Pruning precedence:
  - `empty_malformed -> drop`
  - `navigation_marketplace -> drop`
  - `garbage_noise -> drop`
  - `informational_query -> review`
  - `weak_coverage_no_demand -> review`
  - `pipeline_candidate -> keep`
- Annotation precedence:
  - garbage by pruning reason
  - informational by marker
  - product for multi-token queries with demand
  - category for single-token fallback
  - unknown fallback otherwise
- `query_type` mirrors Task 03 `head_tail_bucket` directly: `head`, `mid`, `tail`.
- Clean query retrieval assembles the fresh unified dataset and overlays persisted current annotations by canonical key.
- Developer execution path:

```bash
python scripts/run_query_pruning.py --project-id 1 --category-id 821
```
