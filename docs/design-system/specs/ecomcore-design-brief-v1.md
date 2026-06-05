# Ecomcore — Design Brief v1.0 (Nav B)

> Источник истины: `Nav B - Rail + sub-nav` + `ecomcore-ui-overrides`.
> Вставляй этот документ в начало каждого чата по UI ecomcore.

---

## Продукт

Ecomcore — SaaS для управления продажами на маркетплейсах (WB, Ozon, YM). Десктопная админка, пользователи — e-commerce менеджеры. Светлая тема.

## Шрифт

**Sans:** `"Geist", "Inter", ui-sans-serif, system-ui, sans-serif`
**Mono:** `"Geist Mono", ui-monospace, "JetBrains Mono", monospace`
**Features:** `"cv11", "ss01", "ss03"`, tabular-nums для числовых колонок.
Рендер: antialiased, optimizeLegibility.

## Типографика

| Токен | px | Где |
|-------|-----|-----|
| xs | 11 | Заголовки таблиц (uppercase 0.04em), eyebrow, лейблы метрик |
| sm | 12 | Подписи, breadcrumbs, delta, категории, filter buttons |
| base | 13 | Основной текст, ячейки таблиц, SubNavItem text |
| md | 14 | Empty/error title, body emphasis |
| lg | 16 | ProjectCard title |
| xl | 20 | ProjectCard metric values |
| 2xl | 24 | — резерв |
| 3xl | 32 | — резерв (hero KPI при необходимости) |

**Page title: 22px, weight 600, letter-spacing −0.02em, line-height 1.1.**
Eyebrow: 10-11px, uppercase, letter-spacing 0.08em, weight 600, color text3.
RailItem label: 9px, weight 600, letter-spacing 0.02em.
Line-height: tight 1.15, snug 1.3, base 1.5.
Weights: regular 400, medium 500, semibold 600, bold 700.

## Цвета (oklch)

### Нейтральные
- **bg** `oklch(98.5% 0.006 250)` — фон страницы
- **surface** `oklch(100% 0 0)` — карточки, rail, topbar, инпуты
- **surface-2** `oklch(97% 0.008 250)` — hover, подложки, segmented bg
- **surface-3** `oklch(94% 0.012 250)` — активные подложки, skeleton
- **border** `oklch(22% 0.03 260 / 0.15)` — все бордеры и разделители
- **text** `oklch(22% 0.03 260)` — основной текст
- **text-2** `oklch(42% 0.02 260)` — вторичный текст
- **text-3** `oklch(58% 0.015 260)` — placeholder, подсказки

### Акцент (forest green)
- **accent** `oklch(38% 0.10 155)` — primary buttons
- **accent-hover** `oklch(32% 0.11 155)` — hover primary
- **accent-soft** `oklch(95% 0.04 155)` — активный RailItem/SubNavItem bg, pill filter active
- **accent-text** `oklch(36% 0.11 155)` — активный RailItem/SubNavItem text, ссылки

### Семантические
- **info** `oklch(52% 0.18 245)` / bg `oklch(95% 0.04 245)`
- **success** `oklch(56% 0.15 158)` / bg `oklch(95% 0.05 158)`
- **warning** `oklch(68% 0.16 70)` / bg `oklch(96% 0.06 75)`
- **danger** `oklch(56% 0.20 22)` / bg `oklch(96% 0.04 22)`

### Маркетплейсы
- **WB** `oklch(58% 0.16 330)` / bg `oklch(96% 0.025 330)`
- **Ozon** `oklch(45% 0.14 250)` / bg `oklch(96% 0.025 250)`
- **YM** `oklch(45% 0.14 60)` / bg `oklch(96% 0.025 60)`

## Пространство (4px grid)

0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 px.

## Скругления

xs 4 · sm 6 · md 8 · lg 10 · xl 14 · pill 999.

## Тени

- **xs** `0 1px 0 0 oklch(20% 0.01 75 / 0.04)` — кнопки secondary
- **sm** `0 1px 2px oklch(20% 0.01 75 / 0.05), 0 1px 0 oklch(20% 0.01 75 / 0.03)` — карточки
- **md** `0 4px 12px oklch(20% 0.01 75 / 0.06), …` — поповеры
- **focus** `0 0 0 3px oklch(38% 0.10 155 / 0.22)` — кольцо фокуса

## Бордеры

Везде: `0.5px solid var(--color-border)`. Это override-контракт Nav B.

## Анимации

ease-out: `cubic-bezier(0.2, 0.8, 0.2, 1)`. Fast 120ms, base 180ms, slow 280ms.

---

## Shell — Nav B Layout

### Размеры
- **Rail:** 76px ширина, surface bg, right border 0.5px (когда subnav открыт)
- **SubNav:** 220px (animated 0→220, transition: width 150ms ease-out, opacity 120ms)
- **Topbar:** 52px высота, surface bg, bottom border 0.5px, padding 0 20px
- **Logo area:** высота 52px, mark 32×32, radius 8, accent-soft bg, accent-text color, 14px/700
- **Content padding:** 16px 20px

### RailItem
- Размер: 64×56, margin 2px 6px, radius 10px
- Icon: 18px, label: 9px/600, letter-spacing 0.02em
- Default: color text-2, bg transparent
- **Active: color accent-text, bg accent-soft, box-shadow inset 0 0 0 0.5px border**
- Indicator dot: 7×7, top 8px right 12px, shadow 0 0 0 2px surface. Green = success, purple = oklch(58% 0.16 305)
- Badge dot: та же геометрия, bg danger

### SubNavItem
- Высота 32px, padding 0 10px, gap 10px, radius 6px
- Icon 16px, text 13px
- Default: color text-2, bg transparent, weight 400
- Hover: bg surface-2
- **Active: color accent-text, bg accent-soft, weight 600, box-shadow inset 2px 0 0 accent**
- Badge: mono 10px/600, pill, min-width 18px

### Topbar
- Высота 52px, surface bg, bottom border 0.5px
- Padding 0 20px
- Right icons: ghost sm btn-icon
- User: pill, surface-2 bg, avatar 22-24px

### Breadcrumbs
- Font 12px. Separator: chevron-right 12px, color text-3
- Non-current: text-2. Current: text

---

## Компоненты

### PageHeader
- Title: **22px/600, letter-spacing −0.02em, line-height 1.1**
- Eyebrow: 10-11px uppercase, letter-spacing 0.08em, weight 600, color text-3
- Subtitle: 12px, color text-2, margin-top 4px
- Layout: flex row, align-items flex-end, justify-content space-between, gap 16px, mb 16px

### Buttons
- Primary: accent bg, textOnDark color
- Secondary: surface bg, border 0.5px, shadow-xs
- Ghost: transparent, border transparent
- Danger: danger bg, white text
- Все: radius-sm (6px), weight 500, letter-spacing −0.005em
- Размеры: sm 28px, default 32px, lg 40px

### Badges
- Pill shape (radius 999), height 20px, font 11px/500
- Варианты: default (surface3), info, success, warning, danger, wb, ozon

### MarketplaceSwitch
- Segmented: surface-2 bg, border 0.5px, radius 6px, padding 2px
- Button height 24px, font 12px
- Active: surface bg, text color, shadow-xs

### FilterBar
- Card wrapper: surface bg, border 0.5px, radius-lg, padding 12px, mb 12px
- Layout: row flex, gap 8px, flex-wrap
- Search: input 280px, inner icon 14px
- Filter buttons: secondary sm
- Pill filter active: accent-soft bg, accent-text color, no heavy border

### DataTable
- Wrapper: border 0.5px, radius 10px, surface bg, overflow-x auto
- Headers: 11px/500, uppercase, 0.04em spacing, color text-3, bg surface-2
- Cells: padding 10px 14px, border-bottom 0.5px
- Row hover: bg surface-2
- Numeric: tabular-nums, text-align right, mono для SKU/цен
- Sticky columns: position sticky, bg surface, z-index 3; sticky header z-index 5

### ProductRow
- Checkbox: 18×18, radius 5px, border 1.5px border-strong
- Thumbnail: 28×28, radius 6px, border 0.5px
- SKU: mono 11px/500. nmID: mono 10px text-3
- Title: 12px, line-height 1.3, ellipsis
- Category: 10px, text-3

### MetricCard
- Surface bg, border 0.5px, radius 10px
- Compact: padding 12px, value 22px/600
- Large: padding 20px, value 26-32px
- Label: 11-12px, text-2/text-3
- Delta: 12px, mono, tabular-nums, success/danger color

### ProjectCard
- Card base: surface, border 0.5px, radius-lg, shadow-sm, padding 18-20px
- Title: 16px/600, letter-spacing −0.01em
- MP badges: MarketplaceTag
- Metric label: 11px text-3, value: 20px/600 tabular-nums
- Hover: bg → surface-2, border → borderStrong

---

## Состояния

### Loading
- Контейнер сохраняет финальный размер (нет layout shift)
- Skeleton line: height 10-12px, radius pill, bg surface-3
- Shimmer: gradient surface-2→surface-3, duration 1200ms
- Row height = density (32px compact, 40px default)

### Empty
- Card/table-wrap wrapper, min-height 160-220px
- Centered: icon 32px text-3, title 14px/600 text, desc 12px text-2 max-w 360px
- Optional action: secondary btn sm/default

### Error
- Card wrapper, border 0.5px (не ярко-красный)
- Icon/dot: danger color
- Title: 14px/600. Message: 12px text-2
- Actions: «Повторить» primary/secondary + «Подробнее» ghost

---

## Density

| | Row | Control | Control px | Card pad | Text |
|---|---|---|---|---|---|
| Default | 40px | 32px | 10px | 20px | 13px |
| Compact | 32px | 28px | 8px | 16px | 12px |
| Comfortable | 48px | 36px | 12px | 24px | 14px |

---

## RRP Report Column Widths (reference)

select 44 · photo 58 · sku 110 · title 430 · price 90 · rrp 90 · vitrina 90 · discount 84 · deltaRrp 74 · recommendation 104 · stock 76 · actions 32.
Sticky left offsets: select 0, photo 44, sku 102, title 212.

---

## Правила

1. Не пересоздавать rail/subnav приблизительным CSS. Использовать точные контракты RailNav, RailItem, SubNav, SubNavItem.
2. Page mockups включают shell с тем же контрактом.
3. Компоненты не из Nav B (например ProjectCard) выводить из .card + MarketplaceTag + MetricCard, не изобретая новый визуальный язык.
4. Все бордеры — 0.5px. Никаких 1px.
5. Иконки — Lucide, 18px в rail, 16px в subnav/кнопках, 14px в filter inputs.
