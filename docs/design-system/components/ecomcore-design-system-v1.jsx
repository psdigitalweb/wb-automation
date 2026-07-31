import { useState } from "react";

/* ═══════════════════════════════════════════════
   ECOMCORE DESIGN SYSTEM v1 — Nav B Source of Truth
   ═══════════════════════════════════════════════ */

const T = {
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
    sans: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif',
    mono: '"Geist Mono", ui-monospace, "JetBrains Mono", monospace',
  },
  text: { xs: 11, sm: 12, base: 13, md: 14, lg: 16, xl: 20, "2xl": 24, "3xl": 32 },
  weight: { regular: 400, medium: 500, semibold: 600, bold: 700 },
  leading: { tight: 1.15, snug: 1.3, base: 1.5 },
  space: (n) => n * 4,
  radius: { xs: 4, sm: 6, md: 8, lg: 10, xl: 14, pill: 999 },
  shadow: {
    xs: "0 1px 0 0 oklch(20% 0.01 75 / 0.04)",
    sm: "0 1px 2px oklch(20% 0.01 75 / 0.05), 0 1px 0 oklch(20% 0.01 75 / 0.03)",
    md: "0 4px 12px oklch(20% 0.01 75 / 0.06), 0 1px 0 oklch(20% 0.01 75 / 0.04)",
    focus: "0 0 0 3px oklch(38% 0.10 155 / 0.22)",
  },
  layout: { railW: 76, railItemW: 64, railItemH: 56, subnavW: 220, topbarH: 52 },
  ease: "cubic-bezier(0.2, 0.8, 0.2, 1)",
};

const bdr = `0.5px solid ${T.color.border}`;
const base = { fontFamily: T.font.sans, WebkitFontSmoothing: "antialiased", fontFeatureSettings: '"cv11", "ss01", "ss03"' };

/* ── Icons (inline SVG, Lucide-style) ── */
const icons = {
  home: <><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1z"/><path d="M9 21V12h6v9"/></>,
  box: <><path d="M21 8L12 2 3 8v8l9 6 9-6z"/><path d="M12 22V12M21 8l-9 4-9-4"/></>,
  chart: <><rect x="3" y="10" width="4" height="11" rx="1"/><rect x="10" y="3" width="4" height="18" rx="1"/><rect x="17" y="7" width="4" height="14" rx="1"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-2.82 1.18V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 3 15.4V14a2 2 0 0 1 4 0v.09c.08.55.44 1.03 1 1.24"/></>,
  bell: <><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></>,
  search: <><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></>,
  filter: <><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></>,
  chevRight: <><polyline points="9 18 15 12 9 6"/></>,
  compare: <><path d="M16 3h5v5M8 3H3v5M21 3L14 10M3 3l7 7M3 21l7-7M21 21l-7-7M16 21h5v-5M8 21H3v-5"/></>,
  inbox: <><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></>,
  expenses: <><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></>,
  modules: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></>,
  alertCircle: <><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></>,
  refresh: <><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></>,
};
function Icon({ name, size = 18, color = "currentColor" }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{icons[name]}</svg>;
}

/* ── Section / Demo helpers ── */
function Section({ title, sub, children }) {
  return <div style={{ marginBottom: 48 }}>
    <h2 style={{ ...base, fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: T.color.text3, marginBottom: 4 }}>{title}</h2>
    {sub && <p style={{ ...base, fontSize: 12, color: T.color.text2, marginBottom: 16 }}>{sub}</p>}
    {!sub && <div style={{ height: 12 }} />}
    {children}
  </div>;
}
function Demo({ label, children, row, gap = 8 }) {
  return <div style={{ marginBottom: 20 }}>
    {label && <div style={{ ...base, fontSize: 11, color: T.color.text3, marginBottom: 8 }}>{label}</div>}
    <div style={row ? { display: "flex", flexWrap: "wrap", gap, alignItems: "center" } : undefined}>{children}</div>
  </div>;
}

/* ══════════════════════════════════════════════
   COMPONENTS — exactly per Nav B spec
   ══════════════════════════════════════════════ */

/* ── RailItem ── */
function RailItem({ icon, label, active, indicator, badge, onClick }) {
  return <button onClick={onClick} style={{
    ...base, width: 64, height: 56, margin: "2px 6px", display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 4, borderRadius: 10, border: "none", cursor: "pointer",
    position: "relative", transition: `all 120ms ${T.ease}`,
    color: active ? T.color.accentText : T.color.text2,
    background: active ? T.color.accentSoft : "transparent",
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

/* ── SubNavItem ── */
function SubNavItem({ icon, label, active, badge, badgeTone = "neutral", onClick }) {
  const toneColor = { danger: T.color.danger, warning: T.color.warning, info: T.color.info, neutral: T.color.text3 };
  return <button onClick={onClick} style={{
    ...base, height: 32, padding: "0 10px", display: "flex", alignItems: "center", gap: 10,
    borderRadius: 6, border: "none", cursor: "pointer", width: "100%", textAlign: "left",
    transition: `all 120ms ${T.ease}`,
    color: active ? T.color.accentText : T.color.text2,
    background: active ? T.color.accentSoft : "transparent",
    fontWeight: active ? 600 : 400,
    boxShadow: active ? `inset 2px 0 0 ${T.color.accent}` : "none",
    fontSize: 13,
  }}>
    <Icon name={icon} size={16} />
    <span style={{ flex: 1 }}>{label}</span>
    {badge != null && <span style={{
      fontFamily: T.font.mono, fontSize: 10, fontWeight: 600, minWidth: 18, textAlign: "center",
      padding: "0 5px", height: 18, lineHeight: "18px", borderRadius: 999,
      background: active ? "transparent" : T.color.surface2,
      color: toneColor[badgeTone] || T.color.text3,
    }}>{badge}</span>}
  </button>;
}

/* ── SubNav ── */
function SubNav({ visible, title, children }) {
  return <div style={{
    width: visible ? 220 : 0, opacity: visible ? 1 : 0, overflow: "hidden", flexShrink: 0,
    transition: `width 150ms ${T.ease}, opacity 120ms ${T.ease}`,
    borderRight: visible ? bdr : "none", background: T.color.surface,
  }}>
    <div style={{ padding: "16px 8px 8px", display: "flex", flexDirection: "column", gap: 1, minWidth: 220 }}>
      {title && <div style={{ ...base, fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: T.color.text3, padding: "0 10px", marginBottom: 8 }}>{title}</div>}
      {children}
    </div>
  </div>;
}

/* ── Topbar ── */
function Topbar({ breadcrumbs = [], projectName, userInitials = "ПС", actions }) {
  return <div style={{
    height: T.layout.topbarH, background: T.color.surface, borderBottom: bdr,
    padding: "0 20px", display: "flex", alignItems: "center", gap: 12, flexShrink: 0, ...base,
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
    <button style={{ ...base, background: "none", border: "none", cursor: "pointer", padding: 4, display: "flex" }}>
      <Icon name="bell" size={18} color={T.color.text3} />
    </button>
    <div style={{
      width: 28, height: 28, borderRadius: 999, background: T.color.surface2,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 600, color: T.color.text2,
    }}>{userInitials}</div>
  </div>;
}

/* ── Breadcrumbs ── */
function Breadcrumbs({ items = [] }) {
  return <div style={{ display: "flex", alignItems: "center", gap: 6, ...base }}>
    {items.map((item, i) => <span key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {i > 0 && <Icon name="chevRight" size={12} color={T.color.text3} />}
      <span style={{ fontSize: 12, color: i === items.length - 1 ? T.color.text : T.color.text2 }}>{item}</span>
    </span>)}
  </div>;
}

/* ── PageHeader ── */
function PageHeader({ title, eyebrow, subtitle, tag, actions }) {
  return <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 16, ...base }}>
    <div>
      {eyebrow && <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: T.color.text3, marginBottom: 4 }}>{eyebrow}</div>}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h1 style={{ fontSize: 22, lineHeight: 1.1, fontWeight: 600, letterSpacing: "-0.02em", color: T.color.text, margin: 0 }}>{title}</h1>
        {tag}
      </div>
      {subtitle && <div style={{ fontSize: 12, color: T.color.text2, marginTop: 4 }}>{subtitle}</div>}
    </div>
    {actions && <div style={{ display: "flex", gap: 8 }}>{actions}</div>}
  </div>;
}

/* ── Badge ── */
function Badge({ variant = "default", children }) {
  const styles = {
    default: { background: T.color.surface3, color: T.color.text2, border: bdr },
    info: { background: T.color.infoBg, color: T.color.info, border: "0.5px solid transparent" },
    success: { background: T.color.successBg, color: "oklch(34% 0.12 158)", border: "0.5px solid transparent" },
    warning: { background: T.color.warningBg, color: "oklch(45% 0.12 75)", border: "0.5px solid transparent" },
    danger: { background: T.color.dangerBg, color: "oklch(36% 0.16 22)", border: "0.5px solid transparent" },
    wb: { background: T.color.mpWbBg, color: T.color.mpWb, border: "0.5px solid transparent" },
    ozon: { background: T.color.mpOzonBg, color: T.color.mpOzon, border: "0.5px solid transparent" },
  };
  return <span style={{ ...base, display: "inline-flex", alignItems: "center", gap: 4, height: 20, padding: "0 7px", borderRadius: 999, fontSize: 11, fontWeight: 500, letterSpacing: "0.01em", ...(styles[variant] || styles.default) }}>{children}</span>;
}

/* ── Button ── */
function Btn({ variant = "primary", size = "default", icon, children, onClick }) {
  const sizes = { sm: { height: 28, padding: "0 8px", fontSize: 12 }, default: { height: 32, padding: "0 10px", fontSize: 13 }, lg: { height: 40, padding: "0 16px", fontSize: 14 } };
  const variants = {
    primary: { background: T.color.accent, color: T.color.textOnDark, border: "0.5px solid transparent" },
    secondary: { background: T.color.surface, color: T.color.text, border: bdr, boxShadow: T.shadow.xs },
    ghost: { background: "transparent", color: T.color.text, border: "0.5px solid transparent" },
    danger: { background: T.color.danger, color: "white", border: "0.5px solid transparent" },
  };
  const isIcon = !children && icon;
  return <button onClick={onClick} style={{
    ...base, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
    borderRadius: 6, fontWeight: 500, letterSpacing: "-0.005em", cursor: "pointer",
    whiteSpace: "nowrap", transition: `all 120ms ${T.ease}`,
    ...(sizes[size] || sizes.default), ...(variants[variant] || variants.primary),
    ...(isIcon ? { width: sizes[size]?.height || 32, padding: 0 } : {}),
  }}>
    {icon && <Icon name={icon} size={size === "sm" ? 14 : 16} />}
    {children}
  </button>;
}

/* ── MarketplaceSwitch (segmented) ── */
function MarketplaceSwitch({ value, options = ["wb", "ozon"], onChange }) {
  const labels = { wb: "WB", ozon: "Ozon", ya: "YM" };
  return <div style={{ display: "inline-flex", background: T.color.surface2, border: bdr, borderRadius: 6, padding: 2, gap: 2 }}>
    {options.map(opt => <button key={opt} onClick={() => onChange(opt)} style={{
      ...base, height: 24, padding: "0 10px", borderRadius: 4, fontSize: 12, border: "none", cursor: "pointer",
      fontWeight: value === opt ? 500 : 400,
      color: value === opt ? T.color.text : T.color.text2,
      background: value === opt ? T.color.surface : "transparent",
      boxShadow: value === opt ? T.shadow.xs : "none",
      transition: `all 120ms ${T.ease}`,
    }}>{labels[opt] || opt}</button>)}
  </div>;
}

/* ── FilterBar ── */
function FilterBar({ search, filters = [], actions }) {
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: T.radius.lg, padding: 12, marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", ...base }}>
    {search && <div style={{ position: "relative", width: 280 }}>
      <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}><Icon name="search" size={14} color={T.color.text3} /></span>
      <input placeholder={search} style={{ ...base, height: 28, width: "100%", padding: "0 10px 0 32px", border: bdr, borderRadius: 6, fontSize: 12, background: T.color.surface, color: T.color.text, outline: "none" }} />
    </div>}
    {filters.map((f, i) => <Btn key={i} variant="secondary" size="sm" icon={f.icon}>{f.label}</Btn>)}
    <div style={{ flex: 1 }} />
    {actions}
  </div>;
}

/* ── DataTable (mini demo) ── */
function DataTable({ columns, rows, loading, empty, error }) {
  const thStyle = { ...base, fontSize: 11, fontWeight: 500, letterSpacing: "0.04em", textTransform: "uppercase", color: T.color.text3, background: T.color.surface2, borderBottom: bdr, padding: "10px 14px", textAlign: "left", position: "sticky", top: 0, zIndex: 1 };
  const tdStyle = { ...base, padding: "10px 14px", borderBottom: bdr, fontSize: 13, color: T.color.text };
  if (loading) return <LoadingState type="table" />;
  if (error) return <ErrorState message={error} />;
  if (empty) return <EmptyState />;
  return <div style={{ border: bdr, borderRadius: 10, background: T.color.surface, overflow: "hidden" }}>
    <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
      <thead><tr>{columns.map((c, i) => <th key={i} style={{ ...thStyle, ...(c.numeric ? { textAlign: "right", fontVariantNumeric: "tabular-nums" } : {}) }}>{c.title}</th>)}</tr></thead>
      <tbody>{rows.map((row, ri) => <tr key={ri} style={{ transition: `background 120ms ${T.ease}` }} onMouseEnter={e => e.currentTarget.style.background = T.color.surface2} onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
        {columns.map((c, ci) => <td key={ci} style={{ ...tdStyle, ...(c.numeric ? { textAlign: "right", fontVariantNumeric: "tabular-nums", fontFamily: T.font.mono, fontSize: 12 } : {}), ...(ci === columns.length - 1 && ri === rows.length - 1 ? { borderBottom: "none" } : {}) }}>{c.render(row)}</td>)}
      </tr>)}</tbody>
    </table>
  </div>;
}

/* ── ProductRow (for table) ── */
function ProductCell({ sku, nmId, title, category }) {
  return <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
    <div style={{ width: 28, height: 28, borderRadius: 6, background: T.color.surface2, border: bdr, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: T.font.mono, fontSize: 9, color: T.color.text3, flexShrink: 0 }}>img</div>
    <div style={{ minWidth: 0 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
        <span style={{ fontFamily: T.font.mono, fontSize: 11, fontWeight: 500, color: T.color.text }}>{sku}</span>
        <span style={{ fontFamily: T.font.mono, fontSize: 10, color: T.color.text3 }}>{nmId}</span>
      </div>
      <div style={{ fontSize: 12, lineHeight: 1.3, color: T.color.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 300 }}>{title}</div>
      <div style={{ fontSize: 10, color: T.color.text3 }}>{category}</div>
    </div>
  </div>;
}

/* ── MetricCard ── */
function MetricCard({ label, value, delta, deltaTone = "neutral", compact }) {
  const toneColors = { success: T.color.success, danger: T.color.danger, neutral: T.color.text3 };
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: compact ? 12 : 20, flex: 1, minWidth: 130, ...base }}>
    <div style={{ fontSize: compact ? 11 : 12, color: T.color.text3, marginBottom: compact ? 6 : 8 }}>{label}</div>
    <div style={{ fontSize: compact ? 22 : 28, fontWeight: 600, color: T.color.text, lineHeight: T.leading.tight, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    {delta != null && <div style={{ fontSize: 12, fontFamily: T.font.mono, fontVariantNumeric: "tabular-nums", color: toneColors[deltaTone], marginTop: 4 }}>{delta}</div>}
  </div>;
}

/* ── ProjectCard ── */
function ProjectCard({ name, marketplaces = ["wb"], metrics = [], updatedAt }) {
  const mpColors = { wb: "wb", ozon: "ozon", ya: "default" };
  const mpLabels = { wb: "WB", ozon: "Ozon", ya: "YM" };
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: T.radius.lg, boxShadow: T.shadow.sm, padding: 20, cursor: "pointer", transition: `all 120ms ${T.ease}`, ...base }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
      <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em", color: T.color.text }}>{name}</span>
      {marketplaces.map(mp => <Badge key={mp} variant={mpColors[mp]}>{mpLabels[mp]}</Badge>)}
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

/* ── States ── */
function LoadingState({ type = "card" }) {
  const shimmer = { height: 10, borderRadius: 999, background: T.color.surface3, animation: "pulse 1.2s ease-in-out infinite" };
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: 20, minHeight: type === "table" ? 200 : 120, ...base }}>
    <style>{`@keyframes pulse { 0%,100%{opacity:.6} 50%{opacity:.3} }`}</style>
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ ...shimmer, width: "40%" }} />
      <div style={{ ...shimmer, width: "70%" }} />
      <div style={{ ...shimmer, width: "55%" }} />
      {type === "table" && <><div style={{ ...shimmer, width: "80%" }} /><div style={{ ...shimmer, width: "45%" }} /></>}
    </div>
  </div>;
}
function EmptyState({ title = "Нет данных", description = "По выбранным фильтрам ничего не найдено", action }) {
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: 40, minHeight: 180, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, textAlign: "center", ...base }}>
    <Icon name="box" size={32} color={T.color.text3} />
    <div style={{ fontSize: 14, fontWeight: 600, color: T.color.text }}>{title}</div>
    <div style={{ fontSize: 12, color: T.color.text2, maxWidth: 360 }}>{description}</div>
    {action || <Btn variant="secondary" size="sm">Сбросить фильтры</Btn>}
  </div>;
}
function ErrorState({ message = "Не удалось загрузить данные" }) {
  return <div style={{ background: T.color.surface, border: bdr, borderRadius: 10, padding: 40, minHeight: 160, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, textAlign: "center", ...base }}>
    <Icon name="alertCircle" size={32} color={T.color.danger} />
    <div style={{ fontSize: 14, fontWeight: 600, color: T.color.text }}>Ошибка</div>
    <div style={{ fontSize: 12, color: T.color.text2, maxWidth: 360 }}>{message}</div>
    <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
      <Btn variant="primary" size="sm" icon="refresh">Повторить</Btn>
      <Btn variant="ghost" size="sm">Подробнее</Btn>
    </div>
  </div>;
}

/* ══════════════════════════════════════════════
   MAIN SHOWCASE
   ══════════════════════════════════════════════ */

const NAV = [
  { id: "shell", label: "Shell", icon: "home" },
  { id: "nav", label: "Nav", icon: "modules" },
  { id: "data", label: "Данные", icon: "chart" },
  { id: "pages", label: "Страницы", icon: "box" },
  { id: "states", label: "Состояния", icon: "alertCircle" },
];

export default function DesignSystemV1() {
  const [section, setSection] = useState("shell");
  const [mp, setMp] = useState("wb");
  const [activeRail, setActiveRail] = useState("overview");
  const [activeSub, setActiveSub] = useState("data");

  const railItems = [
    { id: "overview", icon: "home", label: "Обзор" },
    { id: "wb", icon: "box", label: "WB", indicator: "green" },
    { id: "ozon", icon: "box", label: "Ozon" },
    { id: "modules", icon: "modules", label: "Модули", indicator: "purple" },
    "divider",
    { id: "compare", icon: "compare", label: "Сравн." },
    { id: "inbox", icon: "inbox", label: "Сигналы", badge: true },
    { id: "expenses", icon: "expenses", label: "Расходы" },
    "divider",
    { id: "settings", icon: "settings", label: "Настр." },
  ];

  const subItems = [
    { id: "data", icon: "chart", label: "Загрузка данных" },
    { id: "schedule", icon: "settings", label: "Расписание загрузки" },
    { id: "catalog", icon: "box", label: "Загрузка каталога" },
    { id: "stock", icon: "box", label: "Наличие данных", badge: 3, badgeTone: "warning" },
  ];

  const demoProducts = [
    { sku: "WB-4820", nmId: "174928301", title: "Футболка детская хлопок 100%", category: "Детская одежда", price: "890 ₽", rrp: "1 190 ₽", stock: 142 },
    { sku: "WB-4821", nmId: "174928302", title: "Платье летнее с принтом единорога", category: "Детская одежда", price: "1 290 ₽", rrp: "1 590 ₽", stock: 67 },
    { sku: "WB-4822", nmId: "174928303", title: "Комплект шорты + футболка морская тема", category: "Детская одежда", price: "1 490 ₽", rrp: "1 890 ₽", stock: 0 },
  ];

  return <div style={{ ...base, background: T.color.bg, minHeight: "100vh", color: T.color.text }}>
    {/* Showcase Topbar */}
    <div style={{ background: T.color.surface, borderBottom: bdr, padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em" }}>Ecomcore Design System</div>
        <div style={{ fontSize: 12, color: T.color.text2, marginTop: 2 }}>v1.0 · Nav B source of truth · Geist · oklch</div>
      </div>
      <div style={{ display: "flex", gap: 2 }}>
        {NAV.map(n => <button key={n.id} onClick={() => setSection(n.id)} style={{
          ...base, height: 28, padding: "0 12px", borderRadius: 6, fontSize: 12, border: "none", cursor: "pointer",
          fontWeight: section === n.id ? 500 : 400,
          color: section === n.id ? T.color.textOnDark : T.color.text2,
          background: section === n.id ? T.color.accent : "transparent",
          transition: `all 120ms ${T.ease}`,
        }}>{n.label}</button>)}
      </div>
    </div>

    <div style={{ padding: "32px 24px", maxWidth: 1000 }}>

      {/* ═══ SHELL ═══ */}
      {section === "shell" && <>
        <Section title="App Shell — Nav B" sub="Rail 76px + SubNav 220px + Topbar 52px. Интерактивная демо.">
          <div style={{ border: bdr, borderRadius: T.radius.lg, overflow: "hidden", height: 480, display: "flex", flexDirection: "column", background: T.color.bg }}>
            <Topbar breadcrumbs={["Проекты", "Zakka", "Настройки"]} userInitials="ПС" actions={<MarketplaceSwitch value={mp} onChange={setMp} />} />
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
              {/* Rail */}
              <div style={{ width: T.layout.railW, background: T.color.surface, borderRight: bdr, display: "flex", flexDirection: "column", flexShrink: 0 }}>
                <div style={{ height: T.layout.topbarH, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: T.color.accentSoft, color: T.color.accentText, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 700 }}>E</div>
                </div>
                <div style={{ paddingTop: 8, flex: 1 }}>
                  {railItems.map((item, i) => item === "divider"
                    ? <div key={i} style={{ height: 0.5, margin: "8px 14px", background: T.color.border }} />
                    : <RailItem key={item.id} {...item} active={activeRail === item.id} onClick={() => setActiveRail(item.id)} />
                  )}
                </div>
              </div>
              {/* SubNav */}
              <SubNav visible={activeRail === "wb" || activeRail === "ozon" || activeRail === "settings"} title={activeRail === "settings" ? "Настройки" : "Данные"}>
                {subItems.map(item => <SubNavItem key={item.id} {...item} active={activeSub === item.id} onClick={() => setActiveSub(item.id)} />)}
              </SubNav>
              {/* Content */}
              <div style={{ flex: 1, padding: "16px 20px", overflow: "auto" }}>
                <PageHeader title="Загрузка данных WB" eyebrow="Настройки" subtitle="Состояние и управление загрузками данных из Wildberries." tag={<Badge variant="wb">WB</Badge>} />
                <div style={{ fontSize: 12, color: T.color.text3 }}>← Кликайте по rail-пунктам. SubNav появляется для WB / Ozon / Настройки.</div>
              </div>
            </div>
          </div>
        </Section>

        <Section title="Layout dimensions" sub="Канонические размеры из Nav B.">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            {[
              ["Rail", "76px"], ["RailItem", "64×56px"], ["SubNav", "220px"], ["Topbar", "52px"],
              ["Content pad", "16px 20px"], ["Border", "0.5px"], ["Logo mark", "32×32px"], ["Rail label", "9px/600"],
            ].map(([label, val]) => <div key={label} style={{ background: T.color.surface, border: bdr, borderRadius: 6, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: T.color.text3, marginBottom: 2 }}>{label}</div>
              <div style={{ fontFamily: T.font.mono, fontSize: 13, fontWeight: 500 }}>{val}</div>
            </div>)}
          </div>
        </Section>
      </>}

      {/* ═══ NAV COMPONENTS ═══ */}
      {section === "nav" && <>
        <Section title="RailItem — состояния" sub="64×56, icon 18px, label 9px/600. Active = accentSoft bg + accentText color.">
          <Demo row gap={4}>
            <RailItem icon="home" label="Обзор" active />
            <RailItem icon="box" label="WB" indicator="green" />
            <RailItem icon="modules" label="Модули" indicator="purple" />
            <RailItem icon="inbox" label="Сигналы" badge />
            <RailItem icon="settings" label="Настр." />
          </Demo>
        </Section>

        <Section title="SubNavItem — состояния" sub="H 32px, icon 16px, text 13px. Active = inset 2px left accent border.">
          <div style={{ width: 220, background: T.color.surface, border: bdr, borderRadius: 6, padding: "8px" }}>
            <SubNavItem icon="chart" label="Загрузка данных" active />
            <SubNavItem icon="settings" label="Расписание" />
            <SubNavItem icon="box" label="Наличие данных" badge={3} badgeTone="warning" />
            <SubNavItem icon="box" label="Каталог" />
          </div>
        </Section>

        <Section title="MarketplaceSwitch" sub="Segmented control. Surface-2 bg, active = surface + shadow-xs.">
          <Demo row>
            <MarketplaceSwitch value={mp} options={["wb", "ozon", "ya"]} onChange={setMp} />
            <MarketplaceSwitch value="ozon" options={["wb", "ozon"]} onChange={() => {}} />
          </Demo>
        </Section>

        <Section title="Breadcrumbs" sub="12px, chevron separator, current = text, others = text2.">
          <Breadcrumbs items={["Проекты", "ИП Сидорова", "WB", "Расхождения цен"]} />
        </Section>

        <Section title="Badges" sub="Pill, 20px height, 11px.">
          <Demo row>
            <Badge>Default</Badge>
            <Badge variant="info">Info</Badge>
            <Badge variant="success">✓ Успешно</Badge>
            <Badge variant="warning">⚠ Внимание</Badge>
            <Badge variant="danger">✕ Ошибка</Badge>
            <Badge variant="wb">WB</Badge>
            <Badge variant="ozon">Ozon</Badge>
          </Demo>
        </Section>

        <Section title="Buttons" sub="Radius-sm (6px). Primary = accent, Secondary = surface + border + shadow-xs.">
          <Demo label="Варианты" row>
            <Btn variant="primary">Загрузить</Btn>
            <Btn variant="secondary">Экспорт</Btn>
            <Btn variant="ghost">Отмена</Btn>
            <Btn variant="danger">Удалить</Btn>
          </Demo>
          <Demo label="Размеры" row>
            <Btn size="sm">sm 28px</Btn>
            <Btn size="default">default 32px</Btn>
            <Btn size="lg">lg 40px</Btn>
            <Btn variant="secondary" size="sm" icon="filter">С иконкой</Btn>
          </Demo>
        </Section>
      </>}

      {/* ═══ DATA ═══ */}
      {section === "data" && <>
        <Section title="FilterBar" sub="Card wrapper, 12px padding. Search 280px + filter buttons + spacer + actions.">
          <FilterBar search="Поиск по SKU, названию..." filters={[{ label: "Статус", icon: "filter" }, { label: "Категория", icon: "filter" }]} actions={<Btn variant="secondary" size="sm">Столбцы</Btn>} />
        </Section>

        <Section title="DataTable" sub="0.5px borders, headers 11px uppercase, cells 10px 14px, hover surface2, sticky support.">
          <DataTable
            columns={[
              { title: "Товар", render: (r) => <ProductCell sku={r.sku} nmId={r.nmId} title={r.title} category={r.category} /> },
              { title: "Цена", numeric: true, render: (r) => r.price },
              { title: "РРЦ", numeric: true, render: (r) => r.rrp },
              { title: "Остаток", numeric: true, render: (r) => <span style={{ color: r.stock === 0 ? T.color.danger : T.color.text }}>{r.stock}</span> },
              { title: "Статус", render: (r) => r.stock === 0 ? <Badge variant="danger">Нет остатка</Badge> : <Badge variant="success">В наличии</Badge> },
            ]}
            rows={demoProducts}
          />
        </Section>

        <Section title="MetricCard" sub="Compact (12px pad, 22px value) и Large (20px pad, 28px value).">
          <Demo label="Compact (dashboard)">
            <div style={{ display: "flex", gap: 12 }}>
              <MetricCard label="Выручка" value="2.4М ₽" delta="+12%" deltaTone="success" compact />
              <MetricCard label="Заказы" value="1 230" delta="+8%" deltaTone="success" compact />
              <MetricCard label="Конверсия" value="4.2%" delta="−0.3" deltaTone="danger" compact />
            </div>
          </Demo>
          <Demo label="Large (detail page)">
            <div style={{ display: "flex", gap: 12 }}>
              <MetricCard label="Выручка за месяц" value="2.4М ₽" delta="+12%" deltaTone="success" />
              <MetricCard label="Заказов всего" value="1 230" delta="+8%" deltaTone="success" />
            </div>
          </Demo>
        </Section>

        <Section title="ProjectCard" sub="Card base, title 16px/600, metric values 20px/600, MP badges.">
          <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 700 }}>
            <ProjectCard name="ИП Сидорова / Fashion Kids" marketplaces={["wb", "ozon"]} updatedAt="2 часа назад" metrics={[{ label: "Карточки", value: "847" }, { label: "Выручка 7д", value: "2.4М ₽" }, { label: "Ошибки", value: "5", tone: "danger" }]} />
            <ProjectCard name="ООО Лайтхаус" marketplaces={["wb"]} updatedAt="вчера" metrics={[{ label: "Карточки", value: "312" }, { label: "Выручка 7д", value: "890К ₽" }]} />
          </div>
        </Section>
      </>}

      {/* ═══ PAGES ═══ */}
      {section === "pages" && <>
        <Section title="PageHeader" sub="Title 22px/600, eyebrow 11px uppercase, subtitle 12px text2.">
          <div style={{ background: T.color.surface, border: bdr, borderRadius: T.radius.lg, padding: 20 }}>
            <PageHeader title="Расхождения цен" eyebrow="WB · Отчёты" subtitle="Сравнение цен витрины с РРЦ и рекомендациями" tag={<Badge variant="wb">WB</Badge>} actions={<><Btn variant="secondary" size="sm">Экспорт</Btn><Btn size="sm">Применить РРЦ</Btn></>} />
          </div>
        </Section>

        <Section title="Report page pattern" sub="PageHeader → FilterBar → DataTable. Content padding: 16px 20px.">
          <div style={{ background: T.color.bg, border: bdr, borderRadius: T.radius.lg, padding: "16px 20px" }}>
            <PageHeader title="Загрузка данных WB" subtitle="Состояние и управление загрузками данных." actions={<MarketplaceSwitch value={mp} options={["wb", "ozon"]} onChange={setMp} />} />
            <FilterBar search="Поиск задач..." filters={[{ label: "Статус", icon: "filter" }]} />
            <DataTable
              columns={[
                { title: "Название", render: r => <span style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: r.ok ? T.color.success : T.color.danger }} />{r.name}</span> },
                { title: "Расписание", render: r => <span style={{ color: T.color.text2 }}>{r.schedule}</span> },
                { title: "Обновлено", numeric: true, render: r => r.updated },
                { title: "", render: () => <Btn variant="primary" size="sm">Загрузить</Btn> },
              ]}
              rows={[
                { name: "Загрузка цен с витрины", schedule: "ежедневно в 03:00", updated: "03:02:19", ok: true },
                { name: "Загрузка остатков FBS", schedule: "ежедневно в 05:00", updated: "05:00:01", ok: false },
                { name: "Загрузка каталога", schedule: "ежедневно в 02:00", updated: "02:00:21", ok: true },
              ]}
            />
          </div>
        </Section>
      </>}

      {/* ═══ STATES ═══ */}
      {section === "states" && <>
        <Section title="Loading" sub="Skeleton lines, 10-12px height, pill radius, surface3 bg, pulse 1.2s.">
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}><LoadingState type="card" /></div>
            <div style={{ flex: 1 }}><LoadingState type="table" /></div>
          </div>
        </Section>

        <Section title="Empty" sub="Centered, icon 32px text3, title 14px/600, desc 12px text2, action btn.">
          <EmptyState title="Нет товаров" description="По выбранным фильтрам ничего не найдено. Попробуйте изменить параметры поиска." />
        </Section>

        <Section title="Error" sub="Same card wrapper. Danger icon, title, message, retry + details actions.">
          <ErrorState message="Не удалось загрузить данные с Wildberries. Проверьте API-ключ в настройках." />
        </Section>
      </>}

    </div>
  </div>;
}
