# Reviews source discovery (WB feedback snapshots)

Date: 2026-04-21

Goal: find the **source of reviews** and **source of titles** to build category-level expressive evaluation inputs.

Constraints:
- no LLM calls
- no query clusters / query data
- no semantic filtering
- titles only (no description/attributes)

## 1) Reviews source

### 1.1 DB table

Reviews are stored in PostgreSQL table:

- `wb_feedback_snapshots`

Migration (schema source of truth):
- `alembic/versions/20260219_add_wb_communications_tables.py`
- `alembic/versions/add_wb_feedback_snapshots_cols.py`

### 1.2 Key columns

From migrations:

- `project_id` (FK → `projects.id`)
- `nm_id` (WB SKU / product identifier; bigint; nullable in schema but used when present)
- `external_id` (unique per project)
- `product_valuation` (rating; smallint; nullable)
- `created_date` (review creation time)
- `raw` (`JSONB`) — contains the actual review text fields

Additional columns (added later):
- `is_archived` (bool; nullable)
- `source_endpoint` (text; nullable)
- `last_seen_at` (timestamptz; nullable)

### 1.3 Text fields in `raw`

Existing runtime exporter reads these keys from `raw`:

- `raw.userName`
- `raw.text`
- `raw.pros`
- `raw.cons`

Reference implementation:
- `scripts/export_in_stock_product_reviews.py`
  - `_review_from_row()`

### 1.4 Link to category / SKU

SKU linkage:
- `wb_feedback_snapshots.nm_id` ↔ `products.nm_id`
- scope: `project_id`

Category linkage:
- via `products.subject_id` (WB category id / subject id)
- and `products.subject_name` (human-readable category name)

Practical join pattern (as used in exporter / SQL):
- join on `(project_id, nm_id)` between `products` and `wb_feedback_snapshots`

## 2) Titles source

Titles are taken from the DB table:

- `products`

Relevant columns used in this task:
- `products.title` (text)
- `products.subject_id` (category id)
- `products.subject_name` (category name)
- `products.project_id`
- `products.nm_id`

Evidence for `title` and `subject_name/subject_id/project_id` existence:
- `alembic/versions/e1dcde5e611e_add_brand_to_products.py` (adds `title`, `subject_name`, etc.)
- `alembic/versions/add_product_details_fields.py` (adds `subject_id`)
- `alembic/versions/71fcc51a5119_repair_schema_idempotency.py` (ensures `project_id` exists)

## 3) Summary

- Reviews: `wb_feedback_snapshots` (`product_valuation`, `raw.text/pros/cons`, linked to SKU by `nm_id` and to category by join with `products.subject_id`).
- Titles: `products.title` for SKUs in the selected preview scope.

