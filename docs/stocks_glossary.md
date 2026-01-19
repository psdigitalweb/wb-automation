### Stocks glossary (FBS / FBO)

We use two different stock concepts and **name them explicitly** to avoid ambiguity.

#### FBS stock

**Definition**: “available to sell on WB by FBS” — quantity that **we (merchant)** transferred to WB as availability for FBS orders (goods are physically at the seller).

**Backend source**:
- table: `stock_snapshots`
- key: `(project_id, nm_id)`
- quantity: `SUM(quantity)` in the **latest snapshot_at run** per project

**UI naming**: “FBS”

#### FBO stock

**Definition**: “on WB warehouses (FBO)” — supplier stock for goods we shipped to WB warehouses.

**Backend source**:
- table: `supplier_stock_snapshots`
- key: `nm_id` (no project_id in the table, project-scoping is derived by joining `products` on `(project_id, nm_id)`)
- quantity: sum of latest row per `(nm_id, warehouse_name)` (latest by `COALESCE(last_change_date, snapshot_at)`), then aggregated per `nm_id`

**UI naming**: “FBO”

#### Articles Base fields

`GET /api/v1/projects/{project_id}/articles-base` returns:
- `fbs_stock_qty`, `fbs_stock_updated_at`, `has_fbs_stock`
- `fbo_stock_qty`, `fbo_stock_updated_at`, `has_fbo_stock`

Old fields like `stock_wb` / `"Остаток WB"` may exist as **deprecated aliases** and should not be used by new UI.

