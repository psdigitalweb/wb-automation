# Task 03 — Query Annotation (Rule-based)

## Read First

- docs/seo-module/00_master_context.md
- docs/seo-module/01_architecture.md
- docs/seo-module/02_roadmap.md
- docs/seo-module/tasks/task_01_foundation.md
- docs/seo-module/tasks/task_02_query_ingestion.md

Treat these documents as the source of truth.

---

## Goal

Introduce a deterministic rule-based annotation layer for normalized queries.

This task is about:

- assigning basic intent and relevance labels to normalized queries
- enabling initial pruning before clustering
- preparing data for Phase 2 Query Pipeline

This is still NOT clustering, NOT embeddings, and NOT LLM usage.

---

## Context

From architecture:

- query pipeline requires pruning and annotation before clustering :contentReference[oaicite:0]{index=0}  
- annotation must support later hybrid logic (top queries vs tail) :contentReference[oaicite:1]{index=1}  

From master context:

- system must filter high-frequency irrelevant queries  
- explainability is mandatory  
- no black-box logic allowed :contentReference[oaicite:2]{index=2}  

---

## In Scope

### 1. Rule-based annotation layer

Implement a deterministic classifier over `seo_queries_normalized`.

For each query assign:

- is_relevant (bool)
- intent_type (enum)
- rule_code (string)
- confidence (float, heuristic)

---

### 2. Intent types

Supported values:

- product
- category
- informational
- garbage

Definitions:

- product → clear purchasable intent
- category → broad product group
- informational → research intent, not direct purchase
- garbage → non-usable for SEO/scoring

---

### 3. Rule system (v1)

Implement simple deterministic rules.

#### 3.1 Garbage rules

Conditions:

- contains stop words (e.g. "как", "что", "почему", "отзывы")
- marketplace/navigation terms (e.g. "wildberries", "ozon")
- empty or malformed queries
- no product meaning

---

#### 3.2 Product intent rules

Conditions:

- contains product modifiers (size, gender, type, etc.)
- multi-word queries with product structure
- clearly mappable to SKU

---

#### 3.3 Category intent rules

Conditions:

- single-word or generic plural product terms
- no modifiers

---

#### 3.4 Informational rules

Conditions:

- question-like structure
- contains informational verbs
- not directly purchasable

---

### 4. Rule execution order

Strict order:

1. garbage
2. product
3. category
4. informational

First matched rule wins.

---

### 5. Storage

Persist annotation results.

Table:

- seo_query_annotations

Fields:

- id
- project_id
- category_id
- normalized_query_id
- is_relevant
- intent_type
- confidence
- rule_code
- created_at

---

### 6. Explainability

Mandatory:

- store rule_code for each classification
- rules must be traceable and readable

No implicit logic allowed.

---

### 7. Execution

Provide a way to run annotation for:

- one batch
- one category
- or entire project

Possible interfaces:

- service method
- script
- internal endpoint

No UI required.

---

### 8. Diagnostics

After execution return:

- total queries processed
- counts per intent_type
- % garbage
- top queries per intent (sample)
- queries with low confidence

---

### 9. Data safety

- do not overwrite previous annotations without versioning strategy
- allow re-run safely
- keep deterministic outputs

---

### 10. Tests

Cover:

- deterministic classification
- rule priority correctness
- garbage filtering
- correct persistence
- correct diagnostics output

---

## Out of Scope

Do NOT implement:

- clustering
- embeddings
- LLM classification
- scoring logic
- generation
- UI

---

## Expected Output

At the end of this task:

1. All normalized queries can be annotated
2. Garbage queries are filtered
3. Queries have intent labels
4. Annotation is explainable
5. Diagnostics allow manual validation

---

## Constraints

- strictly follow existing architecture
- no redesign of ingestion layer
- no advanced NLP
- no probabilistic models
- keep logic transparent and extendable

---

## Relation to Roadmap

This task completes the first usable part of the Query Pipeline preparation:

- ingestion → done in Task 02  
- annotation → current task  
- clustering → next phase :contentReference[oaicite:3]{index=3}  

---

## Next Step

Task 04:

- query clustering
- hybrid annotation (top vs tail)
- integration with clustering pipeline