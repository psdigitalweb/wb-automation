# Task 03 — Query Dataset Unification + Pruning Preparation

## Read First

- docs/seo-module/00_master_context.md
- docs/seo-module/01_architecture.md
- docs/seo-module/02_roadmap.md
- docs/seo-module/tasks/task_01_foundation.md
- docs/seo-module/tasks/task_02_query_ingestion.md

Treat these documents as the source of truth.

---

## Goal

Prepare a unified query layer for the Query Pipeline phase.

This task is about:

- identifying and unifying current query sources
- defining the canonical query entity for project × category scope
- preparing deterministic pruning inputs
- preparing head / tail split inputs for the next pipeline step

This is still NOT query clustering, NOT embeddings, NOT scoring, and NOT LLM work.

---

## Context

At this point we already have:

- local WB frequency CSV ingestion
- raw query persistence
- deterministic query normalization

However, query data currently exists in multiple forms and sources.

Before implementing query clustering and hybrid annotation, we need one unified query dataset that can serve as the input layer for the Query Pipeline.

This task is the bridge between:

- Phase 1 foundation work
- Phase 2 query pipeline work

---

## In Scope

### 1. Query source inventory

Identify all currently used query sources relevant to SEO query processing.

At minimum, account for:

- normalized queries from local WB frequency CSV import
- query data already received from WB API and stored in existing project tables

For each source, document:

- source table / model
- project_id linkage
- category_id linkage
- query text field
- frequency / demand fields if present
- source-specific identifiers if present
- current freshness / timestamp fields if present

Output must make clear what sources are available and what can be reliably joined.

---

### 2. Canonical query entity definition

Define the canonical query entity for pipeline use.

The canonical entity must:

- operate within project × category scope
- use normalized query text as the primary matching basis unless a better existing stable key already exists
- preserve traceability back to source records
- support multiple contributing sources per canonical query

The result of this task must clearly specify:

- what one canonical query row represents
- how multiple source records map into one canonical query
- what fields belong to canonical query level vs source-record level

---

### 3. Unified dataset assembly

Implement a service that assembles a unified query dataset for one project_id + category_id.

The assembled dataset should combine available signals from all relevant query sources.

Minimum required per canonical query:

- normalized_query_text
- project_id
- category_id
- source_presence flags
- source_count
- source record references
- aggregated frequency / demand fields where available
- first_seen_at / last_seen_at if derivable
- raw source payload references only if already consistent with current architecture

The assembly must be deterministic.

Do NOT invent fuzzy matching or semantic matching in this task.

Matching basis should be explicit and explainable.

---

### 4. Pruning preparation flags

Add deterministic preparation flags for future pruning.

Minimum flags:

- is_empty_candidate
- is_duplicate_candidate
- is_garbage_candidate
- is_informational_candidate
- is_navigation_candidate

These flags are not final business decisions yet.

They are preparation signals for the next task.

Rules must remain simple, deterministic, and explainable.

Do NOT build a full classifier in this task.

---

### 5. Head / tail split preparation

Prepare fields required for future differentiated processing of top queries vs long tail queries.

At minimum:

- head_tail_bucket
- bucket_basis
- ranking_value_used

The implementation must support assigning each canonical query into a simple bucket such as:

- head
- mid
- tail

Use currently available demand/frequency signals only.

If multiple sources provide frequency-like signals, document and implement the precedence/aggregation rule explicitly.

Do NOT implement clustering in this task.

---

### 6. Diagnostics

Provide a readable diagnostic summary for one assembled dataset.

Minimum summary fields:

- project_id
- category_id
- total canonical queries
- total source-linked queries
- queries by source presence combination
- queries by head_tail_bucket
- top queries by ranking value
- sample rows with conflicting or partial source coverage
- sample rows flagged by pruning preparation rules

Diagnostics may be returned as:

- structured dict / response object
- script output
- debug endpoint response

But must be usable for manual verification by developers/operators.

---

### 7. Access pattern

Implement the smallest practical execution path for developers/operators.

Allowed options:

- service callable from shell / REPL
- internal script
- internal debug/admin endpoint

Choose the option that best fits current project conventions.

Do NOT build end-user UI.

---

### 8. Tests

Add or extend tests to cover:

- source inventory assumptions where testable
- deterministic unified dataset assembly
- correct canonical merging by normalized query
- correct source traceability
- correct preparation flag output shape
- correct head / tail bucketing output shape
- correct diagnostics output shape

---

## Out of Scope

Do NOT implement:

- final pruning decisions
- full query annotation logic
- query clustering
- embeddings
- scoring
- generation
- LLM classification
- UI
- fuzzy semantic deduplication
- cross-category semantic reconciliation

---

## Expected Output

At the end of this task, we should have:

1. A clearly defined canonical query entity
2. A deterministic unified query dataset for project × category
3. Traceability from canonical queries back to source records
4. Preparation flags for future pruning
5. Head / tail split inputs for future query pipeline logic
6. Diagnostics proving the assembly is usable

---

## Constraints

- Reuse existing foundation and ingestion work
- Do not redesign existing DB schema unless absolutely necessary
- Do not introduce semantic matching
- Do not introduce advanced NLP
- Keep logic deterministic and explainable
- Keep implementation extensible for next Phase 2 steps

---

## Process Requirement

First:

- provide implementation plan
- list files to create/modify
- specify how unified dataset assembly will be triggered
- specify source inventory assumptions
- specify canonical query matching rule
- specify head / tail bucketing rule

Only after approval:

- proceed with implementation

---

## Implementation Note (v1)

- Unified dataset is assembled on-demand in memory; no canonical DB table is added in this task.
- Sources included:
  - latest completed `seo_queries_normalized` batch for `project_id × category_id`
  - `wb_search_query_terms` joined through `products(project_id, nm_id, subject_id)`
  - `wb_search_query_daily` joined through `products(project_id, nm_id, subject_id)`
- Canonical matching rule:
  - one canonical row per `project_id × category_id × normalized_query_text`
  - WB rows are normalized with existing `normalize_query_text(...)`
  - no fuzzy matching, no semantic reconciliation
- Head/mid/tail bucketing:
  - use `frequency_total` first
  - fallback to `orders_total`
  - fallback to `0` with bucket basis `none`
- Developer execution path:

```bash
python scripts/prepare_seo_query_dataset.py --project-id 1 --category-id 821
```
