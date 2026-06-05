# Navigation V2 Contract

> Status: approved UI v2 navigation contract.
> Version: v1 (2026-05-14).
> Scope: `frontend/components/ui-v2/*` and project routes rendered with `?ui=v2`.

This document fixes the current Rail/SubNav structure for UI v2. Visual dimensions and component styling stay in `docs/design-system/specs/ecomcore-navb-compact-spec.md`; this file defines route ownership, menu behavior, connected marketplace rules, and future/disabled items.

## Rail Items

Rail items are route-owned. Active state is computed from the current pathname only; opening a subnav must not make the rail item active by itself.

| Rail id | Label | Route ownership | Behavior |
| --- | --- | --- | --- |
| `overview` | Обзор | `/app/project/:projectId/dashboard` | Direct link to dashboard. |
| `wb` | WB | WB-owned routes under `/wildberries`, except routes owned by Modules, Compare, Signals, or Expenses | Opens WB SubNav immediately. |
| `ozon` | Ozon | Future `/app/project/:projectId/ozon/*` routes | Hidden unless Ozon is connected. Opens Ozon SubNav when visible. |
| `modules` | Модули | `/seo/*` and `/wildberries/hypothesis-lab/*` | Opens Modules SubNav immediately. |
| `compare` | Сравн. | `/wildberries/price-discrepancies/*` | Direct link to the comparison report. |
| `inbox` | Сигналы | `/wildberries/funnel-signals/*` | Direct link to funnel signals. |
| `expenses` | Расходы | `/additional-costs/*`, `/cogs/*`, `/wildberries/finances/*` | Direct link to additional costs. |
| `settings` | Настр. | `/settings/*`, `/members/*`, `/marketplaces/*` | Opens Settings SubNav immediately. |

## Subnav WB

WB SubNav contains WB report and data destinations. Enabled links must point to final routes, not redirect-wrapper pages.

Enabled:

- `price-discrepancies`: `/app/project/:projectId/wildberries/price-discrepancies`
- `without-photos`: `/app/project/:projectId/wildberries/stock-without-photos`
- `unit-pnl`: `/app/project/:projectId/wildberries/finances/unit-pnl`
- `funnel`: `/app/project/:projectId/wildberries/funnel-signals`
- `reviews`: `/app/project/:projectId/wildberries/reviews`

Disabled/future:

- `geo-sales`
- `spp-dynamics`
- `catalog`
- `prices`
- `stocks`

## Subnav Modules

Modules SubNav owns cross-cutting product modules, including modules that currently live below a marketplace route for historical reasons.

Enabled:

- `seo`: `/app/project/:projectId/seo`
- `hypotheses`: `/app/project/:projectId/wildberries/hypothesis-lab/experiments`

Disabled/future:

- `tests`
- `supplies`
- `design`

`/app/project/:projectId/wildberries/hypothesis-lab` is a redirect-wrapper route and must not be used as a menu target.

## Subnav Settings

Settings SubNav owns project configuration, users, and marketplace connection screens.

Enabled:

- `project-settings`: `/app/project/:projectId/settings`
- `members`: `/app/project/:projectId/members`
- `marketplaces`: `/app/project/:projectId/marketplaces`

`/marketplaces/*` belongs to Settings for active-state purposes. Ozon must not become active on `/marketplaces`.

## Connected Marketplaces

Rail marketplace items use the project marketplace connection list from `/api/v1/projects/:projectId/marketplaces`.

- A marketplace rail item is visible only when its `marketplace_code` is enabled for the current project.
- WB uses `marketplace_code = wildberries`.
- Ozon uses `marketplace_code = ozon`.
- Ozon stays hidden when Ozon is not connected.
- If the marketplace list fails to load, marketplace rail items are treated as not connected for this render.

## Interaction Rules

- Rail items with SubNav (`wb`, `ozon`, `modules`, `settings`) open the SubNav immediately on click.
- Opening a SubNav does not require navigating to a heavy section landing page.
- If the current route already belongs to that rail section, clicking the rail item must not trigger a redundant navigation.
- SubNav links perform the real navigation to final destination routes.
- Direct Rail items without SubNav navigate normally.

## Active State Checks

- WB active only for WB-owned routes that are not owned by Modules, Compare, Signals, or Expenses.
- Modules active for `/seo/*` and `/wildberries/hypothesis-lab/*`.
- Settings active for `/settings/*`, `/members/*`, and `/marketplaces/*`.
- Ozon is hidden unless connected and does not own `/marketplaces/*`.
