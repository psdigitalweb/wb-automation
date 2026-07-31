# EcomCore Nav B Compact Spec

Source of truth: `Nav B - Rail _ sub-nav _standalone_.html`.
This spec describes the applied visual contract, including the `ecomcore-ui-overrides` layer.

## Tokens

```json
{
  "tokens": {
    "colors": {
      "bg": "oklch(98.5% 0.006 250)",
      "surface": "oklch(100% 0 0)",
      "surface2": "oklch(97% 0.008 250)",
      "surface3": "oklch(94% 0.012 250)",
      "border": "oklch(22% 0.03 260 / 0.15)",
      "borderStrong": "oklch(22% 0.03 260 / 0.15)",
      "text": "oklch(22% 0.03 260)",
      "text2": "oklch(42% 0.02 260)",
      "text3": "oklch(58% 0.015 260)",
      "textOnDark": "oklch(98% 0.005 250)",
      "accent": "oklch(38% 0.10 155)",
      "accentHover": "oklch(32% 0.11 155)",
      "accentSoft": "oklch(95% 0.04 155)",
      "accentText": "oklch(36% 0.11 155)",
      "info": "oklch(52% 0.18 245)",
      "infoBg": "oklch(95% 0.04 245)",
      "success": "oklch(56% 0.15 158)",
      "successBg": "oklch(95% 0.05 158)",
      "warning": "oklch(68% 0.16 70)",
      "warningBg": "oklch(96% 0.06 75)",
      "danger": "oklch(56% 0.20 22)",
      "dangerBg": "oklch(96% 0.04 22)",
      "mpWb": "oklch(58% 0.16 330)",
      "mpWbBg": "oklch(96% 0.025 330)",
      "mpOzon": "oklch(45% 0.14 250)",
      "mpOzonBg": "oklch(96% 0.025 250)",
      "mpYm": "oklch(45% 0.14 60)",
      "mpYmBg": "oklch(96% 0.025 60)"
    },
    "fonts": {
      "sans": "\"Geist\", \"Inter\", ui-sans-serif, system-ui, -apple-system, sans-serif",
      "mono": "\"Geist Mono\", ui-monospace, \"JetBrains Mono\", \"SFMono-Regular\", monospace",
      "features": "\"cv11\", \"ss01\", \"ss03\"",
      "numeric": "tabular-nums"
    },
    "text": {
      "xs": "11px",
      "sm": "12px",
      "base": "13px",
      "md": "14px",
      "lg": "16px",
      "xl": "20px",
      "2xl": "24px",
      "3xl": "32px",
      "4xl": "44px"
    },
    "lineHeight": {
      "tight": 1.15,
      "snug": 1.3,
      "base": 1.5
    },
    "fontWeight": {
      "regular": 400,
      "medium": 500,
      "semibold": 600,
      "bold": 700
    },
    "space": {
      "0": "0",
      "1": "4px",
      "2": "8px",
      "3": "12px",
      "4": "16px",
      "5": "20px",
      "6": "24px",
      "8": "32px",
      "10": "40px",
      "12": "48px",
      "16": "64px"
    },
    "radius": {
      "xs": "4px",
      "sm": "6px",
      "md": "8px",
      "lg": "10px",
      "xl": "14px",
      "pill": "999px"
    },
    "shadow": {
      "xs": "0 1px 0 0 oklch(20% 0.01 75 / 0.04)",
      "sm": "0 1px 2px oklch(20% 0.01 75 / 0.05), 0 1px 0 oklch(20% 0.01 75 / 0.03)",
      "md": "0 4px 12px oklch(20% 0.01 75 / 0.06), 0 1px 0 oklch(20% 0.01 75 / 0.04)",
      "lg": "0 12px 32px oklch(20% 0.01 75 / 0.08), 0 1px 0 oklch(20% 0.01 75 / 0.04)",
      "focus": "0 0 0 3px oklch(38% 0.10 155 / 0.22)"
    },
    "motion": {
      "easeOut": "cubic-bezier(0.2, 0.8, 0.2, 1)",
      "easeInOut": "cubic-bezier(0.4, 0, 0.2, 1)",
      "fast": "120ms",
      "base": "180ms",
      "slow": "280ms"
    },
    "density": {
      "default": { "rowH": "40px", "controlH": "32px", "controlPx": "10px", "cardPad": "20px", "textBase": "13px" },
      "compact": { "rowH": "32px", "controlH": "28px", "controlPx": "8px", "cardPad": "16px", "textBase": "12px" },
      "comfortable": { "rowH": "48px", "controlH": "36px", "controlPx": "12px", "cardPad": "24px", "textBase": "14px" }
    },
    "layout": {
      "shellSidebarW": "232px",
      "shellSidebarCollapsedW": "56px",
      "shellTopbarH": "52px",
      "shellSubbarH": "44px",
      "navBRailW": "76px",
      "navBRailItemW": "64px",
      "navBRailItemH": "56px",
      "navBSubnavW": "220px",
      "contentPadding": "16px 20px",
      "borderWidth": "0.5px"
    }
  }
}
```

## Shell Dimensions And Navigation States

### Nav B Shell

- Root layout: `display: flex; height: 100%; background: var(--color-bg)`.
- Rail column: `width: 76px; flex-shrink: 0; background: var(--color-surface)`.
- Rail right border when subnav exists: `0.5px solid var(--color-border)`.
- Outer nav border: `0.5px solid var(--color-border)`.
- Logo area: `height: 52px`, centered.
- Logo mark: `32x32`, `border-radius: 8px`, `background: var(--color-accent-soft)`, `color: var(--color-accent-text)`, `font-size: 14px`, `font-weight: 700`.
- Rail nav top padding: `8px`.
- Rail divider: `height: 0.5px`, `margin: 8px 14px`, `background: var(--color-border)`.
- Subnav panel: animated `width: 0 -> 220px`, `opacity: 0 -> 1`, `transition: width 150ms var(--ease-out), opacity 120ms var(--ease-out)`.
- Subnav content: `padding: 16px 8px 8px`, `gap: 1px`, scrollable.
- Main content in report screens: `padding: 16px 20px`.

### RailItem Active State

- Item size: `64x56`.
- Margin: `2px 6px`.
- Layout: vertical flex, center, `gap: 4px`.
- Radius: `10px`.
- Icon: `18px`.
- Label: `font-size: 9px`, `font-weight: 600`, `letter-spacing: 0.02em`.
- Default: `color: var(--color-text-2)`, `background: transparent`.
- Active: `color: var(--color-accent-text)`, `background: var(--color-accent-soft)`, `box-shadow: inset 0 0 0 0.5px var(--color-border)`.
- Indicator dot: `7x7`, `top: 8px`, `right: 12px`, `box-shadow: 0 0 0 2px var(--color-surface)`.
- Indicator green: `var(--color-success)`.
- Indicator purple: `oklch(58% 0.16 305)`.
- Badge dot: same geometry, `background: var(--color-danger)`.

### SubNavItem Active State

- Item height: `32px`.
- Padding: `0 10px`.
- Gap: `10px`.
- Radius: `6px`.
- Icon: `16px`.
- Text: `13px`.
- Default: `color: var(--color-text-2)`, `background: transparent`, `font-weight: 400`.
- Hover: `background: var(--color-surface-2)`.
- Active: `color: var(--color-accent-text)`, `background: var(--color-accent-soft)`, `font-weight: 600`, `box-shadow: inset 2px 0 0 var(--color-accent)`.
- Badge: mono `10px`, `font-weight: 600`, pill, `min-width: 18px`.

## Components

### AppShell

Props:

```ts
type AppShellProps = {
  variant?: "sidebar" | "topbar" | "hybrid";
  project: Project;
  screen: string;
  density: "compact" | "default" | "comfortable";
  onDensity: (density: string) => void;
  theme: "light" | "dark";
  onTheme: () => void;
  children: React.ReactNode;
};
```

Key CSS:

- Shell fills viewport: `height: 100%`.
- Background: `var(--color-bg)`.
- For Nav B use dedicated rail + subnav layout, not the generic `sidebar` variant.
- All shell borders use the override value: `0.5px solid var(--color-border)`.

### RailNav

Props:

```ts
type RailNavProps = {
  activePrimary: "overview" | "wb" | "ozon" | "modules" | "compare" | "inbox" | "expenses" | "settings";
  onPrimaryChange: (id: string) => void;
  items: Array<RailItemConfig | { divider: true }>;
};
```

Key CSS:

- Width: `76px`.
- Background: `var(--color-surface)`.
- Right border: `0.5px solid var(--color-border)` if a subnav is open.
- Logo area height: `52px`.
- Nav list top padding: `8px`.
- Dividers between zones.

### RailItem

Props:

```ts
type RailItemProps = {
  id: string;
  icon: IconName;
  label: string;
  active?: boolean;
  indicator?: "green" | "purple";
  badge?: boolean;
  onClick?: () => void;
};
```

Key CSS:

- `width: 64px`, `height: 56px`, `margin: 2px 6px`.
- Icon `18px`.
- Label `9px / 600 / 0.02em`.
- Active state exactly as described in "RailItem Active State".

### SubNav

Props:

```ts
type SubNavProps = {
  visible: boolean;
  kind: "marketplace" | "modules" | "settings";
  activeId: string;
  groups?: SubNavGroup[];
  children?: React.ReactNode;
};
```

Key CSS:

- Width: `220px` when visible, `0` when hidden.
- `overflow: hidden`.
- `transition: width 150ms var(--ease-out), opacity 120ms var(--ease-out)`.
- Inner nav: `padding: 16px 8px 8px`, `gap: 1px`.
- Panel starts directly with group label or segmented switch; no panel title/header block.

### SubNavItem

Props:

```ts
type SubNavItemProps = {
  id: string;
  label: string;
  icon: IconName;
  active?: boolean;
  badge?: number | string;
  badgeTone?: "danger" | "warning" | "info" | "neutral";
  onClick?: () => void;
};
```

Key CSS:

- Same as `NavItem` non-horizontal: height `32px`, radius `6px`, icon `16px`, text `13px`.
- Active: `accentSoft` background, `accentText` text, `inset 2px 0 0 var(--color-accent)`.

### Topbar

Props:

```ts
type TopbarProps = {
  project?: Project;
  breadcrumbs?: BreadcrumbItem[];
  actions?: React.ReactNode;
  user?: { name: string; email?: string; avatar?: string };
};
```

Key CSS:

- Height: `52px`.
- Background: `var(--color-surface)`.
- Bottom border: `0.5px solid var(--color-border)`.
- Padding: `0 20px`.
- Right action icon buttons: `.btn.btn-ghost.btn-sm.btn-icon`.
- User cluster: rounded pill, surface-2 background, avatar `22-24px`.

### Breadcrumbs

Props:

```ts
type BreadcrumbsProps = {
  items: Array<{ label: string; href?: string }>;
};
```

Key CSS:

- `display: flex`, `align-items: center`, `gap: 6px`.
- Font: `12px`.
- Non-current: `var(--color-text-2)`.
- Current: `var(--color-text)`.
- Separator: chevron-right icon `12px`, `var(--color-text-3)`.

### PageHeader

Props:

```ts
type PageHeaderProps = {
  title: string;
  eyebrow?: string;
  subtitle?: string;
  marketplaceTag?: "wb" | "ozon" | "ya";
  actions?: React.ReactNode;
};
```

Key CSS:

- Container: flex row, `align-items: flex-end`, `justify-content: space-between`, `gap: 16px`, `margin-bottom: 16px`.
- Title: `22px`, `line-height: 1.1`, `font-weight: 600`, `letter-spacing: -0.02em`.
- Eyebrow: `10-11px`, uppercase, `letter-spacing: 0.08em`, `color: var(--color-text-3)`, `font-weight: 600`.
- Subtitle: `12px`, `color: var(--color-text-2)`, `margin-top: 4px`.

### FilterBar

Props:

```ts
type FilterBarProps = {
  search?: { value: string; placeholder: string; onChange: (v: string) => void };
  filters: Array<{ id: string; label: string; value?: string; icon?: IconName }>;
  sort?: React.ReactNode;
  columnPicker?: React.ReactNode;
  actions?: React.ReactNode;
};
```

Key CSS:

- Wrapper: `.card`, `padding: 12px`, `margin-bottom: 12px`.
- Layout: row flex, `gap: 8px`, `flex-wrap: wrap`.
- Search: `.input`, width around `280px`, inner icon `14px`.
- Filter buttons: `.btn.btn-secondary.btn-sm`, icons `10-12px`.
- Right side uses `.spacer`.
- Saved view / filter tabs above table are pill buttons: `border-radius: 20px`; active background `var(--color-accent-soft)`, text `var(--color-accent-text)`, no heavy border.

### MarketplaceSwitch

Props:

```ts
type MarketplaceSwitchProps = {
  value: "wb" | "ozon" | "ya";
  options: Array<"wb" | "ozon" | "ya">;
  onChange: (value: string) => void;
};
```

Key CSS:

- `.segmented`.
- Background: `var(--color-surface-2)`.
- Border: `0.5px solid var(--color-border)`.
- Radius: `6px`.
- Padding: `2px`.
- Button height: `24px` in compact usage; `font-size: 12px`.
- Active button: `background: var(--color-surface)`, `color: var(--color-text)`, `box-shadow: var(--shadow-xs)`.

### DataTable

Props:

```ts
type DataTableProps<Row> = {
  rows: Row[];
  columns: Array<{
    id: string;
    title: string;
    width?: number;
    minWidth?: number;
    numeric?: boolean;
    sticky?: "left" | "right";
    titleAttr?: string;
    render: (row: Row) => React.ReactNode;
  }>;
  selectedIds?: Set<string>;
  onRowClick?: (row: Row) => void;
  onSelectionChange?: (ids: Set<string>) => void;
  footer?: React.ReactNode;
  loading?: boolean;
  empty?: boolean;
  error?: string;
};
```

Key CSS:

- Wrapper: `.table-wrap`, `border: 0.5px solid var(--color-border)`, radius `10px`, background `surface`, `overflow-x: auto`.
- Table: `width: 100%` or `max-content` for wide reports; `border-collapse: separate`, `border-spacing: 0`.
- Headers: `font-size: 11px`, `font-weight: 500`, uppercase, `letter-spacing: 0.04em`, `color: text3`, `background: surface2`.
- Cells: `padding: 10px 14px`, `border-bottom: 0.5px solid var(--color-border)`.
- Row hover: `background: var(--color-surface-2)`.
- Numeric cells: `font-variant-numeric: tabular-nums`; use mono for SKU, prices, counters.
- Sticky columns: `position: sticky`, `background: surface`, `z-index: 3`; sticky header uses `surface2`, `z-index: 5`.

RRP report column widths:

```json
{
  "select": 44,
  "photo": 58,
  "sku": 110,
  "title": 430,
  "price": 90,
  "rrp": 90,
  "vitrina": 90,
  "discount": 84,
  "deltaRrp": 74,
  "recommendation": 104,
  "stock": 76,
  "actions": 32
}
```

Sticky left offsets for product table:

```json
{ "select": 0, "photo": 44, "sku": 102, "title": 212 }
```

### ProductRow

Props:

```ts
type ProductRowProps = {
  selected?: boolean;
  imageLabel: string;
  sku: string;
  nmId: string;
  title: string;
  category: string;
  cells?: React.ReactNode;
  onSelect?: () => void;
  onClick?: () => void;
};
```

Key CSS:

- Checkbox cell: width `44px`; checkbox `18x18`, radius `5px`, border `1.5px solid var(--color-border-strong)`.
- Thumbnail: `28x28` in dense report tables; placeholder uses `surface2`, border `0.5px`, radius `6px`, mono `9px`.
- SKU: mono `11px`, `font-weight: 500`, ellipsis.
- nmID: mono `10px`, `color: text3`.
- Title: `12px`, `line-height: 1.3`, ellipsis.
- Category: `10px`, `color: text3`.

### ProjectCard

Props:

```ts
type ProjectCardProps = {
  name: string;
  marketplaces: Array<"wb" | "ozon" | "ya">;
  metrics: Array<{ label: string; value: string | number; tone?: "neutral" | "warning" | "danger" | "success" }>;
  updatedAt: string;
  onClick?: () => void;
};
```

Key CSS:

- Uses `.card` base: `surface`, `0.5px solid border`, `radius-lg`, `shadow-sm`.
- Width: full within content column, usually max `900px` on project list.
- Padding: `18-20px` desktop; compact can use `16px`.
- Title: `16px`, `font-weight: 600`, `letter-spacing: -0.01em`.
- Marketplace badges use `MarketplaceTag` with short labels.
- Metric label: `11px`, `color: text3`.
- Metric value: `20px`, `font-weight: 600`, tabular nums.
- Hover: background moves toward `surface2` or subtle `accentSoft`, border `borderStrong`.

### MetricCard

Props:

```ts
type MetricCardProps = {
  label: string;
  value: string | number;
  hint?: string;
  delta?: number;
  deltaTone?: "success" | "danger" | "neutral";
  marketplace?: "wb" | "ozon" | "ya";
};
```

Key CSS:

- Background: `surface`.
- Border: `0.5px solid var(--color-border)`.
- Radius: `10px`.
- Padding: `12px` for compact dashboard cards, `20px` for larger KPI cards.
- Label: `11-12px`, `color: text2/text3`.
- Value: compact `22px / 600`; large KPI can use `26-32px`, mono for dense numeric dashboards.
- Delta: `12px`, mono/tabular, success or danger color.

## States

### Loading

Use for tables, cards, and page sections.

- Container keeps final size to prevent layout shift.
- Background: `var(--color-surface)`.
- Border: `0.5px solid var(--color-border)`.
- Skeleton line: `height: 10-12px`, radius `999px`, background `var(--color-surface-3)`.
- Skeleton row height matches density: `32px compact`, `40px default`.
- Optional shimmer: linear gradient from `surface-2` to `surface-3`, duration `1200ms`.
- Text alternative: muted `Загрузка...`, `font-size: 12px`, `color: text3`.

### Empty

Use when the request succeeded but there is no data.

- Same wrapper as `.card` or `.table-wrap`.
- Min height: `160-220px`.
- Centered column, `gap: 8px`.
- Icon: `32px`, `color: text3`.
- Title: `14px`, `font-weight: 600`, `color: text`.
- Description: `12px`, `color: text2`, max width `360px`.
- Optional action: secondary button, height `28px` or `32px`.

### Error

Use when data cannot load or an operation failed.

- Same wrapper as `.card`.
- Border: `0.5px solid var(--color-border)`; avoid bright full red borders.
- Background: `var(--color-surface)`.
- Status pill or inline badge: `badge-danger`.
- Icon/dot: `var(--color-danger)`.
- Title: `14px`, `font-weight: 600`.
- Message: `12px`, `color: text2`.
- Actions: `Повторить` primary or secondary; optional `Подробнее` ghost.

## Border Override Contract

Nav B applies a final override layer. Production components must encode this directly instead of relying on CSS overrides:

- All borders and dividers: `0.5px solid var(--color-border)`.
- `.table th`, `.table td`: `padding: 10px 14px`, bottom border `0.5px`.
- `.badge-danger`: pastel danger background + dark danger text.
- `.badge-success`: pastel success background + dark success text.
- Filter/saved-view pill active: soft accent fill; no bold heavy outline.

## Notes

- Do not recreate rail/subnav with approximate CSS. Use the exact `RailNav`, `RailItem`, `SubNav`, and `SubNavItem` contracts above.
- Page-level mockups must include the same shell contract before page content is judged visually.
- If a component is not in Nav B (for example `ProjectCard`), derive it from `.card`, `MarketplaceTag`, and `MetricCard` rather than inventing a new visual language.
