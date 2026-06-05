# Dashboard V2 Current-Capability Spec

> Status: current-capability guardrail for the next Dashboard UI v2 implementation.
> Scope: `frontend/app/app/project/[projectId]/dashboard/page.tsx` and dashboard UI v2 planning.
> Version: v1 (2026-05-14).

## 1. Scope

Dashboard v2 must use only real existing product/API capabilities. The Project Overview design mockup is visual direction, not functional truth.

This is not an SEO module task. Dashboard v2 may link to SEO as navigation, but must not claim SEO queue, SEO work-item status, or SEO production state unless a real dashboard-level SEO data contract exists.

Current verified dashboard-facing sources are:

- project name from `GET /api/v1/projects/:projectId`;
- connected marketplaces from `GET /api/v1/projects/:projectId/marketplaces`;
- dashboard KPI counts and snapshot timestamps from `GET /api/v1/dashboard/projects/:projectId/kpis`;
- WB price-discrepancy count from `GET /api/v1/projects/:projectId/wildberries/price-discrepancies?only_below_rrp=true&page_size=1`;
- latest WB finance report metadata from `GET /api/v1/projects/:projectId/marketplaces/wildberries/finances/reports/latest`.

## 2. Explicit Non-Goals For Current Implementation

- Do not implement the "Требует внимания / Сигналы" block now: there is no unified signals backend/data contract.
- Do not implement the "В работе / Гипотезы" live block now: there is no dashboard aggregate for hypotheses.
- Do not implement "Цели" now: there is no goals model/API.
- Do not render Ozon/YM pulse sections unless the marketplace is connected and a real data source exists.
- Do not mock revenue/orders/conversion/cards/stage metrics.

## 3. Implement-Now Candidates

- Project header with the real project name from `GET /api/v1/projects/:projectId`.
- Connected marketplace chips from existing project marketplaces data from `GET /api/v1/projects/:projectId/marketplaces`.
- WB-only "Пульс проекта" if the current dashboard/API exposes enough real WB data for each displayed metric.
- Each metric must include its real period/source: latest stock snapshot, latest storefront snapshot, latest RRP snapshot, latest report period, and so on.
- If the period is not truly 7 days, do not label it "7 дней".

Current WB pulse candidates are counts/statuses, not sales-performance KPIs:

- WB catalog products: `kpis.wb.products_total`.
- Storefront products and expected storefront products: `kpis.storefront.*`, source period is `kpis.last_snapshots.storefront_at`.
- FBS/FBO products in stock: `kpis.stock.*`, source periods are `kpis.last_snapshots.fbs_stock_at` and `kpis.last_snapshots.fbo_stock_at`.
- WB prices loaded: `kpis.prices.wb_prices_products`, source period is `kpis.last_snapshots.wb_prices_at`.
- RRP XML coverage: `kpis.rrp_xml.*`, source period is `kpis.last_snapshots.rrp_at`.
- Internal data availability, if present: `kpis.internal_data.*`, source period is `kpis.last_snapshots.internal_data_at`.
- Price discrepancies below RRP: total count from the existing price-discrepancy endpoint, with no implied time period unless the endpoint supplies one.
- Latest WB finance report link/status: latest `report_id`, `period_from`, and `period_to`; this is report metadata, not dashboard revenue/order summary.

## 4. Block Decision Table

| Mockup block | Current real data/API status | Decision | Allowed source/API | Notes |
| --- | --- | --- | --- | --- |
| Требует внимания | Partial module-level signals exist as destinations, but no unified dashboard signals contract or cross-module attention feed is present. | Do not implement as live block. | None for dashboard live status. Navigation link to `/wildberries/funnel-signals` is allowed if clearly navigational. | Do not synthesize alerts from unrelated counts. |
| Пульс проекта | Real WB operational counts and timestamps exist; sales pulse metrics from the mockup do not. | Implement WB-only pulse with truthful available metrics. | `GET /api/v1/dashboard/projects/:projectId/kpis`; optionally latest WB finance report metadata. | Label every metric by its real source/snapshot. |
| WB metrics: revenue | Latest finance report has `total_amount` metadata in `WBFinanceReportLatest`, but current dashboard page only uses report id/period and there is no dashboard aggregate period contract. | Do not render revenue KPI now. | Future backend-approved dashboard contract, or explicitly scoped finance report card. | Do not label as 7-day revenue unless the API guarantees that exact period. |
| WB metrics: orders | No current dashboard/API field for WB order count. | Do not implement. | None. | No mock order counts. |
| WB metrics: conversion | No current dashboard/API field for conversion. Funnel signals page may exist, but no dashboard aggregate conversion source is present. | Do not implement. | None for dashboard live metric. | A navigational link to funnel signals is allowed. |
| WB cards/stages | Current KPI API exposes product, storefront, stock, price, RRP, and internal-data counts; it does not expose pipeline stages matching the mockup. | Implement only truthful count cards if needed; do not present mockup stages. | `GET /api/v1/dashboard/projects/:projectId/kpis`. | Use source labels such as latest snapshot timestamps. |
| Ozon/YM pulse | Marketplace connection data can show whether non-WB marketplaces are enabled, but there is no current dashboard pulse data source for Ozon/YM. | Do not render live Ozon/YM pulse sections. | `GET /api/v1/projects/:projectId/marketplaces` for chips/visibility only. | Future/unavailable placeholders must not look like live data. |
| В работе / Гипотезы | Hypothesis destinations and APIs exist elsewhere, but no dashboard aggregate for active work/hypotheses is used by the current dashboard. | Do not implement as live aggregate. | Navigation link to `/wildberries/hypothesis-lab/experiments` only. | Do not claim counts, status, progress, or impact. |
| SEO queue/work item | SEO module has its own routes/APIs, but this task is not SEO and there is no dashboard-level SEO queue contract in current dashboard. | Do not implement status block. | Navigation link to `/seo` only. | Avoid reading or depending on SEO phase docs for this dashboard spec. |
| Last action | No current dashboard/API field for a unified last action across modules. | Do not implement. | None. | Snapshot timestamps may be shown per metric, but not collapsed into a product-level last-action claim. |
| Goals | No goals model/API is present for dashboard. | Do not implement. | None. | No fake targets, progress bars, or completion states. |

## 5. Rules For Next Implementation

- If data source is absent or ambiguous, omit the block.
- Disabled/future blocks are allowed only if explicitly marked as unavailable and not styled as live data.
- Prefer a smaller dashboard with truthful data over a full mockup with fake data.
- Dashboard v2 implementation must not change backend/API contracts unless a separate backend task is approved.
- Connected marketplace UI must use the project marketplace connection list. Ozon/YM should not appear as live pulse sections without a connected marketplace and a real data source.
- WB metrics must be gated by the existing WB connection check.
- Module links are allowed when they are clearly navigational and not presented as status claims.

## 6. Next Recommended Implementation

Build a "Dashboard v2 current-capability" page with:

- header using the real project name;
- connected marketplace chips from existing marketplace data;
- WB-only "Пульс проекта" built from current KPI counts and source timestamps;
- no attention block;
- no goals;
- no hypotheses live aggregate;
- optional links to modules if they are navigational only, not status claims.

Recommended WB pulse content:

- catalog/storefront coverage;
- FBS/FBO in-stock counts;
- WB prices loaded;
- RRP XML coverage;
- internal-data coverage when available;
- price-discrepancy count as a link to the existing report, without inventing a period;
- latest WB finance report link/status with its actual report period, without converting it into revenue/orders/conversion cards.
