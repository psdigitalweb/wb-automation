### Key matching (Articles Base)

This project merges data from multiple sources using a small set of **stable keys**.

#### Normalization: `vendor_code_norm`

We normalize vendor codes to make cross-source joins stable:

- **Rule**: take the last non-empty segment after `/` and trim `/` and whitespace.
  - `"560/ZKPY-1138"` → `"ZKPY-1138"`
  - `"4003/"` → `"4003"`
  - `"  /ABC/  "` → `"ABC"`

In DB, `products.vendor_code_norm` is a **generated stored column** so it can be indexed.

#### Primary identity: `nm_id`

`nm_id` is the WB product id and is the primary join key for WB-origin data.

- **WB API prices** (`price_snapshots`): join by `(project_id, nm_id)`
- **WB stocks** (`stock_snapshots`): join by `(project_id, nm_id)`
- **Frontend catalog prices** (`frontend_catalog_price_snapshots`): join by `nm_id` and the project’s WB `brand_id`

#### 1C / RRP XML: `vendor_code_norm`

RRP snapshots (`rrp_snapshots`) are keyed by:

- `(project_id, vendor_code_norm)`

We pick the latest XML run by `MAX(snapshot_at)` per project.

#### Barcode: best-effort

Barcode is not consistently present everywhere. Current strategy:

- take the latest `supplier_stock_snapshots` row per `nm_id` and use its `barcode`

#### Articles Base endpoint

`GET /api/v1/projects/{project_id}/articles-base` uses a **two-phase query**:

1) Page selection (LIMIT/OFFSET) over `products` + latest (rrp, stock) to keep it fast.
2) Join “heavy” sources (prices, frontend, supplier) only for the selected page keys.

