# Task 04.1 — Pruning Hardening

## Read First

- docs/seo-module/00_master_context.md
- docs/seo-module/01_architecture.md
- docs/seo-module/02_roadmap.md
- docs/seo-module/tasks/task_01_foundation.md
- docs/seo-module/tasks/task_02_query_ingestion.md
- docs/seo-module/tasks/task_03_query_dataset_unification_and_pruning_prep.md
- docs/seo-module/tasks/task_04_query_pruning_and_basic_annotation.md

Treat these documents as the source of truth.

---

## Goal

Harden the Task 04 pruning/annotation layer before moving to query clustering.

This task is about:

- validating migration safety for the canonical annotation schema
- making material-change versioning rules explicit and deterministic
- making overlay behavior explicit when canonical queries disappear from the current unified dataset
- performing a lightweight diagnostics scalability sanity check

This task is NOT a redesign.

This task must remain narrow and implementation-focused.

---

## Context

Task 04 introduced:

- canonical-key-based persistence for pruning/annotation results
- versioned annotation snapshots
- clean query set retrieval via unified dataset recomputation + overlay of persisted decisions
- CLI and diagnostics

Before using this as a stable input for future query clustering, we need to remove the main correctness risks.

---

## In Scope

### 1. Migration safety verification

Verify that the migration evolving `seo_query_annotations` for canonical pruning is safe to apply on a non-empty database.

The verification must explicitly cover:

- existing rows in `seo_query_annotations`
- transition of `normalized_query_id` to nullable
- population / compatibility of `normalized_query_text`
- new uniqueness rule on `(project_id, category_id, normalized_query_text)`
- preservation of current/latest version pointers
- compatibility of `seo_query_annotation_versions`

Implementation may include:

- migration adjustments if required
- data backfill step inside migration if required
- defensive migration comments
- migration-focused tests where practical

Do NOT redesign the schema beyond what is necessary for safety.

---

### 2. Explicit material-change comparator

Make version creation logic explicitly deterministic.

Define and implement one clear rule for when a new version row must be created.

Required behavior:

- identical effective snapshot must NOT create a new version
- changed effective snapshot must create a new version
- comparison must ignore non-semantic fields that should not trigger version churn

At minimum, explicitly define whether comparison includes:

- pruning fields
- annotation fields
- head_tail_bucket / query_type
- ranking_value_used
- bucket_basis
- source presence summary
- preparation flags
- source refs summary
- explainability timestamps / freshness hints

The comparator must be readable and tested.

---

### 3. Overlay policy for disappeared canonical queries

Make overlay behavior explicit when a canonical query has a persisted current decision but is absent from the newly assembled unified dataset.

Required policy for v1:

- disappeared canonical queries must NOT be returned in the current clean query set
- disappeared canonical queries remain in persisted history/current tables for traceability
- diagnostics should be able to surface the count and/or sample of such stale persisted decisions if practical

Implementation must make this behavior explicit in code and tests.

Do NOT introduce a full stale-lifecycle framework.

---

### 4. Diagnostics scalability sanity check

Perform a narrow sanity check on diagnostics generation.

Verify that diagnostics:

- respect `top_limit` and `samples_limit`
- do not perform obviously quadratic in-memory processing
- do not require loading unnecessary full payloads for small preview sections if avoidable within current design

This is NOT a full optimization task.

Only fix clearly material inefficiencies discovered during review.

---

### 5. Tests

Add or extend tests to cover:

- migration safety assumptions where practical
- stable no-op rerun does not create extra version rows
- semantic change does create a new version row
- disappeared canonical query is excluded from clean query set
- diagnostics limits are respected
- any migration backfill assumptions introduced for safety

---

## Out of Scope

Do NOT implement:

- query clustering
- scoring
- embeddings
- LLM classification
- stale lifecycle management UI
- major persistence redesign
- broad performance optimization campaign

---

## Expected Output

At the end of this task, we should have:

1. A migration that is safe to apply to realistic existing data
2. Deterministic version creation behavior
3. Explicit and tested overlay behavior for disappeared canonical queries
4. Basic confidence that diagnostics will not misbehave on larger datasets

---

## Constraints

- Keep the current architecture
- Do not introduce new core tables unless absolutely necessary
- Keep changes minimal and targeted
- Prefer explicit comments and tests over clever abstractions
- Do not broaden scope beyond hardening

---

## Process Requirement

First:

- provide implementation plan
- list files to create/modify
- specify migration safety approach
- specify exact material-change comparison rule
- specify explicit disappeared-query overlay behavior
- specify diagnostics sanity-check approach

Only after approval:

- proceed with implementation