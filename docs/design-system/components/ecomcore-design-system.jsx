import { useState } from "react";

const tokens = {
  colors: {
    bg: "oklch(98.5% 0.006 250)",
    surface: "oklch(100% 0 0)",
    surface2: "oklch(97% 0.008 250)",
    surface3: "oklch(94% 0.012 250)",
    border: "oklch(22% 0.03 260 / 0.15)",
    borderStrong: "oklch(22% 0.03 260 / 0.15)",
    text: "oklch(22% 0.03 260)",
    text2: "oklch(42% 0.02 260)",
    text3: "oklch(58% 0.015 260)",
    textOnDark: "oklch(98% 0.005 250)",
    accent: "oklch(38% 0.10 155)",
    accentHover: "oklch(32% 0.11 155)",
    accentSoft: "oklch(95% 0.04 155)",
    accentText: "oklch(36% 0.11 155)",
    info: "oklch(52% 0.18 245)",
    infoBg: "oklch(95% 0.04 245)",
    success: "oklch(56% 0.15 158)",
    successBg: "oklch(95% 0.05 158)",
    warning: "oklch(68% 0.16 70)",
    warningBg: "oklch(96% 0.06 75)",
    danger: "oklch(56% 0.20 22)",
    dangerBg: "oklch(96% 0.04 22)",
    mpWb: "oklch(58% 0.16 330)",
    mpWbBg: "oklch(96% 0.025 330)",
  },
  space: [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64],
  radius: { xs: 4, sm: 6, md: 8, lg: 10, xl: 14, pill: 999 },
  text: { xs: 11, sm: 12, base: 13, md: 14, lg: 16, xl: 20, "2xl": 24, "3xl": 32, "4xl": 44 },
  shadow: {
    xs: "0 1px 0 0 oklch(20% 0.01 75 / 0.04)",
    sm: "0 1px 2px oklch(20% 0.01 75 / 0.05), 0 1px 0 oklch(20% 0.01 75 / 0.03)",
    md: "0 4px 12px oklch(20% 0.01 75 / 0.06), 0 1px 0 oklch(20% 0.01 75 / 0.04)",
    lg: "0 12px 32px oklch(20% 0.01 75 / 0.08), 0 1px 0 oklch(20% 0.01 75 / 0.04)",
    focus: "0 0 0 3px oklch(38% 0.10 155 / 0.22)",
  },
};

const fontStack = '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif';
const monoStack = '"Geist Mono", ui-monospace, "JetBrains Mono", monospace';

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 40 }}>
      <h2
        style={{
          fontSize: 11,
          fontWeight: 500,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: tokens.colors.text3,
          marginBottom: 16,
          fontFamily: fontStack,
        }}
      >
        {title}
      </h2>
      {children}
    </div>
  );
}

function ColorSwatch({ name, value, dark }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 6,
          background: value,
          border: "0.5px solid oklch(22% 0.03 260 / 0.15)",
          flexShrink: 0,
        }}
      />
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text, fontFamily: fontStack }}>{name}</div>
        <div style={{ fontSize: 11, color: tokens.colors.text3, fontFamily: monoStack }}>{value}</div>
      </div>
    </div>
  );
}

function Btn({ variant = "primary", size = "default", children }) {
  const base = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 500,
    letterSpacing: "-0.005em",
    border: "0.5px solid transparent",
    cursor: "pointer",
    whiteSpace: "nowrap",
    fontFamily: fontStack,
    transition: "all 120ms cubic-bezier(0.2, 0.8, 0.2, 1)",
  };
  const sizes = {
    sm: { height: 28, padding: "0 8px", fontSize: 12 },
    default: { height: 32, padding: "0 10px" },
    lg: { height: 40, padding: "0 16px", fontSize: 14 },
  };
  const variants = {
    primary: { background: tokens.colors.accent, color: tokens.colors.textOnDark, borderColor: "transparent" },
    secondary: {
      background: tokens.colors.surface,
      color: tokens.colors.text,
      borderColor: tokens.colors.borderStrong,
      boxShadow: tokens.shadow.xs,
    },
    ghost: { background: "transparent", color: tokens.colors.text, borderColor: "transparent" },
    danger: { background: tokens.colors.danger, color: "white", borderColor: "transparent" },
  };
  return <button style={{ ...base, ...sizes[size], ...variants[variant] }}>{children}</button>;
}

function Badge({ variant = "default", children }) {
  const variants = {
    default: { background: tokens.colors.surface3, color: tokens.colors.text2, border: `0.5px solid ${tokens.colors.border}` },
    info: { background: tokens.colors.infoBg, color: tokens.colors.info, border: "0.5px solid transparent" },
    success: { background: tokens.colors.successBg, color: "oklch(34% 0.12 158)", border: "0.5px solid transparent" },
    warning: { background: tokens.colors.warningBg, color: "oklch(45% 0.12 75)", border: "0.5px solid transparent" },
    danger: { background: tokens.colors.dangerBg, color: "oklch(36% 0.16 22)", border: "0.5px solid transparent" },
    wb: { background: tokens.colors.mpWbBg, color: tokens.colors.mpWb, border: "0.5px solid transparent" },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        height: 20,
        padding: "0 7px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: "0.01em",
        fontFamily: fontStack,
        ...variants[variant],
      }}
    >
      {children}
    </span>
  );
}

function InputDemo() {
  const [focused, setFocused] = useState(false);
  return (
    <input
      placeholder="Поиск товаров..."
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 32,
        padding: "0 10px",
        background: tokens.colors.surface,
        border: `0.5px solid ${focused ? tokens.colors.info : tokens.colors.borderStrong}`,
        borderRadius: 6,
        fontSize: 13,
        color: tokens.colors.text,
        width: 240,
        outline: "none",
        fontFamily: fontStack,
        boxShadow: focused ? tokens.shadow.focus : "none",
        transition: "all 120ms cubic-bezier(0.2, 0.8, 0.2, 1)",
      }}
    />
  );
}

function MiniTable() {
  const data = [
    { name: "Загрузка цен с витрины", schedule: "ежедневно в 03:00", status: "success", time: "13.05.2026, 03:02:19" },
    { name: "Загрузка остатков FBS", schedule: "ежедневно в 05:00", status: "danger", time: "13.05.2026, 05:00:01" },
    { name: "Загрузка каталога товаров", schedule: "ежедневно в 02:00", status: "success", time: "13.05.2026, 02:00:21" },
  ];
  const thStyle = {
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    color: tokens.colors.text3,
    background: tokens.colors.surface2,
    borderBottom: `0.5px solid ${tokens.colors.border}`,
    padding: "10px 14px",
    textAlign: "left",
    fontFamily: fontStack,
  };
  const tdStyle = {
    padding: "10px 14px",
    borderBottom: `0.5px solid ${tokens.colors.border}`,
    fontSize: 13,
    color: tokens.colors.text,
    fontFamily: fontStack,
  };
  return (
    <div
      style={{
        border: `0.5px solid ${tokens.colors.border}`,
        borderRadius: 10,
        background: tokens.colors.surface,
        overflow: "hidden",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0, tableLayout: "fixed" }}>
        <thead>
          <tr>
            <th style={thStyle}>Название</th>
            <th style={thStyle}>Расписание</th>
            <th style={thStyle}>Статус</th>
            <th style={thStyle}>Обновлено</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} style={{ transition: "background 120ms" }}>
              <td style={tdStyle}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: row.status === "success" ? tokens.colors.success : tokens.colors.danger,
                    }}
                  />
                  {row.name}
                </span>
              </td>
              <td style={{ ...tdStyle, color: tokens.colors.text2 }}>{row.schedule}</td>
              <td style={tdStyle}>
                <Badge variant={row.status}>{row.status === "success" ? "✓ Успешно" : "✕ Ошибка"}</Badge>
              </td>
              <td style={{ ...tdStyle, fontFamily: monoStack, fontSize: 12, color: tokens.colors.text2 }}>{row.time}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KpiCard({ label, value, delta, positive }) {
  return (
    <div
      style={{
        background: tokens.colors.surface,
        border: `0.5px solid ${tokens.colors.border}`,
        borderRadius: 10,
        padding: 20,
        flex: 1,
        minWidth: 140,
      }}
    >
      <div style={{ fontSize: 12, color: tokens.colors.text2, marginBottom: 8, fontFamily: fontStack }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, color: tokens.colors.text, fontFamily: fontStack, lineHeight: 1.15 }}>
        {value}
      </div>
      <div
        style={{
          fontSize: 12,
          fontWeight: 500,
          color: positive ? tokens.colors.success : tokens.colors.danger,
          marginTop: 4,
          fontFamily: fontStack,
        }}
      >
        {delta}
      </div>
    </div>
  );
}

function AlertCard({ mp, color, text, count, countColor }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "12px 16px",
        background: tokens.colors.surface,
        border: `0.5px solid ${tokens.colors.border}`,
        borderRadius: 10,
        fontFamily: fontStack,
      }}
    >
      <Badge variant={mp === "WB" ? "wb" : "info"}>{mp}</Badge>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ flex: 1, fontSize: 13, color: tokens.colors.text }}>{text}</span>
      <Badge variant={countColor || "danger"}>{count}</Badge>
    </div>
  );
}

function SegmentedControl({ items, active, onChange }) {
  return (
    <div
      style={{
        display: "inline-flex",
        background: tokens.colors.surface2,
        border: `0.5px solid ${tokens.colors.border}`,
        borderRadius: 6,
        padding: 2,
        gap: 2,
      }}
    >
      {items.map((item) => (
        <button
          key={item}
          onClick={() => onChange(item)}
          style={{
            height: 24,
            padding: "0 10px",
            borderRadius: 4,
            fontSize: 12,
            fontWeight: active === item ? 500 : 400,
            color: active === item ? tokens.colors.text : tokens.colors.text2,
            background: active === item ? tokens.colors.surface : "transparent",
            boxShadow: active === item ? tokens.shadow.xs : "none",
            border: "none",
            cursor: "pointer",
            fontFamily: fontStack,
            transition: "all 120ms",
          }}
        >
          {item}
        </button>
      ))}
    </div>
  );
}

function TabsDemo() {
  const [active, setActive] = useState("Обзор");
  const tabs = ["Обзор", "Товары", "Аналитика", "Настройки"];
  return (
    <div style={{ display: "flex", gap: 2, borderBottom: `0.5px solid ${tokens.colors.border}` }}>
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => setActive(tab)}
          style={{
            height: 36,
            padding: "0 12px",
            fontSize: 13,
            fontWeight: active === tab ? 500 : 400,
            color: active === tab ? tokens.colors.text : tokens.colors.text2,
            borderBottom: `2px solid ${active === tab ? tokens.colors.text : "transparent"}`,
            marginBottom: -1,
            background: "none",
            border: "none",
            borderBottomStyle: "solid",
            borderBottomWidth: 2,
            borderBottomColor: active === tab ? tokens.colors.text : "transparent",
            cursor: "pointer",
            fontFamily: fontStack,
            transition: "all 120ms",
          }}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

export default function EcomcoreDesignSystem() {
  const [seg, setSeg] = useState("WB");
  const [activeSection, setActiveSection] = useState("all");

  const sections = [
    { id: "all", label: "Все" },
    { id: "colors", label: "Цвета" },
    { id: "type", label: "Типографика" },
    { id: "components", label: "Компоненты" },
    { id: "patterns", label: "Паттерны" },
  ];

  const show = (id) => activeSection === "all" || activeSection === id;

  return (
    <div
      style={{
        fontFamily: fontStack,
        background: tokens.colors.bg,
        color: tokens.colors.text,
        minHeight: "100vh",
        WebkitFontSmoothing: "antialiased",
        textRendering: "optimizeLegibility",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: tokens.colors.surface,
          borderBottom: `0.5px solid ${tokens.colors.border}`,
          padding: "20px 32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.02em" }}>Ecomcore — Design System</div>
          <div style={{ fontSize: 12, color: tokens.colors.text2, marginTop: 4 }}>
            Foundations v1.0 · Geist · oklch · 4px grid
          </div>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id)}
              style={{
                height: 28,
                padding: "0 10px",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: activeSection === s.id ? 500 : 400,
                color: activeSection === s.id ? tokens.colors.textOnDark : tokens.colors.text2,
                background: activeSection === s.id ? tokens.colors.accent : "transparent",
                border: activeSection === s.id ? "none" : `0.5px solid transparent`,
                cursor: "pointer",
                fontFamily: fontStack,
                transition: "all 120ms",
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: "32px 32px", maxWidth: 960 }}>
        {/* Colors */}
        {show("colors") && (
          <Section title="Цвета — палитра">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: tokens.colors.text2, marginBottom: 12 }}>
                  Нейтральные
                </div>
                <ColorSwatch name="bg" value={tokens.colors.bg} />
                <ColorSwatch name="surface" value={tokens.colors.surface} />
                <ColorSwatch name="surface-2" value={tokens.colors.surface2} />
                <ColorSwatch name="surface-3" value={tokens.colors.surface3} />
                <ColorSwatch name="text" value={tokens.colors.text} />
                <ColorSwatch name="text-2" value={tokens.colors.text2} />
                <ColorSwatch name="text-3" value={tokens.colors.text3} />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: tokens.colors.text2, marginBottom: 12 }}>
                  Акцент (forest green)
                </div>
                <ColorSwatch name="accent" value={tokens.colors.accent} />
                <ColorSwatch name="accent-hover" value={tokens.colors.accentHover} />
                <ColorSwatch name="accent-soft" value={tokens.colors.accentSoft} />
                <ColorSwatch name="accent-text" value={tokens.colors.accentText} />
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: tokens.colors.text2, marginBottom: 12 }}>
                  Семантические
                </div>
                <ColorSwatch name="info" value={tokens.colors.info} />
                <ColorSwatch name="success" value={tokens.colors.success} />
                <ColorSwatch name="warning" value={tokens.colors.warning} />
                <ColorSwatch name="danger" value={tokens.colors.danger} />
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, color: tokens.colors.text2, marginBottom: 8 }}>МП</div>
                  <ColorSwatch name="WB (magenta)" value={tokens.colors.mpWb} />
                </div>
              </div>
            </div>
          </Section>
        )}

        {/* Typography */}
        {show("type") && (
          <Section title="Типографика — шкала">
            <div
              style={{
                background: tokens.colors.surface,
                border: `0.5px solid ${tokens.colors.border}`,
                borderRadius: 10,
                padding: 24,
              }}
            >
              {Object.entries(tokens.text).map(([name, size]) => (
                <div
                  key={name}
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 16,
                    padding: "8px 0",
                    borderBottom: `0.5px solid ${tokens.colors.border}`,
                  }}
                >
                  <span style={{ width: 60, fontSize: 11, color: tokens.colors.text3, fontFamily: monoStack }}>
                    {name}
                  </span>
                  <span style={{ width: 40, fontSize: 11, color: tokens.colors.text3, fontFamily: monoStack }}>
                    {size}px
                  </span>
                  <span style={{ fontSize: size, fontWeight: name === "3xl" || name === "4xl" ? 700 : 400 }}>
                    Выручка 2.4M ₽
                  </span>
                </div>
              ))}
              <div style={{ marginTop: 16, display: "flex", gap: 24 }}>
                <div>
                  <span style={{ fontSize: 11, color: tokens.colors.text3 }}>Tabular nums: </span>
                  <span style={{ fontVariantNumeric: "tabular-nums", fontFamily: fontStack }}>
                    1,234,567.89
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: tokens.colors.text3 }}>Mono: </span>
                  <span style={{ fontFamily: monoStack, fontSize: 13 }}>SKU-4820174</span>
                </div>
              </div>
            </div>
          </Section>
        )}

        {/* Components */}
        {show("components") && (
          <>
            <Section title="Кнопки">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <Btn variant="primary">Загрузить сейчас</Btn>
                <Btn variant="secondary">Экспорт</Btn>
                <Btn variant="ghost">Отмена</Btn>
                <Btn variant="danger">Удалить</Btn>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
                <Btn variant="primary" size="sm">sm — 28px</Btn>
                <Btn variant="primary" size="default">default — 32px</Btn>
                <Btn variant="primary" size="lg">lg — 40px</Btn>
              </div>
            </Section>

            <Section title="Бейджи">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <Badge>Default</Badge>
                <Badge variant="info">Info</Badge>
                <Badge variant="success">✓ Успешно</Badge>
                <Badge variant="warning">⚠ Внимание</Badge>
                <Badge variant="danger">✕ Ошибка</Badge>
                <Badge variant="wb">WB</Badge>
              </div>
            </Section>

            <Section title="Инпут">
              <InputDemo />
            </Section>

            <Section title="Segmented Control">
              <SegmentedControl items={["WB", "Ozon", "YM"]} active={seg} onChange={setSeg} />
            </Section>

            <Section title="Табы">
              <TabsDemo />
            </Section>

            <Section title="Скругления и тени">
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                {Object.entries(tokens.radius)
                  .filter(([k]) => k !== "pill")
                  .map(([name, val]) => (
                    <div
                      key={name}
                      style={{
                        width: 72,
                        height: 72,
                        background: tokens.colors.surface,
                        border: `0.5px solid ${tokens.colors.border}`,
                        borderRadius: val,
                        boxShadow: tokens.shadow.sm,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 11,
                        color: tokens.colors.text2,
                        fontFamily: monoStack,
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{name}</div>
                      <div>{val}px</div>
                    </div>
                  ))}
              </div>
            </Section>
          </>
        )}

        {/* Patterns */}
        {show("patterns") && (
          <>
            <Section title="Таблица — загрузка данных WB">
              <MiniTable />
            </Section>

            <Section title="KPI-карточки — пульс проекта">
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                <KpiCard label="Выручка" value="2.4М ₽" delta="+12%" positive />
                <KpiCard label="Заказы" value="1 230" delta="+8%" positive />
                <KpiCard label="Конверсия" value="4.2%" delta="−0.3" positive={false} />
              </div>
            </Section>

            <Section title="Алерт-карточки — требует внимания">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <AlertCard mp="WB" color={tokens.colors.danger} text="Нулевые остатки" count="5 SKU" countColor="danger" />
                <AlertCard mp="WB" color={tokens.colors.warning} text="Расхождения цен" count="2" countColor="warning" />
                <AlertCard mp="WB" color={tokens.colors.info} text="Гипотеза завершена — нужно решение" count="1" countColor="info" />
              </div>
            </Section>

            <Section title="Стадии карточек">
              <div style={{ display: "flex", gap: 6 }}>
                <Badge variant="danger">Launch 42</Badge>
                <Badge variant="success">Growth 680</Badge>
                <Badge variant="default">Defend 125</Badge>
              </div>
            </Section>
          </>
        )}

        {/* Spacing */}
        {show("components") && (
          <Section title="Пространство — сетка 4px">
            <div style={{ display: "flex", gap: 4, alignItems: "flex-end" }}>
              {tokens.space.filter((s) => s > 0).map((s) => (
                <div key={s} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                  <div
                    style={{
                      width: s,
                      height: s,
                      background: tokens.colors.accentSoft,
                      border: `0.5px solid ${tokens.colors.accent}`,
                      borderRadius: 2,
                    }}
                  />
                  <span style={{ fontSize: 10, color: tokens.colors.text3, fontFamily: monoStack }}>{s}</span>
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
