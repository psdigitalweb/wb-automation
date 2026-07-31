import { useState } from "react";

/* ═══════════════════════════════════════════════════════════
   ECOMCORE DESIGN SYSTEM v1.1 — Nav B Source of Truth
   
   Exports: T (tokens), AppShell, RailNav, RailItem, RailDivider,
   SubNav, SubNavItem, Topbar, ContentArea, Breadcrumbs, PageHeader,
   FilterBar, DataTable, ProductRow, MetricCard, ProjectCard,
   MarketplaceSwitch, Badge, Btn, Icon,
   LoadingState, EmptyState, ErrorState
   ═══════════════════════════════════════════════════════════ */

// ─── TOKENS ───
export const T = {
  color: {
    bg: "oklch(98.5% 0.006 250)",
    surface: "oklch(100% 0 0)",
    surface2: "oklch(97% 0.008 250)",
    surface3: "oklch(94% 0.012 250)",
    border: "oklch(22% 0.03 260 / 0.15)",
    text: "oklch(22% 0.03 260)",
    text2: "oklch(42% 0.02 260)",
    text3: "oklch(58% 0.015 260)",
    textOnDark: "oklch(98% 0.005 250)",
    accent: "oklch(38% 0.10 155)",
    accentHover: "oklch(32% 0.11 155)",
    accentSoft: "oklch(95% 0.04 155)",
    accentText: "oklch(36% 0.11 155)",
    info: "oklch(52% 0.18 245)", infoBg: "oklch(95% 0.04 245)",
    success: "oklch(56% 0.15 158)", successBg: "oklch(95% 0.05 158)",
    warning: "oklch(68% 0.16 70)", warningBg: "oklch(96% 0.06 75)",
    danger: "oklch(56% 0.20 22)", dangerBg: "oklch(96% 0.04 22)",
    mpWb: "oklch(58% 0.16 330)", mpWbBg: "oklch(96% 0.025 330)",
    mpOzon: "oklch(45% 0.14 250)", mpOzonBg: "oklch(96% 0.025 250)",
    mpYm: "oklch(45% 0.14 60)", mpYmBg: "oklch(96% 0.025 60)",
  },
  font: {
    sans: '"Geist","Inter",ui-sans-serif,system-ui,-apple-system,sans-serif',
    mono: '"Geist Mono",ui-monospace,"JetBrains Mono",monospace',
  },
  text: { xs: 11, sm: 12, base: 13, md: 14, lg: 16, xl: 20, "2xl": 24, "3xl": 32, "4xl": 44 },
  weight: { regular: 400, medium: 500, semibold: 600, bold: 700 },
  leading: { tight: 1.15, snug: 1.3, base: 1.5 },
  sp: (n) => n * 4,
  radius: { xs: 4, sm: 6, md: 8, lg: 10, xl: 14, pill: 999 },
  shadow: {
    xs: "0 1px 0 0 oklch(20% 0.01 75 / 0.04)",
    sm: "0 1px 2px oklch(20% 0.01 75 / 0.05),0 1px 0 oklch(20% 0.01 75 / 0.03)",
    md: "0 4px 12px oklch(20% 0.01 75 / 0.06),0 1px 0 oklch(20% 0.01 75 / 0.04)",
    focus: "0 0 0 3px oklch(38% 0.10 155 / 0.22)",
  },
  layout: { railW: 76, railItemW: 64, railItemH: 56, subnavW: 220, topbarH: 52 },
  ease: "cubic-bezier(0.2,0.8,0.2,1)",
};

const bdr = `0.5px solid ${T.color.border}`;
const bs = { fontFamily: T.font.sans, WebkitFontSmoothing: "antialiased", fontFeatureSettings: '"cv11","ss01","ss03"' };

// ─── ICONS ───
const iconPaths = {
  layout: <><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></>,
  home: <><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1z"/><path d="M9 21V12h6v9"/></>,
  box: <><path d="M21 8L12 2 3 8v8l9 6 9-6z"/><path d="M12 22V12M21 8l-9 4-9-4"/></>,
  chart: <><rect x="3" y="10" width="4" height="11" rx="1"/><rect x="10" y="3" width="4" height="18" rx="1"/><rect x="17" y="7" width="4" height="14" rx="1"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-2.82 1.18V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1.08-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 003 15.4V14a2 2 0 014 0"/></>,
  bell: <><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></>,
  search: <><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></>,
  filter: <><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></>,
  chevRight: <><polyline points="9 18 15 12 9 6"/></>,
  arrowsDiff: <><path d="M17 3l4 4-4 4"/><path d="M3 7h18"/><path d="M7 21l-4-4 4-4"/><path d="M21 17H3"/></>,
  compare: <><path d="M16 3h5v5M8 3H3v5M21 3l-7 7M3 3l7 7M3 21l7-7M21 21l-7-7M16 21h5v-5M8 21H3v-5"/></>,
  inbox: <><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></>,
  coins: <><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.66 3.13 3 7 3s7-1.34 7-3V5"/><path d="M5 11v6c0 1.66 3.13 3 7 3s7-1.34 7-3v-6"/></>,
  expenses: <><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></>,
  puzzle: <><path d="M9 3h6v4a2 2 0 102 2h4v6h-4a2 2 0 10-2 2v4H9v-4a2 2 0 10-2-2H3V9h4a2 2 0 102-2z"/></>,
  modules: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></>,
  alertCircle: <><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></>,
  refresh: <><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></>,
  check: <><polyline points="20 6 9 17 4 12"/></>,
};
export function Icon({ name, size = 18, color = "currentColor" }) {
  const aliases = { dashboard: "layout", arrowsdiff: "arrowsDiff", puzzlepiece: "puzzle", coin: "coins" };
  const iconName = aliases[name] || name;
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{iconPaths[iconName] || iconPaths.box}</svg>;
}

// ═══════════════════════════════════════════════
// SHELL COMPONENTS
// ═══════════════════════════════════════════════

/*
  Nav B layout (correct):
  ┌──────┬──────────┬─────────────────────────┐
  │      │          │        Topbar 52px       │
  │ Rail │  SubNav  ├─────────────────────────┤
  │ 76px │  220px   │                         │
  │      │ (anim)   │     ContentArea         │
  │      │          │     padding 16px 20px   │
  │ full │          │                         │
  │height│          │                         │
  └──────┴──────────┴─────────────────────────┘
  Rail spans full viewport height with logo at top.
  Topbar belongs to the main zone (right of rail+subnav).
*/

export function RailDivider() {
  return <div style={{ height: 0.5, margin: "8px 14px", background: T.color.border }} />;
}

export function RailItem({ icon, label, active, indicator, badge, onClick }) {
  const [hover, setHover] = useState(false);
  return <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{
    ...bs, width: 64, height: 56, margin: "2px 6px", display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 4, borderRadius: 10, border: "none", cursor: "pointer",
    position: "relative", transition: `all 120ms ${T.ease}`,
    color: active ? T.color.accentText : T.color.text2,
    background: active ? T.color.accentSoft : hover ? T.color.surface2 : "transparent",
    boxShadow: active ? `inset 0 0 0 0.5px ${T.color.border}` : "none",
  }}>
    <Icon name={icon} size={18} />
    <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.02em", lineHeight: 1 }}>{label}</span>
    {indicator && <span style={{
      position: "absolute", top: 8, right: 12, width: 7, height: 7, borderRadius: "50%",
      background: indicator === "green" ? T.color.success : "oklch(58% 0.16 305)",
      boxShadow: `0 0 0 2px ${T.color.surface}`,
    }} />}
    {badge && <span style={{
      position: "absolute", top: 8, right: 12, width: 7, height: 7, borderRadius: "50%",
      background: T.color.danger, boxShadow: `0 0 0 2px ${T.color.surface}`,
    }} />}
  </button>;
}

export function RailNav({ items, activeId, onSelect, logoContent }) {
  return <div style={{
    width: T.layout.railW, background: T.color.surface, display: "flex",
    flexDirection: "column", flexShrink: 0, height: "100%",
  }}>
    {/* Logo area */}
    <div style={{ height: T.layout.topbarH, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
      {logoContent || <div style={{
        width: 32, height: 32, borderRadius: 8, background: T.color.accentSoft,
        color: T.color.accentText, display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 700, ...bs,
      }}>E</div>}
    </div>
    {/* Nav items */}
    <nav style={{ paddingTop: 8, flex: 1, overflowY: "auto" }}>
      {items.map((item, i) => item.divider
        ? <RailDivider key={`d${i}`} />
        : <RailItem key={item.id} {...item} active={activeId === item.id} onClick={() => onSelect(item.id)} />
      )}
    </nav>
  </div>;
}

export function SubNavItem({ icon, label, active, badge, badgeTone = "neutral", onClick }) {
  const [hover, setHover] = useState(false);
  const tc = { danger: T.color.danger, warning: T.color.warning, info: T.color.info, neutral: T.color.text3 };
  return <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{
    ...bs, height: 32, padding: "0 10px", display: "flex", alignItems: "center", gap: 10,
    borderRadius: 6, border: "none", cursor: "pointer", width: "100%", textAlign: "left",
    transition: `all 120ms ${T.ease}`, fontSize: 13,
    color: active ? T.color.accentText : T.color.text2,
    background: active ? T.color.accentSoft : hover ? T.color.surface2 : "transparent",
    fontWeight: active ? 600 : 400,
    boxShadow: active ? `inset 2px 0 0 ${T.color.accent}` : "none",
  }}>
    <Icon name={icon} size={16} />
    <span style={{ flex: 1 }}>{label}</span>
    {badge != null && <span style={{
      fontFamily: T.font.mono, fontSize: 10, fontWeight: 600, minWidth: 18, textAlign: "center",
      padding: "0 5px", height: 18, lineHeight: "18px", borderRadius: 999,
      background: active ? "transparent" : T.color.surface2, color: tc[badgeTone] || T.color.text3,
    }}>{badge}</span>}
  </button>;
}

export function SubNav({ visible, groupLabel, children }) {
  return <div style={{
    width: visible ? T.layout.subnavW : 0, opacity: visible ? 1 : 0, overflow: "hidden", flexShrink: 0,
    transition: `width 150ms ${T.ease}, opacity 120ms ${T.ease}`,
    background: T.color.surface, height: "100%",
  }}>
    <div style={{ padding: "16px 8px 8px", display: "flex", flexDirection: "column", gap: 1, minWidth: T.layout.subnavW }}>
      {groupLabel && <div style={{ ...bs, fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: T.color.text3, padding: "0 10px", marginBottom: 8 }}>{groupLabel}</div>}
      {children}
    </div>
  </div>;
}

export function Topbar({ breadcrumbs = [], actions, userInitials = "ПС" }) {
  return <div style={{
    height: T.layout.topbarH, background: T.color.surface, borderBottom: bdr,
    padding: "0 20px", display: "flex", alignItems: "center", gap: 12, flexShrink: 0, ...bs,
  }}>
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: T.color.text2 }}>
      {breadcrumbs.map((b, i) => <span key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {i > 0 && <Icon name="chevRight" size={12} color={T.color.text3} />}
        <span style={{ color: i === breadcrumbs.length - 1 ? T.color.text : T.color.text2 }}>{b}</span>
      </span>)}
    </div>
    <div style={{ flex: 1 }} />
    {actions}
    <div style={{ width: 1, height: 24, background: T.color.border, margin: "0 4px" }} />
    <button style={{ ...bs, background: "none", border: "none", cursor: "pointer", padding: 4, display: "flex" }}>
      <Icon name="bell" size={18} color={T.color.text3} />
    </button>
    <div style={{
      width: 28, height: 28, borderRadius: 999, background: T.color.surface2,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 600, color: T.color.text2, ...bs,
    }}>{userInitials}</div>
  </div>;
}

export function ContentArea({ children }) {
  return <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", background: T.color.bg }}>{children}</div>;
}

export function AppShell({ railItems, activeRailId, onRailSelect, subnavVisible, subnavContent, topbarBreadcrumbs, topbarActions, userInitials, logoContent, children }) {
  return <div style={{ display: "flex", height: "100%", background: T.color.bg, ...bs }}>
    {/* Rail — full height */}
    <div style={{ borderRight: subnavVisible ? bdr : "none", display: "flex", flexShrink: 0 }}>
      <RailNav items={railItems} activeId={activeRailId} onSelect={onRailSelect} logoContent={logoContent} />
    </div>
    {/* SubNav — full height, animated */}
    <SubNav visible={subnavVisible}>{subnavContent}</SubNav>
    {/* Outer border between nav zone and main */}
    {subnavVisible && <div style={{ width: 0.5, background: T.color.border, flexShrink: 0 }} />}
    {!subnavVisible && <div style={{ width: 0.5, background: T.color.border, flexShrink: 0 }} />}
    {/* Main zone: topbar + content */}
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <Topbar breadcrumbs={topbarBreadcrumbs} actions={topbarActions} userInitials={userInitials} />
      <ContentArea>{children}</ContentArea>
    </div>
  </div>;
}

// ═══════════════════════════════════════════════
// UI COMPONENTS
// ═══════════════════════════════════════════════

export function Badge({ variant = "default", children }) {
  const s = {
    default: { background: T.color.surface3, color: T.color.text2, border: bdr },
    info: { background: T.color.infoBg, color: T.color.info },
    success: { background: T.color.successBg, color: "oklch(34% 0.12 158)" },
    warning: { background: T.color.warningBg, color: "oklch(45% 0.12 75)" },
    danger: { background: T.color.dangerBg, color: "oklch(36% 0.16 22)" },
    wb: { background: T.color.mpWbBg, color: T.color.mpWb },
    ozon: { background: T.color.mpOzonBg, color: T.color.mpOzon },
  };
  return <span style={{ ...bs, display: "inline-flex", alignItems: "center", gap: 4, height: 20, padding: "0 7px", borderRadius: 999, fontSize: 11, fontWeight: 500, border: "0.5px solid transparent", ...(s[variant] || s.default) }}>{children}</span>;
}

export function Btn({ variant = "primary", size = "default", icon, children, onClick }) {
  const [hover, setHover] = useState(false);
  const sz = { sm: { height: 28, padding: "0 8px", fontSize: 12 }, default: { height: 32, padding: "0 10px", fontSize: 13 }, lg: { height: 40, padding: "0 16px", fontSize: 14 } };
  const v = {
    primary: { background: T.color.accent, color: T.color.textOnDark, border: "0.5px solid transparent" },
    secondary: { background: T.color.surface, color: T.color.text, border: bdr, boxShadow: T.shadow.xs },
    ghost: { background: "transparent", color: T.color.text, border: "0.5px solid transparent" },
    danger: { background: T.color.danger, color: "white", border: "0.5px solid transparent" },
  };
  const hv = {
    primary: { background: T.color.accentHover },
    secondary: { background: T.color.surface2 },
    ghost: { background: T.color.surface2 },
    danger: { background: "oklch(48% 0.20 22)" },
  };
  const isIconOnly = !children && icon;
  return <button onClick={onClick} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{
    ...bs, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
    borderRadius: 6, fontWeight: 500, letterSpacing: "-0.005em", cursor: "pointer",
    whiteSpace: "nowrap", transition: `all 120ms ${T.ease}`,
    ...(sz[size] || sz.default), ...(v[variant] || v.primary), ...(hover ? (hv[variant] || hv.primary) : {}),
    ...(isIconOnly ? { width: sz[size]?.height || 32, padding: 0 } : {}),
  }}>
    {icon && <Icon name={icon} size={size === "sm" ? 14 : 16} />}
    {children}
  </button>;
}

export function MarketplaceSwitch({ value, options = ["wb", "ozon"], onChange }) {
  const lb = { wb: "WB", ozon: "Ozon", ya: "YM" };
  return <div style={{ display: "inline-flex", background: T.color.surface2, border: bdr, borderRadius: 6, padding: 2, gap: 2 }}>
    {options.map(o => <button key={o} onClick={() => onChange(o)} style={{
      ...bs, height: 24, padding: "0 10px", borderRadius: 4, fontSize: 12, border: "none", cursor: "pointer",
      fontWeight: value === o ? 500 : 400, color: value === o ? T.color.text : T.color.text2,
      background: value === o ? T.color.surface : "transparent",
      boxShadow: value === o ? T.shadow.xs : "none", transition: `all 120ms ${T.ease}`,
    }}>{lb[o] || o}</button>)}
  </div>;
}

export function Breadcrumbs({ items = [] }) {
  return <div style={{ display: "flex", alignItems: "center", gap: 6, ...bs }}>
    {items.map((item, i) => <span key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {i > 0 && <Icon name="chevRight" size={12} color={T.color.text3} />}
      <span style={{ fontSize: 12, color: i === items.length - 1 ? T.color.text : T.color.text2 }}>{item}</span>
    </span>)}
  </div>;
}

export function PageHeader({ title, eyebrow, subtitle, tag, actions }) {
  return <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 16, ...bs }}>
    <div>
      {eyebrow && <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.color.text3, marginBottom: 4 }}>{eyebrow}</div>}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h1 style={{ fontSize: 22, lineHeight: 1.1, fontWeight: 600, letterSpacing: "-0.02em", color: T.color.text, margin: 0 }}>{title}</h1>
        {tag}
      </div>
      {subtitle && <div style={{ fontSize: 12, color: T.color.text2, marginTop: 4 }}>{subtitle}</div>}
    </div>
    {actions && <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>{actions}</div>}
  </div>;
}

export function FilterBar({ search, filters = [], actions }) {
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: T.radius.lg, padding: 12, marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", ...bs }}>
    {search && <div style={{ position: "relative", width: 280 }}>
      <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}><Icon name="search" size={14} color={T.color.text3} /></span>
      <input placeholder={search} style={{ ...bs, height: 28, width: "100%", padding: "0 10px 0 32px", border: bdr, borderRadius: 6, fontSize: 12, background: T.color.surface, color: T.color.text, outline: "none" }} />
    </div>}
    {filters.map((f, i) => <Btn key={i} variant="secondary" size="sm" icon={f.icon}>{f.label}</Btn>)}
    <div style={{ flex: 1 }} />
    {actions}
  </div>;
}

// ─── Checkbox ───
function Checkbox({ checked, onChange }) {
  return <div onClick={(e) => { e.stopPropagation(); onChange(!checked); }} style={{
    width: 18, height: 18, borderRadius: 5, border: checked ? `1.5px solid ${T.color.accent}` : `1.5px solid ${T.color.border}`,
    background: checked ? T.color.accent : T.color.surface, cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, transition: `all 120ms ${T.ease}`,
  }}>{checked && <Icon name="check" size={12} color={T.color.textOnDark} />}</div>;
}

// ─── DataTable with sticky support ───
export function DataTable({ columns, rows, selectedIds, onSelectionChange, onRowClick, loading, empty, error, selectable }) {
  const thS = { ...bs, fontSize: 11, fontWeight: 500, letterSpacing: "0.04em", textTransform: "uppercase", color: T.color.text3, background: T.color.surface2, borderBottom: bdr, padding: "10px 14px", textAlign: "left", whiteSpace: "nowrap" };
  const tdS = { ...bs, padding: "10px 14px", borderBottom: bdr, fontSize: 13, color: T.color.text, verticalAlign: "middle" };
  const selectColW = selectable ? 44 : 0;
  const stickyLeft = (c) => (c.stickyLeft ?? 0) + selectColW;

  if (loading) return <LoadingState type="table" />;
  if (error) return <ErrorState message={error} />;
  if (empty || (!rows?.length && !loading)) return <EmptyState />;

  const allSelected = selectable && rows.length > 0 && selectedIds?.size === rows.length;
  const toggleAll = () => {
    if (!onSelectionChange) return;
    onSelectionChange(allSelected ? new Set() : new Set(rows.map((_, i) => String(i))));
  };
  const toggleRow = (i) => {
    if (!onSelectionChange || !selectedIds) return;
    const next = new Set(selectedIds);
    const id = String(i);
    next.has(id) ? next.delete(id) : next.add(id);
    onSelectionChange(next);
  };

  return <div style={{ border: bdr, borderRadius: 10, background: T.color.surface, overflowX: "auto" }}>
    <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
      <thead><tr>
        {selectable && <th style={{ ...thS, width: 44, textAlign: "center", position: "sticky", left: 0, zIndex: 5, background: T.color.surface2 }}>
          <Checkbox checked={allSelected} onChange={toggleAll} />
        </th>}
        {columns.map((c, i) => <th key={i} style={{
          ...thS, width: c.width, minWidth: c.minWidth,
          ...(c.numeric ? { textAlign: "right", fontVariantNumeric: "tabular-nums" } : {}),
          ...(c.sticky ? { position: "sticky", left: stickyLeft(c), zIndex: 5, background: T.color.surface2 } : {}),
        }}>{c.title}</th>)}
      </tr></thead>
      <tbody>{rows.map((row, ri) => {
        const isLast = ri === rows.length - 1;
        const isSelected = selectedIds?.has(String(ri));
        return <tr key={ri}
          onClick={() => onRowClick?.(row)}
          style={{ cursor: onRowClick ? "pointer" : "default", transition: `background 120ms ${T.ease}`, background: isSelected ? T.color.accentSoft : "transparent" }}
          onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = T.color.surface2; }}
          onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = "transparent"; }}
        >
          {selectable && <td style={{ ...tdS, width: 44, textAlign: "center", position: "sticky", left: 0, zIndex: 3, background: isSelected ? T.color.accentSoft : T.color.surface, ...(isLast ? { borderBottom: "none" } : {}) }}>
            <Checkbox checked={isSelected} onChange={() => toggleRow(ri)} />
          </td>}
          {columns.map((c, ci) => <td key={ci} style={{
            ...tdS,
            ...(c.numeric ? { textAlign: "right", fontVariantNumeric: "tabular-nums", fontFamily: T.font.mono, fontSize: 12 } : {}),
            ...(c.sticky ? { position: "sticky", left: stickyLeft(c), zIndex: 3, background: isSelected ? T.color.accentSoft : T.color.surface } : {}),
            ...(isLast ? { borderBottom: "none" } : {}),
          }}>{c.render(row)}</td>)}
        </tr>;
      })}</tbody>
    </table>
  </div>;
}

// ─── ProductRow (renders inside DataTable columns) ───
export function ProductRow({ imageLabel, sku, nmId, title, category, thumbSize = 28, titleMaxWidth = 360 }) {
  const large = thumbSize >= 40;
  return <div style={{ display: "flex", gap: 10, alignItems: "center", ...bs }}>
    <div style={{ width: thumbSize, height: thumbSize, borderRadius: 6, background: T.color.surface2, border: bdr, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: T.font.mono, fontSize: large ? 11 : 9, color: T.color.text3, flexShrink: 0 }}>{imageLabel || "img"}</div>
    <div style={{ minWidth: 0 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
        <span style={{ fontFamily: T.font.mono, fontSize: large ? 12 : 11, fontWeight: 500, color: T.color.text }}>{sku}</span>
        <span style={{ fontFamily: T.font.mono, fontSize: large ? 11 : 10, color: T.color.text3 }}>{nmId}</span>
      </div>
      <div style={{ fontSize: large ? 13 : 12, lineHeight: 1.3, color: T.color.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: titleMaxWidth }}>{title}</div>
      {category && <div style={{ fontSize: large ? 11 : 10, color: T.color.text3 }}>{category}</div>}
    </div>
  </div>;
}

export function MetricCard({ label, value, delta, deltaTone = "neutral", compact }) {
  const dc = { success: T.color.success, danger: T.color.danger, neutral: T.color.text3 };
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: compact ? 12 : 20, flex: 1, minWidth: 130, ...bs }}>
    <div style={{ fontSize: compact ? 11 : 12, color: T.color.text3, marginBottom: compact ? 6 : 8 }}>{label}</div>
    <div style={{ fontSize: compact ? 22 : 28, fontWeight: 600, color: T.color.text, lineHeight: T.leading.tight, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    {delta != null && <div style={{ fontSize: 12, fontFamily: T.font.mono, fontVariantNumeric: "tabular-nums", color: dc[deltaTone], marginTop: 4 }}>{delta}</div>}
  </div>;
}

export function ProjectCard({ name, marketplaces = ["wb"], metrics = [], updatedAt }) {
  const [hover, setHover] = useState(false);
  const mpV = { wb: "wb", ozon: "ozon", ya: "default" };
  const mpL = { wb: "WB", ozon: "Ozon", ya: "YM" };
  return <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{
    background: hover ? T.color.surface2 : T.color.surface,
    border: bdr, borderRadius: T.radius.lg, boxShadow: T.shadow.sm, padding: 20,
    cursor: "pointer", transition: `all 120ms ${T.ease}`, ...bs,
  }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
      <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em", color: T.color.text }}>{name}</span>
      {marketplaces.map(m => <Badge key={m} variant={mpV[m]}>{mpL[m]}</Badge>)}
      <div style={{ flex: 1 }} />
      {updatedAt && <span style={{ fontSize: 11, color: T.color.text3 }}>{updatedAt}</span>}
    </div>
    <div style={{ display: "flex", gap: 24 }}>
      {metrics.map((m, i) => <div key={i}>
        <div style={{ fontSize: 11, color: T.color.text3, marginBottom: 2 }}>{m.label}</div>
        <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: "tabular-nums", color: m.tone === "danger" ? T.color.danger : m.tone === "warning" ? T.color.warning : T.color.text }}>{m.value}</div>
      </div>)}
    </div>
  </div>;
}

// ─── States ───
export function LoadingState({ type = "card" }) {
  const line = { height: 10, borderRadius: 999, background: T.color.surface3 };
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: 20, minHeight: type === "table" ? 200 : 120, ...bs }}>
    <style>{`@keyframes ecPulse{0%,100%{opacity:.6}50%{opacity:.3}}`}</style>
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {[40, 70, 55, ...(type === "table" ? [80, 45] : [])].map((w, i) => <div key={i} style={{ ...line, width: `${w}%`, animation: "ecPulse 1.2s ease-in-out infinite" }} />)}
    </div>
  </div>;
}
export function EmptyState({ title = "Нет данных", description = "По выбранным фильтрам ничего не найдено", action }) {
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: 40, minHeight: 180, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, textAlign: "center", ...bs }}>
    <Icon name="box" size={32} color={T.color.text3} />
    <div style={{ fontSize: 14, fontWeight: 600, color: T.color.text }}>{title}</div>
    <div style={{ fontSize: 12, color: T.color.text2, maxWidth: 360 }}>{description}</div>
    {action || <Btn variant="secondary" size="sm">Сбросить фильтры</Btn>}
  </div>;
}
export function ErrorState({ message = "Не удалось загрузить данные" }) {
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: 40, minHeight: 160, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, textAlign: "center", ...bs }}>
    <Icon name="alertCircle" size={32} color={T.color.danger} />
    <div style={{ fontSize: 14, fontWeight: 600, color: T.color.text }}>Ошибка</div>
    <div style={{ fontSize: 12, color: T.color.text2, maxWidth: 360 }}>{message}</div>
    <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
      <Btn variant="primary" size="sm" icon="refresh">Повторить</Btn>
      <Btn variant="ghost" size="sm">Подробнее</Btn>
    </div>
  </div>;
}

// ═══════════════════════════════════════════════
// SHOWCASE (default export)
// ═══════════════════════════════════════════════

function SectionHeader({ title, sub }) {
  return <div style={{ marginBottom: 20 }}>
    <h2 style={{ ...bs, fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: T.color.text3, marginBottom: sub ? 4 : 12 }}>{title}</h2>
    {sub && <p style={{ ...bs, fontSize: 12, color: T.color.text2, marginBottom: 12 }}>{sub}</p>}
  </div>;
}

const TABS = [
  { id: "shell", label: "Shell" },
  { id: "nav", label: "Nav" },
  { id: "data", label: "Данные" },
  { id: "states", label: "Состояния" },
];

const RAIL_ITEMS = [
  { id: "overview", icon: "layout", label: "Обзор" },
  { id: "wb", icon: "box", label: "WB", indicator: "green" },
  { id: "ozon", icon: "box", label: "Ozon" },
  { id: "modules", icon: "puzzle", label: "Модули", indicator: "purple" },
  { divider: true },
  { id: "compare", icon: "arrowsDiff", label: "Сравн." },
  { id: "inbox", icon: "bell", label: "Сигналы", badge: true },
  { id: "expenses", icon: "coins", label: "Расходы" },
  { divider: true },
  { id: "settings", icon: "settings", label: "Настр." },
];

const SUB_ITEMS = [
  { id: "data", icon: "chart", label: "Загрузка данных" },
  { id: "schedule", icon: "settings", label: "Расписание" },
  { id: "catalog", icon: "box", label: "Каталог" },
  { id: "stock", icon: "box", label: "Наличие данных", badge: 3, badgeTone: "warning" },
];

const PRODUCTS = [
  { sku: "WB-4820", nmId: "174928301", title: "Футболка детская хлопок 100%", cat: "Детская одежда", price: "890 ₽", rrp: "1 190 ₽", stock: 142 },
  { sku: "WB-4821", nmId: "174928302", title: "Платье летнее с принтом единорога", cat: "Детская одежда", price: "1 290 ₽", rrp: "1 590 ₽", stock: 67 },
  { sku: "WB-4822", nmId: "174928303", title: "Комплект шорты + футболка морская тема", cat: "Детская одежда", price: "1 490 ₽", rrp: "1 890 ₽", stock: 0 },
];

export default function DesignSystemShowcase() {
  const [tab, setTab] = useState("shell");
  const [mp, setMp] = useState("wb");
  const [rail, setRail] = useState("wb");
  const [sub, setSub] = useState("data");
  const [sel, setSel] = useState(new Set());

  const hasSubnav = rail === "wb" || rail === "ozon" || rail === "settings";

  return <div style={{ ...bs, background: T.color.bg, minHeight: "100vh", color: T.color.text }}>
    {/* Header */}
    <div style={{ background: T.color.surface, borderBottom: bdr, padding: "14px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em" }}>Ecomcore Design System</div>
        <div style={{ fontSize: 11, color: T.color.text3, marginTop: 2 }}>v1.1 · Nav B · Composable components · Named exports</div>
      </div>
      <div style={{ display: "flex", gap: 2 }}>
        {TABS.map(t => <button key={t.id} onClick={() => setTab(t.id)} style={{
          ...bs, height: 28, padding: "0 12px", borderRadius: 6, fontSize: 12, border: "none", cursor: "pointer",
          fontWeight: tab === t.id ? 500 : 400, color: tab === t.id ? T.color.textOnDark : T.color.text2,
          background: tab === t.id ? T.color.accent : "transparent", transition: `all 120ms ${T.ease}`,
        }}>{t.label}</button>)}
      </div>
    </div>

    <div style={{ padding: "32px 24px", maxWidth: 1060 }}>

      {/* ═══ SHELL ═══ */}
      {tab === "shell" && <>
        <SectionHeader title="AppShell — Nav B layout" sub="Rail на всю высоту (с logo), SubNav анимирован, Topbar принадлежит main zone. Кликайте по rail." />
        <div style={{ border: bdr, borderRadius: T.radius.lg, overflow: "hidden", height: 500 }}>
          <AppShell
            railItems={RAIL_ITEMS}
            activeRailId={rail}
            onRailSelect={setRail}
            subnavVisible={hasSubnav}
            subnavContent={SUB_ITEMS.map(s => <SubNavItem key={s.id} {...s} active={sub === s.id} onClick={() => setSub(s.id)} />)}
            topbarBreadcrumbs={["Проекты", "Zakka", "Настройки"]}
            topbarActions={<MarketplaceSwitch value={mp} options={["wb", "ozon", "ya"]} onChange={setMp} />}
            userInitials="ПС"
          >
            <PageHeader title="Загрузка данных WB" eyebrow="Настройки" subtitle="Состояние и управление загрузками." tag={<Badge variant="wb">WB</Badge>} actions={<Btn size="sm">Загрузить всё</Btn>} />
            <div style={{ fontSize: 12, color: T.color.text3, marginTop: 8 }}>
              Rail на всю высоту · Logo выровнен с Topbar · SubNav появляется для WB/Ozon/Настройки · Topbar только в main zone
            </div>
          </AppShell>
        </div>

        <div style={{ marginTop: 32 }}>
          <SectionHeader title="Layout dimensions" />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            {[["Rail", "76px"], ["RailItem", "64×56"], ["SubNav", "220px"], ["Topbar", "52px"],
              ["Content pad", "16px 20px"], ["Border", "0.5px"], ["Logo", "32×32 r8"], ["Rail label", "9px/600"],
            ].map(([l, v]) => <div key={l} style={{ background: T.color.surface, border: bdr, borderRadius: 6, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: T.color.text3, marginBottom: 2 }}>{l}</div>
              <div style={{ fontFamily: T.font.mono, fontSize: 13, fontWeight: 500 }}>{v}</div>
            </div>)}
          </div>
        </div>
      </>}

      {/* ═══ NAV ═══ */}
      {tab === "nav" && <>
        <SectionHeader title="RailItem" sub="64×56, icon 18px, label 9px/600. Active = accentSoft + accentText + inset border." />
        <div style={{ display: "flex", gap: 4, marginBottom: 32 }}>
          <RailItem icon="layout" label="Обзор" active />
          <RailItem icon="box" label="WB" indicator="green" />
          <RailItem icon="puzzle" label="Модули" indicator="purple" />
          <RailItem icon="bell" label="Сигналы" badge />
          <RailItem icon="settings" label="Настр." />
        </div>

        <SectionHeader title="SubNavItem" sub="H 32, icon 16, text 13. Active = inset 2px left accent." />
        <div style={{ width: 220, background: T.color.surface, border: bdr, borderRadius: 6, padding: 8, marginBottom: 32 }}>
          {SUB_ITEMS.map(s => <SubNavItem key={s.id} {...s} active={sub === s.id} onClick={() => setSub(s.id)} />)}
        </div>

        <SectionHeader title="MarketplaceSwitch · Breadcrumbs · Badges · Buttons" />
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <MarketplaceSwitch value={mp} options={["wb", "ozon", "ya"]} onChange={setMp} />
            <Breadcrumbs items={["Проекты", "ИП Сидорова", "WB", "Цены"]} />
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <Badge>Default</Badge><Badge variant="info">Info</Badge><Badge variant="success">✓ Успешно</Badge>
            <Badge variant="warning">⚠ Внимание</Badge><Badge variant="danger">✕ Ошибка</Badge>
            <Badge variant="wb">WB</Badge><Badge variant="ozon">Ozon</Badge>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn>Primary</Btn><Btn variant="secondary">Secondary</Btn><Btn variant="ghost">Ghost</Btn><Btn variant="danger">Danger</Btn>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn size="sm">sm 28</Btn><Btn size="default">default 32</Btn><Btn size="lg">lg 40</Btn>
            <Btn variant="secondary" size="sm" icon="filter">Filter</Btn>
          </div>
        </div>
      </>}

      {/* ═══ DATA ═══ */}
      {tab === "data" && <>
        <SectionHeader title="FilterBar + DataTable + ProductRow" sub="Полная цепочка: фильтры → таблица с чекбоксами, sticky, hover, selection." />
        <FilterBar search="Поиск по SKU, названию..." filters={[{ label: "Статус", icon: "filter" }, { label: "Категория", icon: "filter" }]} actions={<Btn variant="secondary" size="sm">Столбцы</Btn>} />
        <DataTable
          selectable
          selectedIds={sel}
          onSelectionChange={setSel}
          columns={[
            { title: "Товар", sticky: true, stickyLeft: 0, minWidth: 300, render: r => <ProductRow sku={r.sku} nmId={r.nmId} title={r.title} category={r.cat} /> },
            { title: "Цена", width: 90, numeric: true, render: r => r.price },
            { title: "РРЦ", width: 90, numeric: true, render: r => r.rrp },
            { title: "Остаток", width: 76, numeric: true, render: r => <span style={{ color: r.stock === 0 ? T.color.danger : T.color.text }}>{r.stock}</span> },
            { title: "Статус", width: 120, render: r => r.stock === 0 ? <Badge variant="danger">Нет остатка</Badge> : <Badge variant="success">В наличии</Badge> },
          ]}
          rows={PRODUCTS}
        />

        <div style={{ marginTop: 32 }}>
          <SectionHeader title="MetricCard" sub="Compact (12px pad, 22px val) и Large (20px pad, 28px val)." />
          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <MetricCard label="Выручка" value="2.4М ₽" delta="+12%" deltaTone="success" compact />
            <MetricCard label="Заказы" value="1 230" delta="+8%" deltaTone="success" compact />
            <MetricCard label="Конверсия" value="4.2%" delta="−0.3" deltaTone="danger" compact />
          </div>
        </div>

        <SectionHeader title="ProjectCard" />
        <div style={{ maxWidth: 700, display: "flex", flexDirection: "column", gap: 12 }}>
          <ProjectCard name="ИП Сидорова / Fashion Kids" marketplaces={["wb", "ozon"]} updatedAt="2 ч. назад" metrics={[{ label: "Карточки", value: "847" }, { label: "Выручка 7д", value: "2.4М ₽" }, { label: "Ошибки", value: "5", tone: "danger" }]} />
        </div>
      </>}

      {/* ═══ STATES ═══ */}
      {tab === "states" && <>
        <SectionHeader title="Loading" sub="Skeleton: pill radius, surface3, pulse 1.2s. Контейнер держит размер." />
        <div style={{ display: "flex", gap: 12, marginBottom: 32 }}>
          <div style={{ flex: 1 }}><LoadingState type="card" /></div>
          <div style={{ flex: 1 }}><LoadingState type="table" /></div>
        </div>
        <SectionHeader title="Empty" sub="Icon 32px text3, title 14/600, desc 12px text2, action btn." />
        <div style={{ marginBottom: 32 }}><EmptyState title="Товары не найдены" description="Попробуйте изменить параметры поиска или сбросить фильтры." /></div>
        <SectionHeader title="Error" sub="Danger icon, title, message, retry + details." />
        <ErrorState message="Не удалось загрузить данные с Wildberries. Проверьте API-ключ." />
      </>}

    </div>
  </div>;
}
