# Production Query Selection Workflow

> Status: planning document for Phase 1Q Step 0.
> Scope: production-targeted human-in-the-loop query selection for a SKU.
> Date: 2026-04-27.
> Source contracts: `CONTEXT_PRIMER.md`, `ROADMAP.md`, `CATEGORY_PROFILE_SPEC.md`, `OPERATOR_WORKFLOW.md`.

---

## 1. Executive Summary

Phase 1Q moves SEO query selection from research/preview tooling toward a minimal production workflow: category queries are imported and clustered, a product is selected, the operator provides a brief, an LLM proposes SKU-specific query candidates, and the operator explicitly approves the final query set before it can be used by SEO generation.

This document is a workflow lock, not an implementation spec for a large rewrite. The first implementation should reuse the existing query import, clustering, product, AI vision, expressive prior, and query-set surfaces where practical. The missing piece is a production service and UI path for operator brief + reproducible LLM query selection + operator review + approved query set.

Human approval is mandatory. No generated candidate set becomes production input for generation until the operator approves it.

---

## 2. Product Goal

Give the operator a reliable path:

1. Upload one or more category query files.
2. Start clustering as a separate operator action.
3. Verify category readiness: imported queries, processed corpus, clusters, expressive prior.
4. Pick an in-stock product in the category.
5. Confirm product readiness: card data, AI vision, saved category query data.
6. Fill a lightweight operator brief.
7. Run LLM query selection for the SKU.
8. Review candidates, approve/reject explicitly.
9. Save the approved query set as the production SEO query input for that SKU.

The core product promise is SKU-specific semantic relevance, not category-wide popularity optimization. Category-level `orders` / `conversion` fields must not drive scoring or labels.

---

## 3. Production Workflow Screens

### 3.1. Category Query Data Screen

Purpose: manage category query corpus before SKU work begins.

Required behavior:
- Accept multiple CSV/files for the same category import session.
- Show upload/import status per file and aggregate category status.
- Do not auto-cluster immediately after upload; expose "Build clusters" as a separate operator action.
- Show query count, processed/normalized count, cluster count, latest batch, and failure/warning messages.
- Let the operator open the cluster list.
- Let the operator expand a cluster and inspect included queries.

### 3.2. Product List Screen

Purpose: choose the SKU to work on.

Required columns:
- Product photo.
- Product name.
- Category.
- `nm_id`.
- Vendor article / SKU article.
- Product review count.

Required filters:
- Category.
- Stock availability.

### 3.3. Product Page

Purpose: inspect SKU evidence and either review previous results or start selection.

Required blocks:
- Product photo, name, characteristics, description.
- Saved AI vision verdict.
- Existing selected/approved queries when analysis exists.
- "Select queries" action when analysis does not exist.

Button eligibility:
- Enabled only when AI vision exists and category query data is ready.
- Disabled state explains missing readiness item.

### 3.4. Query Selection Readiness Block

Purpose: make prerequisites explicit before LLM selection.

Statuses:
- Category queries uploaded and processed.
- Clusters built.
- Category expressive prior ready.
- AI vision ready.

When all statuses pass, the operator can fill the brief and start query selection.

### 3.5. Operator Brief Block

Purpose: capture operator intent immediately before selection.

Fields:
- Primary focus: what matters most.
- Secondary focus: what matters but is not decisive.
- Allowed hypotheses: what the LLM may include as plausible but not proven.
- Exclusions: what must not be selected.
- Desired query count.

The brief is not a separate heavy versioned entity at this stage. Store it inside the query-selection run input as structured JSON.

### 3.6. Operator Review Screen

Purpose: approve the production result.

Candidate table columns:
- Query.
- Frequency.
- Cluster.
- Meaning line.
- Candidate type: selected / operator candidate.
- Status: strong / plausible / risky.
- Risk.
- Explanation.
- Approve / reject action.

Rejected candidates remain part of review history, but rejected/unselected queries are not returned as a separate `rejected` LLM output class. Everything not selected by the LLM is ignored by omission.

---

## 4. Technical Components Already Available

Backend:
- Query CSV import router: `src/app/routers/seo_query_import.py`.
- Query pipeline services: `src/app/services/seo/query_pipeline/*`.
- Clustering pipeline: `src/app/services/seo/query_pipeline/clustering.py`.
- Clustering services: `src/app/services/seo/clustering/*`.
- Query storage tables: `seo_query_batches`, `seo_queries_normalized`, `seo_query_clusters`, `seo_query_cluster_memberships`.
- Product endpoints: `src/app/routers/seo_products.py`.
- SKU meaning / evidence endpoints: `src/app/routers/seo_sku_meaning.py`.
- Category expressive prior services: `src/app/services/seo/expressive_llm/*`.
- AI vision components: `src/app/services/seo/atoms/v1/vision.py`.
- Query-set related components: `seo_sku_query_sets`, `seo_sku_query_set_items`, `src/app/services/seo/query_set_candidate.py`.
- Generation endpoints and services: `src/app/routers/seo_generation.py`, `src/app/services/seo/generation/*`.

Frontend:
- Existing SEO category/product/debug surfaces under `frontend/app/app/project/[projectId]/seo/**`.
- Existing badges/components from Iteration 2 can be reused where they match the production workflow.

These components are inputs to the production workflow. They do not yet form the required end-to-end operator path.

---

## 5. Missing Production Components

Required minimal additions:

- Category readiness API that summarizes query import, normalization, clustering, expressive prior, and cluster counts.
- Explicit cluster-build action after upload.
- Cluster list/detail API and UI.
- Product list view with category and stock filters plus review count.
- Product readiness API for AI vision + category query data.
- Query selection run service that saves input, prompt, result, model, prompt version, and readiness snapshot.
- LLM prompt builder for production query selection through the controlled LLM client path.
- Candidate review state: approve/reject per returned candidate.
- Approved query-set finalization action that writes the production result for the SKU.
- Generation guard that uses only approved query sets for production SEO generation.

Out of scope for this step: designing a new matcher architecture, changing `CategoryProfile`, adding economic scoring, or creating a heavy versioned brief subsystem.

---

## 6. Data / Persistence Decisions

### 6.1. Query Selection Run

Production query selection needs a persisted run record. Minimal required fields:

- `project_id`.
- `category_id`.
- `nm_id`.
- `status`: pending / running / completed / failed / reviewed / approved.
- Readiness snapshot at run start.
- Operator brief JSON.
- Product card snapshot used in the prompt.
- AI vision snapshot or reference.
- Category expressive prior snapshot or reference.
- Candidate query source metadata: cluster ids, query ids, frequency values, meaning lines.
- Prompt text or structured prompt payload.
- Prompt version.
- Model name.
- LLM raw result.
- Parsed result.
- Error payload when failed.
- Created/updated timestamps.

This can be implemented with a new table in a later code step. Step 0 only locks the persistence contract.

### 6.2. Operator Brief

Do not create a separate versioned brief entity now. Store the brief as structured JSON inside the query-selection run. Reproducibility comes from saving the full run input, prompt, prompt version, model, and result.

### 6.3. Candidate Review

Each LLM-returned candidate needs review state:

- Candidate source: `selected_queries` or `operator_candidates`.
- Query id / normalized query id when available.
- Query text.
- Frequency.
- Cluster id and cluster label/meaning line when available.
- Status: strong / plausible / risky.
- Risk.
- Explanation.
- Operator decision: pending / approved / rejected.

The approved production result should be represented as an approved `SeoSkuQuerySet` or a compatible adaptation of the existing query-set tables.

### 6.4. Economic Fields

Category-level `orders` and `conversion` values from CSV payloads may be shown as diagnostic/import metadata later, but they must not be used for query scoring, candidate labels, or selection logic.

---

## 7. Backend Endpoint Plan

Minimal endpoint groups:

### 7.1. Category Query Data

- `GET /api/seo/categories/{category_id}/query-data/status`
  - Returns upload/import status, normalized query count, cluster count, expressive prior status, latest batch, and readiness booleans.
- `POST /api/seo/categories/{category_id}/query-data/import`
  - Accepts one or more files, creates import batch records, starts normalization/import.
- `POST /api/seo/categories/{category_id}/query-data/build-clusters`
  - Starts clustering as a separate operator action.
- `GET /api/seo/categories/{category_id}/clusters`
  - Returns cluster list with counts and representative meaning/label fields.
- `GET /api/seo/categories/{category_id}/clusters/{cluster_id}`
  - Returns queries in a cluster.

### 7.2. Product Workbench

- `GET /api/seo/products`
  - Supports category and stock filters; returns photo, name, category, `nm_id`, article, review count.
- `GET /api/seo/products/{nm_id}/readiness`
  - Returns product card, AI vision status, category query data status, expressive prior status, and previous query-set summary.

### 7.3. Query Selection

- `POST /api/seo/products/{nm_id}/query-selection/runs`
  - Creates a run from operator brief and current readiness snapshot, calls the LLM service, persists full input/prompt/result/model/prompt_version.
- `GET /api/seo/products/{nm_id}/query-selection/runs/{run_id}`
  - Returns run status, parsed candidates, and reproducibility metadata.
- `PATCH /api/seo/products/{nm_id}/query-selection/runs/{run_id}/candidates/{candidate_id}`
  - Saves approve/reject decision.
- `POST /api/seo/products/{nm_id}/query-selection/runs/{run_id}/approve`
  - Creates or updates the approved production query set for the SKU.

### 7.4. Generation Gate

- Generation endpoints should require an approved query set for production generation.
- Preview/debug generation may remain available only when clearly marked as preview and not treated as production output.

---

## 8. Frontend Screen Plan

Implementation should reorganize existing surfaces into the operator path:

1. Category query data page:
   - Multi-file upload.
   - Import/processing status.
   - "Build clusters" button.
   - Query and cluster counts.
   - Cluster list and expandable cluster detail.

2. Product list page:
   - Category filter.
   - Stock filter.
   - Table with required product columns.

3. Product page:
   - SKU evidence block: photo, title, characteristics, description.
   - AI vision block.
   - Existing approved query-set block, if present.
   - Query-selection readiness block.
   - "Select queries" button gated by readiness.

4. Query selection panel/page:
   - Operator brief form.
   - Run button.
   - Run status/errors.
   - Candidate review table.
   - Final "Approve query set" action.

5. Generation entry point:
   - Show approved query set as the production input.
   - Block production generation when the query set is not approved.

Keep debug views available separately; do not make matcher traces or raw JSON the primary operator path.

---

## 9. Implementation Steps

### Step 1. Category Query Data Readiness

Add backend status summaries and frontend category query data screen for import state, processed query count, cluster count, expressive prior status, and cluster inspection.

### Step 2. Explicit Cluster Build Action

Separate upload/import from clustering. Add operator action, status polling, and failure display.

### Step 3. Product List and Product Readiness

Add/adjust product list filters and columns. Add product readiness endpoint/page block for AI vision and category query data.

### Step 4. Query Selection Run Persistence

Add minimal persistence for query-selection runs, including operator brief JSON and reproducibility fields: input, prompt, result, model, prompt_version.

### Step 5. Production LLM Query Selection Service

Build candidate input from product card, constrained characteristics, AI vision, category expressive prior, query candidates from clusters, and operator brief. Call LLM through the controlled SEO LLM client path. Parse only `selected_queries` and `operator_candidates`.

### Step 6. Operator Review

Add candidate review API and UI table with approve/reject decisions, status, risk, and explanation.

### Step 7. Approved Query Set Finalization

Finalize approved candidates into the existing query-set storage or a compatible minimal extension. Mark the set as the production result for the SKU.

### Step 8. Generation Gate

Require approved query set for production generation. Keep preview/debug behavior clearly separated.

### Step 9. End-to-End Operator Smoke

Run one category and one SKU through the full flow: upload/import, cluster build, readiness, brief, LLM selection, review, approval, generation eligibility.

---

## 10. Acceptance Criteria / DoD per Step

### Step 1 DoD

- Category status endpoint returns query count, processed count, cluster count, expressive prior status, and readiness booleans.
- Category UI shows status and counts without requiring debug pages.
- Cluster list/detail is reachable from category screen.

### Step 2 DoD

- Upload accepts multiple files.
- Clustering is not started implicitly by upload.
- Operator can start clustering explicitly.
- UI shows clustering running/succeeded/failed states.

### Step 3 DoD

- Product list supports category and stock filters.
- Product table shows photo, name, category, `nm_id`, article, and review count.
- Product page shows required evidence and existing query selection result, if present.
- "Select queries" is disabled until AI vision and category query data are ready.

### Step 4 DoD

- A query-selection run can be persisted with brief JSON.
- Run stores input snapshot, prompt/prompt payload, result, model, and prompt_version.
- Failed runs store an error payload.
- No heavy separate brief-versioning subsystem is introduced.

### Step 5 DoD

- LLM input includes product card, constrained characteristics, AI vision, category expressive prior, clustered query candidates, and operator brief.
- LLM output parser accepts `selected_queries` and `operator_candidates`.
- Each candidate has query, status, risk, and explanation.
- No `rejected` output class is required or stored as LLM output.
- No orders/conversion fields are used for scoring or labels.

### Step 6 DoD

- Operator can approve or reject each returned candidate.
- Candidate table includes query, frequency, cluster, meaning line, candidate type, status, risk, explanation, and decision.
- Review decisions are persisted.

### Step 7 DoD

- Approved candidates can be finalized into a production query set.
- Approved query set is linked to project, category, SKU, source run, and approved items.
- Generation can identify the approved set for the SKU.
- Unapproved candidate sets cannot be treated as production results.

### Step 8 DoD

- Production generation path refuses to run without an approved query set.
- Preview/debug generation remains visibly marked as preview when available.
- Existing generation code is adapted minimally.

### Step 9 DoD

- One full operator flow completes in a local environment.
- Run reproducibility metadata is visible or retrievable.
- The approved query set is visible on the product page.
- The production generation gate sees the approved query set.

---

## 11. Explicit Non-Goals

- Do not implement code in Step 0.
- Do not add migrations in Step 0.
- Do not replace the product workflow with matcher-v2 as the primary production selection mechanism.
- Do not create a heavy versioned operator brief model now.
- Do not use category-level `orders` or `conversion` for scoring, candidate labels, or ranking.
- Do not add category-specific Python literals.
- Do not make LLM output directly production-approved.
- Do not return or persist an LLM `rejected` list as a first-class output.
- Do not remove human approval.
- Do not redesign the whole SEO module or rewrite existing import/clustering/generation systems.

---

## 12. Risks / Open Questions

Risks:

- Existing query-set tables may not exactly fit candidate review state; implementation should prefer a minimal compatible extension over a parallel query-set universe.
- Cluster labels/meaning lines may be incomplete for some categories; candidate UI needs graceful empty states.
- AI vision may be missing for many SKUs; readiness gating should make this visible rather than silently blocking.
- Category expressive prior readiness may not be represented by a single current endpoint yet.
- Prompt input can become too large if all cluster candidates are sent; implementation needs deterministic candidate preselection without category-specific literals or economic scoring.
- LLM output quality depends on prompt/version discipline; saving prompt_version/model/result is mandatory for reproducibility.

Open questions:

- What exact source should define "in stock" for the product list filter?
- Should query-selection runs be single active run per SKU or allow multiple historical runs with one approved set?
- Which existing `SeoSkuQuerySet` statuses map cleanly to draft/reviewed/approved?
- What is the initial default desired query count when the operator leaves it blank?
- Should cluster build be synchronous job polling through current import status machinery or a separate job record?
- Which generation endpoint is the first production-gated consumer of approved query sets?
