# Task 05 — Query Clustering

## Read First

- docs/seo-module/00_master_context.md
- docs/seo-module/01_architecture.md
- docs/seo-module/02_roadmap.md
- docs/seo-module/tasks/task_01_foundation.md
- docs/seo-module/tasks/task_02_query_ingestion.md
- docs/seo-module/tasks/task_03_query_dataset_unification_and_pruning_prep.md
- docs/seo-module/tasks/task_04_query_pruning_and_basic_annotation.md
- docs/seo-module/tasks/task_04_1_pruning_hardening.md

Treat these documents as the source of truth.

---

## Goal

Implement the first deterministic query clustering layer on top of the clean query set.

This task is about:

- grouping kept queries into stable query clusters
- preparing the dataset for later hybrid annotation
- preserving explainability and traceability from cluster to source queries

This task is still NOT embeddings-based matching, NOT scoring, NOT generation, and NOT LLM usage.

---

## Context

At this point we already have:

- query ingestion from CSV
- deterministic normalization
- unified query dataset assembly
- pruning and basic annotation
- clean query set retrieval

The next step in the roadmap is Query Pipeline work:
- query clustering
- hybrid annotation
- caching and incremental updates

This task covers only the clustering part.

---

## In Scope

### 1. Input dataset

Use only the current clean query set from Task 04.

Cluster input scope:

- project_id
- category_id
- only queries with is_kept_for_pipeline = true

Support optional filtering by query_type / bucket:

- head
- mid
- tail

Do NOT cluster dropped queries.

---

### 2. Clustering objective

Group similar queries into deterministic clusters suitable for later annotation.

The clustering objective for v1 is:

- group close textual variants
- group narrow lexical families
- keep explainability high
- avoid opaque semantic grouping

This is a practical query clustering layer, not a research system.

---

### 3. Clustering approach (v1)

Implement a deterministic non-LLM clustering approach.

Allowed basis:

- normalized query text
- tokenized normalized text
- simple lexical overlap / token rules
- optional n-gram or phrase signatures if useful and deterministic

The approach must be explicit and inspectable.

Do NOT introduce:

- embeddings
- semantic vector DB logic
- LLM-based grouping
- fuzzy black-box clustering

If multiple heuristics are used, define precedence clearly.

---

### 4. Cluster entity

Persist query clusters in dedicated tables.

Need to support:

- cluster current state
- cluster membership
- traceability from query to cluster
- rerun safety

Minimum cluster-level fields:

- id
- project_id
- category_id
- cluster_key or stable cluster code
- cluster_label_candidate
- query_count
- head_query_count
- mid_query_count
- tail_query_count
- top_query_text
- created_at
- updated_at

Minimum membership-level fields:

- cluster_id
- normalized_query_text or canonical query reference
- query_type
- ranking_value_used
- membership_reason_code

Reuse existing persistence patterns where reasonable.
Do not redesign the architecture unnecessarily.

---

### 5. Stable cluster key

Define an explicit deterministic rule for cluster identity.

Examples of acceptable basis:

- canonical representative query
- deterministic token signature
- sorted core token key

The cluster key must be stable across no-op reruns on unchanged input.

If cluster composition changes materially, cluster updates must remain explainable.

---

### 6. Cluster label candidate

For each cluster produce a simple label candidate for diagnostics and later manual understanding.

V1 label candidate may be based on:

- most representative query
- top ranked query in cluster
- deterministic token signature

Do NOT generate labels via LLM.

---

### 7. Diagnostics

Provide readable diagnostics for one clustering run.

Minimum summary fields:

- project_id
- category_id
- total input queries
- total clusters created
- singleton cluster count
- average cluster size
- top clusters by size
- sample clusters with members
- sample ambiguous/small clusters if detectable
- counts by query_type inside clusters

Diagnostics may be returned as:

- structured dict / response object
- script output
- internal debug/admin endpoint response

Diagnostics must be usable for developer/operator verification.

---

### 8. Access pattern

Implement the smallest practical execution path.

Allowed options:

- service callable from shell / REPL
- internal script
- internal debug/admin endpoint

No UI required.

---

### 9. Tests

Add or extend tests to cover:

- deterministic clustering on unchanged input
- stable cluster key generation
- correct persistence of clusters and memberships
- traceability from clean query to cluster
- correct diagnostics output shape
- representative examples of:
  - close lexical variants grouped together
  - unrelated queries separated
  - singleton clusters
  - bucket-aware counts

---

## Out of Scope

Do NOT implement:

- hybrid annotation logic
- embeddings
- scoring
- generation
- LLM clustering
- UI
- automatic semantic label generation
- cross-category clustering

---

## Expected Output

At the end of this task, we should have:

1. A deterministic clustering layer over the clean query set
2. Stable persisted query clusters
3. Membership traceability from query to cluster
4. Diagnostics showing whether clustering is usable
5. A cluster structure ready for the next hybrid annotation step

---

## Constraints

- Reuse existing clean query set and persistence patterns
- Keep clustering deterministic and explainable
- Do not introduce opaque semantic logic
- Do not broaden scope into scoring/generation
- Keep implementation extensible for later Query Pipeline work

---

## Process Requirement

First:

- provide implementation plan
- list files to create/modify
- specify clustering heuristic
- specify cluster key rule
- specify persistence approach
- specify run command / access path

Only after approval:

- proceed with implementation

---

## Implementation Note (v1)

- Input is the current clean query set from Task 04 only; dropped/review queries are excluded.
- Deterministic clustering heuristic:
  - exact unordered token signature groups first
  - singleton multi-token queries may join an existing parent signature by `superset_plus_one_token`
  - everything else becomes a singleton cluster
- Stable cluster identity:
  - `cluster_key = "qcl:" + base_signature`
  - `base_signature` is the shortest member exact signature, then lexicographically minimal
- Persistence:
  - `seo_query_clusters` stores current cluster state and counts
  - `seo_query_cluster_memberships` stores current query-to-cluster memberships
- Label candidate is derived from the representative query only; no LLM label generation is used.
- Developer execution path:

```bash
python scripts/run_query_clustering.py --project-id 1 --category-id 821
```
