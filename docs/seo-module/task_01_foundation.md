Task 01 — SEO Foundation (Models + Migrations + Structure)
Read First
docs/seo-module/00_master_context.md
docs/seo-module/01_architecture.md
docs/seo-module/02_roadmap.md

Treat these documents as the source of truth.

Goal

Create the foundational layer of the SEO module:

database schema
SQLAlchemy models
module structure
provider abstraction
basic ingestion and clustering skeletons

This is NOT full implementation.

In Scope
1. Database (Alembic + models)

Create tables:

seo_query_batches
seo_queries_raw
seo_queries_normalized
seo_query_clusters
seo_query_annotations
seo_query_annotation_versions
seo_sku_cluster_runs
seo_sku_clusters
seo_sku_cluster_assignments
seo_cluster_profiles
seo_cluster_profile_versions
seo_score_runs
seo_query_scores
seo_score_explanations
seo_content_versions
seo_generation_runs
2. Module structure

Create folders:

app/services/seo/
 providers/
 query_pipeline/
 clustering/
 profiles/
 scoring/
 generation/

3. LLM Provider Abstraction

Implement:

ChatProvider interface
EmbeddingProvider interface
OpenRouterProvider adapter

Env config:

OPENROUTER_API_KEY
OPENROUTER_BASE_URL
OPENROUTER_CHAT_MODEL
OPENROUTER_EMBEDDING_MODEL

IMPORTANT:
Do NOT hardcode OpenRouter into business logic.

4. Query ingestion foundation

Implement:

CSV import service
store raw queries
normalize queries
deduplicate
store normalized queries
link to project_id and category_id
batch metadata
5. Clustering skeleton

Implement structure for:

clustering run
pre-segmentation hook (empty placeholder)
SKU representation builder (basic)
HDBSCAN hook (no full logic yet)

IMPORTANT:
Include noise handling strategy:

nearest cluster fallback (placeholder)
"other" cluster
manual_review_required flag
6. Scoring skeleton

Define structure:

Score components:

semantic_similarity
product_type_match
attribute_match
use_case_match
behavior_score
frequency_score
product_type_mismatch
attribute_mismatch
cluster_mismatch
competition_penalty

Store explainability in seo_score_explanations.

7. Default scoring weights

Add config with initial weights:

semantic_similarity = 0.35
product_type_match = 0.20
attribute_match = 0.15
use_case_match = 0.10
behavior_score = 0.10
frequency_score = 0.10
product_type_mismatch = 0.25
attribute_mismatch = 0.10
cluster_mismatch = 0.15
competition_penalty = 0.10

Make them configurable (not hardcoded deep in logic).

Out of Scope

DO NOT implement:

text generation (title/description)
production LLM prompts
query annotation logic
competition parsing
UI
full clustering logic
feedback loop
Expected Output
Alembic migration
SQLAlchemy models
module structure
provider abstraction
ingestion skeleton
clustering skeleton
scoring skeleton

Code must compile and integrate cleanly.

Constraints
Do not break existing project structure
Do not modify unrelated modules
Do not invent business logic beyond defined scope
Leave TODOs where logic is incomplete
Keep code extensible for next phases
Process Requirement

First:

provide implementation plan
list of files to create/modify

Only after approval:

proceed with implementation
