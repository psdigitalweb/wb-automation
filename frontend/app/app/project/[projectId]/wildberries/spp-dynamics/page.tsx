'use client'

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { apiGetData } from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import styles from './spp-dynamics.module.css'

const PAGE_SIZE = 50

interface SppSummary {
  period: { date_from: string; date_to: string }
  total_products: number
  products_with_spp: number
  products_with_events: number
  events_count: number
  avg_spp_start: number | null
  avg_spp_end: number | null
  max_abs_delta_spp: number | null
}

interface SppItem {
  nm_id: number
  vendor_code: string | null
  name: string | null
  category: string | null
  subject_name: string | null
  photos: string[]
  first_spp_percent: number | null
  last_spp_percent: number | null
  delta_spp: number | null
  abs_delta_spp: number | null
  min_spp_percent: number | null
  avg_spp_percent: number | null
  max_spp_percent: number | null
  points_count: number
  events_count: number
  max_event_delta: number | null
  last_changed_at: string | null
  rrc: number | null
  wb_price: number | null
  first_price_showcase: number | null
  last_price_showcase: number | null
}

interface SppItemsResponse {
  period: { date_from: string; date_to: string }
  items: SppItem[]
  meta: { total: number; limit: number; offset: number; sort: string }
}

interface CategoryOption {
  id: number
  name: string | null
}

interface SeriesPoint {
  snapshot_at: string
  spp_percent: number | null
  price_showcase: number | null
}

interface AdminPricePoint {
  created_at: string
  wb_price: number | null
}

interface SeriesEvent {
  changed_at: string
  prev_spp_percent: number | null
  spp_percent: number
  ingest_run_id: number | null
}

interface SalesPoint {
  date: string
  units_sold: number
  gross_sales: number
}

type ChangeKind = 'spp' | 'showcase' | 'admin'
interface TimelineChange {
  id: string
  kind: ChangeKind
  at: string
  label: string
  previous: string
  current: string
}

interface SppShowcaseChangeRow {
  at: string
  spp: TimelineChange | null
  showcase: TimelineChange | null
}

interface SppSeriesResponse {
  product: {
    nm_id: number
    vendor_code: string | null
    name: string | null
    category: string | null
    subject_name: string | null
  }
  points: SeriesPoint[]
  admin_price_points: AdminPricePoint[]
  events: SeriesEvent[]
  sales_daily: SalesPoint[]
}

interface FiltersState {
  dateFrom: string
  dateTo: string
  q: string
  categoryIds: number[]
  onlyChanged: boolean
  hasSppPeriod: boolean
  hasSppToday: boolean
  minDelta: number
  sort: string
  page: number
}

function isoDateDaysAgo(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date.toISOString().slice(0, 10)
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

function parseCategoryIdsParam(value: string | null): number[] {
  if (!value) return []
  return value
    .split(',')
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isFinite(value))
}

function buildCategoryIdsParam(ids: number[]): string | null {
  if (!ids.length) return null
  return ids.join(',')
}

function parseFilters(searchParams: URLSearchParams): FiltersState {
  const page = Number(searchParams.get('page') || '1')
  const minDelta = Number(searchParams.get('min_delta') || '0')

  return {
    dateFrom: searchParams.get('date_from') || isoDateDaysAgo(30),
    dateTo: searchParams.get('date_to') || todayIsoDate(),
    q: searchParams.get('q') || '',
    categoryIds: parseCategoryIdsParam(searchParams.get('category_ids')),
    onlyChanged: searchParams.get('only_changed') === 'true',
    hasSppPeriod: searchParams.get('has_spp_period') === 'true',
    hasSppToday: searchParams.get('has_spp_today') === 'true',
    minDelta: Number.isNaN(minDelta) || minDelta < 0 ? 0 : minDelta,
    sort: searchParams.get('sort') || 'delta_desc',
    page: Number.isNaN(page) || page < 1 ? 1 : page,
  }
}

function appendSppAvailabilityParams(qs: URLSearchParams, filters: FiltersState) {
  if (filters.hasSppPeriod) qs.set('has_spp_period', 'true')
  if (filters.hasSppToday) {
    qs.set('has_spp_today', 'true')
    qs.set('spp_today_date', todayIsoDate())
  }
}

function toApiDateStart(date: string): string {
  return `${date}T00:00:00Z`
}

function toApiDateEnd(date: string): string {
  return `${date}T23:59:59Z`
}

function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('ru-RU').format(value)
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`
}

function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  if (value === 0) return '0 п.п.'
  return `${value > 0 ? '+' : ''}${value} п.п.`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatShortDate(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
  }).format(date)
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function deltaClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return styles.deltaNeutral
  return value > 0 ? styles.deltaUp : styles.deltaDown
}

function buildValueChanges<T>(
  rows: T[],
  getTime: (row: T) => string,
  getValue: (row: T) => number | null,
  formatValue: (value: number | null | undefined) => string,
  kind: ChangeKind,
  label: string,
): TimelineChange[] {
  const valid = rows
    .map((row) => ({ at: getTime(row), value: getValue(row) }))
    .filter((row): row is { at: string; value: number } => row.value !== null && row.value !== undefined)
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())

  const changes: TimelineChange[] = []
  for (let idx = 1; idx < valid.length; idx += 1) {
    const previous = valid[idx - 1]
    const current = valid[idx]
    if (previous.value === current.value) continue
    changes.push({
      id: `${kind}-${current.at}-${idx}`,
      kind,
      at: current.at,
      label,
      previous: formatValue(previous.value),
      current: formatValue(current.value),
    })
  }
  return changes
}

function buildTimelineChanges(series: SppSeriesResponse): TimelineChange[] {
  const sppChanges = series.events.map((event, idx) => ({
    id: `spp-${event.changed_at}-${idx}`,
    kind: 'spp' as const,
    at: event.changed_at,
    label: 'СПП',
    previous: formatPercent(event.prev_spp_percent),
    current: formatPercent(event.spp_percent),
  }))

  const showcaseChanges = buildValueChanges(
    series.points,
    (point) => point.snapshot_at,
    (point) => point.price_showcase,
    formatCurrency,
    'showcase',
    'Витрина',
  )
  const adminChanges = buildValueChanges(
    series.admin_price_points || [],
    (point) => point.created_at,
    (point) => point.wb_price,
    formatCurrency,
    'admin',
    'Цена WB',
  )

  return [...sppChanges, ...showcaseChanges, ...adminChanges].sort(
    (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime(),
  )
}

interface FiltersProps {
  filters: FiltersState
  categories: CategoryOption[]
  onChange: (patch: Partial<FiltersState>) => void
}

function SppFilters({ filters, categories, onChange }: FiltersProps) {
  const [qInput, setQInput] = useState(filters.q)

  useEffect(() => {
    setQInput(filters.q)
  }, [filters.q])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (qInput !== filters.q) onChange({ q: qInput, page: 1 })
    }, 350)
    return () => window.clearTimeout(handle)
  }, [filters.q, onChange, qInput])

  return (
    <section className={styles.filterToolbar} aria-label="Фильтры">
      <label className={styles.field}>
        <span>Период с</span>
        <input
          type="date"
          value={filters.dateFrom}
          onChange={(event) => onChange({ dateFrom: event.target.value, page: 1 })}
        />
      </label>
      <label className={styles.field}>
        <span>по</span>
        <input
          type="date"
          value={filters.dateTo}
          onChange={(event) => onChange({ dateTo: event.target.value, page: 1 })}
        />
      </label>
      <label className={styles.searchControl}>
        <span aria-hidden="true">⌕</span>
        <input
          type="search"
          placeholder="Артикул, nmID, категория"
          value={qInput}
          onChange={(event) => setQInput(event.target.value)}
        />
      </label>
      <label className={styles.field}>
        <span>Категория WB</span>
        <select
          value={filters.categoryIds[0] ? String(filters.categoryIds[0]) : ''}
          onChange={(event) => {
            const value = event.target.value
            onChange({ categoryIds: value ? [Number(value)] : [], page: 1 })
          }}
          disabled={categories.length === 0}
        >
          <option value="">{categories.length ? 'Все категории' : 'Нет категорий'}</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name || `Категория ${category.id}`}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        <span>Мин. изменение</span>
        <input
          type="number"
          min="0"
          max="100"
          value={filters.minDelta}
          onChange={(event) => onChange({ minDelta: Number(event.target.value || 0), page: 1 })}
        />
      </label>
      <label className={styles.field}>
        <span>Сортировка</span>
        <select value={filters.sort} onChange={(event) => onChange({ sort: event.target.value, page: 1 })}>
          <option value="delta_desc">Больше изменение</option>
          <option value="events_desc">Больше событий</option>
          <option value="last_spp_desc">СПП выше</option>
          <option value="last_spp_asc">СПП ниже</option>
          <option value="nm_id_asc">nmID по возр.</option>
        </select>
      </label>
      <label className={styles.toggleField}>
        <input
          type="checkbox"
          checked={filters.onlyChanged}
          onChange={(event) => onChange({ onlyChanged: event.target.checked, page: 1 })}
        />
        <span>Только с изменениями</span>
      </label>
      <label className={styles.toggleField}>
        <input
          type="checkbox"
          checked={filters.hasSppPeriod}
          onChange={(event) => onChange({ hasSppPeriod: event.target.checked, page: 1 })}
        />
        <span>Есть СПП за период</span>
      </label>
      <label className={styles.toggleField}>
        <input
          type="checkbox"
          checked={filters.hasSppToday}
          onChange={(event) => onChange({ hasSppToday: event.target.checked, page: 1 })}
        />
        <span>Есть СПП сегодня</span>
      </label>
    </section>
  )
}

function ProductPhoto({ photos }: { photos: string[] }) {
  const thumbnail = photos[0]
  if (!thumbnail) {
    return <div className={styles.photoPlaceholder}>Нет</div>
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img className={styles.productPhoto} src={thumbnail} alt="Фото товара" loading="lazy" />
  )
}

interface SppChartProps {
  points: SeriesPoint[]
  adminPrices: AdminPricePoint[]
  events: SeriesEvent[]
  sales: SalesPoint[]
}

function buildStepPath<T>(
  items: T[],
  xForItem: (item: T) => number,
  yForItem: (item: T) => number,
): string {
  return items
    .map((item, idx) => {
      const x = xForItem(item).toFixed(1)
      const y = yForItem(item).toFixed(1)
      if (idx === 0) return `M ${x} ${y}`
      return `H ${x} V ${y}`
    })
    .join(' ')
}

function buildStepPathSegments<T>(
  items: T[],
  getTime: (item: T) => string,
  xForItem: (item: T) => number,
  yForItem: (item: T) => number,
  maxGapMs: number,
): string[] {
  const segments: T[][] = []
  let current: T[] = []

  items.forEach((item) => {
    const previous = current[current.length - 1]
    if (previous && new Date(getTime(item)).getTime() - new Date(getTime(previous)).getTime() > maxGapMs) {
      if (current.length) segments.push(current)
      current = []
    }
    current.push(item)
  })
  if (current.length) segments.push(current)

  return segments.map((segment) => buildStepPath(segment, xForItem, yForItem)).filter(Boolean)
}

function SppChart({ points, adminPrices, events, sales }: SppChartProps) {
  const valid = points.filter((point) => point.spp_percent !== null)
  if (valid.length === 0) {
    return <div className={styles.chartEmpty}>Нет точек СПП за выбранный период.</div>
  }

  const width = 720
  const height = 300
  const padX = 42
  const rightPadX = 58
  const topPadY = 24
  const plotBottom = 220
  const salesTop = 246
  const salesBottom = 278
  const sppValues = valid.map((point) => point.spp_percent as number)
  const minSpp = Math.max(0, Math.min(...sppValues) - 2)
  const maxSpp = Math.min(100, Math.max(...sppValues) + 2)
  const sppRange = Math.max(1, maxSpp - minSpp)
  const validPrices = points.filter((point) => point.price_showcase !== null)
  const validAdminPrices = adminPrices.filter((point) => point.wb_price !== null)
  const priceValues = [
    ...validPrices.map((point) => point.price_showcase as number),
    ...validAdminPrices.map((point) => point.wb_price as number),
  ]
  const minPrice = priceValues.length ? Math.max(0, Math.min(...priceValues) * 0.98) : 0
  const maxPrice = priceValues.length ? Math.max(...priceValues) * 1.02 : 1
  const priceRange = Math.max(1, maxPrice - minPrice)
  const salesValues = sales.map((point) => point.units_sold || 0)
  const maxSales = Math.max(0, ...salesValues)
  const startTs = Math.min(
    new Date(valid[0].snapshot_at).getTime(),
    ...sales.map((point) => new Date(`${point.date}T00:00:00`).getTime()),
  )
  const endTs = Math.max(
    new Date(valid[valid.length - 1].snapshot_at).getTime(),
    ...sales.map((point) => new Date(`${point.date}T23:59:59`).getTime()),
  )
  const timeRange = Math.max(1, endTs - startTs)

  const xFor = (iso: string) => {
    const ts = new Date(iso).getTime()
    return padX + ((ts - startTs) / timeRange) * (width - padX - rightPadX)
  }
  const yForSpp = (value: number) => plotBottom - ((value - minSpp) / sppRange) * (plotBottom - topPadY)
  const yForPrice = (value: number) => plotBottom - ((value - minPrice) / priceRange) * (plotBottom - topPadY)
  const xForSale = (date: string) => xFor(`${date}T12:00:00`)
  const observationGapMs = 36 * 60 * 60 * 1000
  const observationGaps = valid.slice(1).flatMap((point, idx) => {
    const previous = valid[idx]
    const previousTs = new Date(previous.snapshot_at).getTime()
    const currentTs = new Date(point.snapshot_at).getTime()
    if (currentTs - previousTs <= observationGapMs) return []
    return [{ from: previous.snapshot_at, to: point.snapshot_at }]
  })
  const sppPaths = buildStepPathSegments(
    valid,
    (point) => point.snapshot_at,
    (point) => xFor(point.snapshot_at),
    (point) => yForSpp(point.spp_percent as number),
    observationGapMs,
  )
  const pricePaths = buildStepPathSegments(
    validPrices,
    (point) => point.snapshot_at,
    (point) => xFor(point.snapshot_at),
    (point) => yForPrice(point.price_showcase as number),
    observationGapMs,
  )
  const adminPricePath = buildStepPath(
    validAdminPrices,
    (point) => xFor(point.created_at),
    (point) => yForPrice(point.wb_price as number),
  )
  const sppGridValues = [minSpp, Math.round((minSpp + maxSpp) / 2), maxSpp]
  const priceGridValues = [minPrice, maxPrice]
  const plotWidth = width - padX - rightPadX
  const daysInRange = Math.max(1, Math.ceil(timeRange / 86_400_000))
  const dayWidth = plotWidth / daysInRange
  const salesBarWidth = Math.max(1.5, Math.min(10, dayWidth * 0.72))
  const tickCount = Math.min(4, Math.max(2, Math.floor(plotWidth / 180) + 1))
  const timeTicks = Array.from({ length: tickCount }, (_, idx) => {
    const ratio = tickCount === 1 ? 0 : idx / (tickCount - 1)
    const ts = startTs + timeRange * ratio
    return { ts, x: padX + ratio * plotWidth }
  })

  return (
    <div className={styles.chartWrap}>
      <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График динамики СПП">
        {observationGaps.map((gap, idx) => {
          const x1 = xFor(gap.from)
          const x2 = xFor(gap.to)
          const widthPx = Math.max(1, x2 - x1)
          return (
            <g key={`${gap.from}-${gap.to}-${idx}`}>
              <rect
                x={x1}
                y={topPadY}
                width={widthPx}
                height={plotBottom - topPadY}
                className={styles.observationGap}
              >
                <title>{`Нет витринных данных: ${formatDateTime(gap.from)} - ${formatDateTime(gap.to)}`}</title>
              </rect>
              {widthPx > 74 && (
                <text x={x1 + widthPx / 2} y={topPadY + 18} className={styles.observationGapLabel}>
                  нет витринных данных
                </text>
              )}
            </g>
          )
        })}
        {sppGridValues.map((value) => (
          <g key={value}>
            <line x1={padX} x2={width - rightPadX} y1={yForSpp(value)} y2={yForSpp(value)} className={styles.chartGrid} />
            <text x="8" y={yForSpp(value) + 4} className={styles.chartLabel}>
              {value}%
            </text>
          </g>
        ))}
        {priceValues.length > 0 &&
          priceGridValues.map((value) => (
            <text key={value} x={width - 46} y={yForPrice(value) + 4} className={`${styles.chartLabel} ${styles.priceAxisLabel}`}>
              {formatCurrency(value)}
            </text>
          ))}
        <line x1={padX} x2={width - rightPadX} y1={salesTop - 12} y2={salesTop - 12} className={styles.salesDivider} />
        {timeTicks.map((tick) => (
          <text key={tick.ts} x={tick.x} y={height - 8} className={styles.timeTick}>
            {formatShortDate(new Date(tick.ts).toISOString())}
          </text>
        ))}
        <text x="8" y={salesTop + 7} className={styles.chartLabel}>
          Продажи
        </text>
        {maxSales > 0 && (
          <text x={width - 46} y={salesTop + 7} className={styles.chartLabel}>
            {formatInt(maxSales)} шт
          </text>
        )}
        {sales.map((point) => {
          const barHeight = maxSales > 0 ? ((point.units_sold || 0) / maxSales) * (salesBottom - salesTop) : 0
          const x = xForSale(point.date) - salesBarWidth / 2
          const y = salesBottom - barHeight
          return (
            <rect
              key={point.date}
              x={x}
              y={y}
              width={salesBarWidth}
              height={Math.max(1, barHeight)}
              rx="1.5"
              className={styles.salesBar}
            >
              <title>{`${point.date}: ${formatInt(point.units_sold)} шт, ${formatCurrency(point.gross_sales)}`}</title>
            </rect>
          )
        })}
        {sppPaths.map((path, idx) => (
          <path key={`spp-path-${idx}`} d={path} className={styles.chartLine} />
        ))}
        {pricePaths.map((path, idx) => (
          <path key={`price-path-${idx}`} d={path} className={styles.priceLine} />
        ))}
        {adminPricePath && <path d={adminPricePath} className={styles.adminPriceLine} />}
        {valid.map((point, idx) => (
          <circle key={`${point.snapshot_at}-${idx}`} cx={xFor(point.snapshot_at)} cy={yForSpp(point.spp_percent as number)} r="2.5">
            <title>{`${formatDateTime(point.snapshot_at)}: ${point.spp_percent}%`}</title>
          </circle>
        ))}
        {validPrices.map((point, idx) => (
          <circle
            key={`${point.snapshot_at}-price-${idx}`}
            cx={xFor(point.snapshot_at)}
            cy={yForPrice(point.price_showcase as number)}
            r="2.2"
            className={styles.pricePoint}
          >
            <title>{`${formatDateTime(point.snapshot_at)}: ${formatCurrency(point.price_showcase)}`}</title>
          </circle>
        ))}
        {validAdminPrices.map((point, idx) => (
          <circle
            key={`${point.created_at}-admin-price-${idx}`}
            cx={xFor(point.created_at)}
            cy={yForPrice(point.wb_price as number)}
            r="2.2"
            className={styles.adminPricePoint}
          >
            <title>{`${formatDateTime(point.created_at)}: цена WB ${formatCurrency(point.wb_price)}`}</title>
          </circle>
        ))}
        {events.map((event, idx) => (
          <line
            key={`${event.changed_at}-${idx}`}
            x1={xFor(event.changed_at)}
            x2={xFor(event.changed_at)}
            y1={topPadY}
            y2={plotBottom}
            className={styles.eventMarker}
          >
            <title>{`${formatDateTime(event.changed_at)}: ${event.prev_spp_percent ?? '-'} → ${event.spp_percent}%`}</title>
          </line>
        ))}
        <g className={styles.chartLegend}>
          <circle cx="52" cy="12" r="3" />
          <text x="60" y="16">СПП</text>
          <circle cx="106" cy="12" r="3" className={styles.pricePoint} />
          <text x="114" y="16">Витрина</text>
          <circle cx="184" cy="12" r="3" className={styles.adminPricePoint} />
          <text x="192" y="16">Цена WB</text>
          <rect x="264" y="8" width="7" height="8" rx="1" className={styles.salesBar} />
          <text x="276" y="16">Продажи</text>
          <rect x="344" y="8" width="10" height="8" rx="1" className={styles.observationGapLegend} />
          <text x="360" y="16">Нет витринных данных</text>
        </g>
      </svg>
    </div>
  )
}

interface TableProps {
  items: SppItem[]
  selectedNmId: number | null
  series: SppSeriesResponse | null
  seriesLoading: boolean
  onToggle: (nmId: number) => void
}

function SppTable({ items, selectedNmId, series, seriesLoading, onToggle }: TableProps) {
  if (!items.length) {
    return (
      <div className={styles.emptyCard}>
        <p>Нет товаров с точками СПП за выбранный период.</p>
      </div>
    )
  }

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableWrap}>
        <table className={styles.sppTable}>
          <thead>
            <tr>
              <th>Фото</th>
              <th>Артикул</th>
              <th>Название</th>
              <th>РРЦ</th>
              <th>Витрина</th>
              <th>Цена WB</th>
              <th>СПП сейчас</th>
              <th>Min / max</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const isExpanded = item.nm_id === selectedNmId

              return (
                <Fragment key={item.nm_id}>
                  <tr
                    key={item.nm_id}
                    className={isExpanded ? styles.selectedRow : undefined}
                    role="button"
                    tabIndex={0}
                    aria-expanded={isExpanded}
                    onClick={() => onToggle(item.nm_id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        onToggle(item.nm_id)
                      }
                    }}
                    title={isExpanded ? 'Свернуть детали' : 'Развернуть детали'}
                  >
                    <td>
                      <ProductPhoto photos={item.photos || []} />
                    </td>
                    <td>
                      <div className={styles.articleCell}>
                        <strong>{item.vendor_code || '-'}</strong>
                        <a
                          href={`https://www.wildberries.ru/catalog/${item.nm_id}/detail.aspx`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={styles.nmLink}
                          onClick={(event) => event.stopPropagation()}
                        >
                          {item.nm_id}
                        </a>
                      </div>
                    </td>
                    <td>
                      <div className={styles.productCell}>
                        <strong>{item.name || 'Без названия'}</strong>
                        <span>{item.subject_name || item.category || 'Без категории'}</span>
                      </div>
                    </td>
                    <td className={styles.numericCell}>{formatCurrency(item.rrc)}</td>
                    <td className={styles.numericCell}>{formatCurrency(item.last_price_showcase)}</td>
                    <td className={styles.numericCell}>{formatCurrency(item.wb_price)}</td>
                    <td className={styles.numericCell}>{formatPercent(item.last_spp_percent)}</td>
                    <td className={styles.numericCell}>
                      {formatPercent(item.min_spp_percent)} / {formatPercent(item.max_spp_percent)}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className={styles.expandedRow}>
                      <td colSpan={8}>
                        <div className={styles.detailExpand}>
                          <SppDetail series={series} item={item} loading={seriesLoading} />
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface DetailProps {
  series: SppSeriesResponse | null
  item: SppItem | null
  loading: boolean
}

function ChangeCard({ title, changes, emptyText }: { title: string; changes: TimelineChange[]; emptyText: string }) {
  return (
    <div className={styles.changeCard}>
      <div className={styles.changeCardHeader}>
        <h3>{title}</h3>
        <span>{formatInt(changes.length)}</span>
      </div>
      {changes.length === 0 ? (
        <p className={styles.muted}>{emptyText}</p>
      ) : (
        changes.slice(0, 8).map((change) => (
          <div key={change.id} className={styles.eventRow}>
            <span className={styles.changeMeta}>
              <span className={`${styles.changeDot} ${styles[`changeDot_${change.kind}`]}`} />
              <span>{formatDateTime(change.at)}</span>
              <strong>{change.label}</strong>
            </span>
            <strong>
              {change.previous} &rarr; {change.current}
            </strong>
          </div>
        ))
      )}
    </div>
  )
}

function buildSppShowcaseRows(changes: TimelineChange[]): SppShowcaseChangeRow[] {
  const byTime = new Map<string, SppShowcaseChangeRow>()

  changes.forEach((change) => {
    if (change.kind !== 'spp' && change.kind !== 'showcase') return
    const row = byTime.get(change.at) || { at: change.at, spp: null, showcase: null }
    if (change.kind === 'spp') row.spp = change
    if (change.kind === 'showcase') row.showcase = change
    byTime.set(change.at, row)
  })

  return Array.from(byTime.values()).sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
}

function ChangeValue({ change }: { change: TimelineChange | null }) {
  if (!change) return <span className={styles.changeDash}>-</span>
  return (
    <strong>
      {change.previous} &rarr; {change.current}
    </strong>
  )
}

function SppShowcaseChangeCard({ changes }: { changes: TimelineChange[] }) {
  const rows = buildSppShowcaseRows(changes)

  return (
    <div className={styles.changeCard}>
      <div className={styles.changeCardHeader}>
        <h3>СПП и витрина</h3>
        <span>{formatInt(changes.length)}</span>
      </div>
      {rows.length === 0 ? (
        <p className={styles.muted}>За период СПП и витринная цена не менялись.</p>
      ) : (
        <div className={styles.combinedChangeTable} role="table" aria-label="Изменения СПП и витрины">
          <div className={styles.combinedChangeHead} role="row">
            <span role="columnheader">Дата</span>
            <span role="columnheader">
              <span className={`${styles.changeDot} ${styles.changeDot_spp}`} />
              СПП
            </span>
            <span role="columnheader">
              <span className={`${styles.changeDot} ${styles.changeDot_showcase}`} />
              Витрина
            </span>
          </div>
          {rows.slice(0, 8).map((row) => (
            <div key={row.at} className={styles.combinedChangeRow} role="row">
              <span role="cell">{formatDateTime(row.at)}</span>
              <span role="cell">
                <ChangeValue change={row.spp} />
              </span>
              <span role="cell">
                <ChangeValue change={row.showcase} />
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ChangeTimeline({ changes }: { changes: TimelineChange[] }) {
  const sppAndShowcase = changes.filter((change) => change.kind === 'spp' || change.kind === 'showcase')
  const adminChanges = changes.filter((change) => change.kind === 'admin')

  return (
    <div className={styles.eventsList}>
      <div className={styles.eventsHeader}>
        <h3>Изменения</h3>
        <span>{formatInt(changes.length)}</span>
      </div>
      <div className={styles.changeGrid}>
        <SppShowcaseChangeCard changes={sppAndShowcase} />
        <ChangeCard
          title="Цена WB"
          changes={adminChanges}
          emptyText="За период цена WB не менялась."
        />
      </div>
    </div>
  )
}

function SppDetail({ series, item, loading }: DetailProps) {
  if (loading) {
    return (
      <div className={styles.detailCard}>
        <p className={styles.loadingText}>Загрузка графика...</p>
      </div>
    )
  }

  if (!series) {
    return (
      <div className={styles.detailCard}>
        <div className={styles.detailPlaceholder}>Нет данных по выбранному артикулу.</div>
      </div>
    )
  }

  const lastPoint = series.points[series.points.length - 1]
  const timelineChanges = buildTimelineChanges(series)
  const lastAdminPrice = [...(series.admin_price_points || [])].reverse().find((point) => point.wb_price !== null)

  return (
    <div className={styles.detailCard}>
      <div className={styles.detailHeader}>
        <div>
          <span className={styles.detailEyebrow}>Артикул</span>
          <h2>{series.product.vendor_code || series.product.nm_id}</h2>
          <p>{series.product.name || 'Без названия'}</p>
        </div>
        <a
          href={`https://www.wildberries.ru/catalog/${series.product.nm_id}/detail.aspx`}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.detailLink}
        >
          WB
        </a>
      </div>

      <div className={styles.detailStats}>
        <div>
          <span>Текущий СПП</span>
          <strong>{formatPercent(lastPoint?.spp_percent)}</strong>
        </div>
        <div>
          <span>Витрина</span>
          <strong>{formatCurrency(lastPoint?.price_showcase)}</strong>
        </div>
        <div>
          <span>РРЦ</span>
          <strong>{formatCurrency(item?.rrc)}</strong>
        </div>
        <div>
          <span>Цена WB</span>
          <strong>{formatCurrency(lastAdminPrice?.wb_price ?? item?.wb_price)}</strong>
        </div>
      </div>

      <SppChart
        points={series.points}
        adminPrices={series.admin_price_points || []}
        events={series.events}
        sales={series.sales_daily || []}
      />

      <ChangeTimeline changes={timelineChanges} />
    </div>
  )
}

export default function SppDynamicsPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = params.projectId as string
  usePageTitle('Динамика СПП', projectId)

  const filters = useMemo(() => parseFilters(new URLSearchParams(searchParams.toString())), [searchParams])
  const [summary, setSummary] = useState<SppSummary | null>(null)
  const [itemsData, setItemsData] = useState<SppItemsResponse | null>(null)
  const [categories, setCategories] = useState<CategoryOption[]>([])
  const [selectedNmId, setSelectedNmId] = useState<number | null>(null)
  const [series, setSeries] = useState<SppSeriesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [seriesLoading, setSeriesLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateQuery = useCallback((patch: Partial<FiltersState>) => {
    const next: FiltersState = { ...filters, ...patch }
    const qs = new URLSearchParams()
    qs.set('date_from', next.dateFrom)
    qs.set('date_to', next.dateTo)
    if (next.q) qs.set('q', next.q)
    const categoryParam = buildCategoryIdsParam(next.categoryIds)
    if (categoryParam) qs.set('category_ids', categoryParam)
    if (next.onlyChanged) qs.set('only_changed', 'true')
    appendSppAvailabilityParams(qs, next)
    if (next.minDelta > 0) qs.set('min_delta', String(next.minDelta))
    if (next.sort !== 'delta_desc') qs.set('sort', next.sort)
    if (next.page > 1) qs.set('page', String(next.page))
    const base = `/app/project/${projectId}/wildberries/spp-dynamics`
    router.push(qs.toString() ? `${base}?${qs.toString()}` : base)
  }, [filters, projectId, router])

  const apiQuery = useMemo(() => {
    const qs = new URLSearchParams()
    qs.set('date_from', toApiDateStart(filters.dateFrom))
    qs.set('date_to', toApiDateEnd(filters.dateTo))
    if (filters.q) qs.set('q', filters.q)
    const categoryParam = buildCategoryIdsParam(filters.categoryIds)
    if (categoryParam) qs.set('category_ids', categoryParam)
    if (filters.onlyChanged) qs.set('only_changed', 'true')
    appendSppAvailabilityParams(qs, filters)
    if (filters.minDelta > 0) qs.set('min_delta', String(filters.minDelta))
    qs.set('sort', filters.sort)
    qs.set('limit', String(PAGE_SIZE))
    qs.set('offset', String((filters.page - 1) * PAGE_SIZE))
    return qs
  }, [filters])

  useEffect(() => {
    let cancelled = false

    async function loadCategories() {
      try {
        const resp = await apiGetData<{ items: CategoryOption[] }>(
          `/api/v1/projects/${projectId}/wildberries/categories`,
        )
        if (!cancelled) setCategories(resp.items || [])
      } catch (e) {
        console.warn('Failed to load WB categories', e)
        if (!cancelled) setCategories([])
      }
    }

    loadCategories()
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    let cancelled = false

    async function loadData() {
      setLoading(true)
      setError(null)
      try {
        const summaryQs = new URLSearchParams()
        summaryQs.set('date_from', toApiDateStart(filters.dateFrom))
        summaryQs.set('date_to', toApiDateEnd(filters.dateTo))
        const categoryParam = buildCategoryIdsParam(filters.categoryIds)
        if (categoryParam) summaryQs.set('category_ids', categoryParam)
        appendSppAvailabilityParams(summaryQs, filters)
        const [summaryResp, itemsResp] = await Promise.all([
          apiGetData<SppSummary>(`/api/v1/projects/${projectId}/wildberries/spp-dynamics/summary?${summaryQs.toString()}`),
          apiGetData<SppItemsResponse>(`/api/v1/projects/${projectId}/wildberries/spp-dynamics/items?${apiQuery.toString()}`),
        ])
        if (cancelled) return
        setSummary(summaryResp)
        setItemsData(itemsResp)
        setSelectedNmId((current) => {
          if (current && itemsResp.items.some((item) => item.nm_id === current)) return current
          return null
        })
      } catch (e: unknown) {
        if (cancelled) return
        console.error('Failed to load SPP dynamics', e)
        setError(e instanceof Error ? e.message : 'Не удалось загрузить динамику СПП')
        setSummary(null)
        setItemsData(null)
        setSelectedNmId(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadData()
    return () => {
      cancelled = true
    }
  }, [apiQuery, filters.categoryIds, filters.dateFrom, filters.dateTo, projectId])

  useEffect(() => {
    if (!selectedNmId) {
      setSeries(null)
      return
    }
    let cancelled = false

    async function loadSeries() {
      setSeriesLoading(true)
      try {
        const qs = new URLSearchParams()
        qs.set('date_from', toApiDateStart(filters.dateFrom))
        qs.set('date_to', toApiDateEnd(filters.dateTo))
        const resp = await apiGetData<SppSeriesResponse>(
          `/api/v1/projects/${projectId}/wildberries/spp-dynamics/items/${selectedNmId}/series?${qs.toString()}`,
        )
        if (!cancelled) setSeries(resp)
      } catch (e) {
        console.warn('Failed to load SPP series', e)
        if (!cancelled) setSeries(null)
      } finally {
        if (!cancelled) setSeriesLoading(false)
      }
    }

    loadSeries()
    return () => {
      cancelled = true
    }
  }, [filters.dateFrom, filters.dateTo, projectId, selectedNmId])

  const total = itemsData?.meta.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const toggleItem = useCallback((nmId: number) => {
    setSeries(null)
    setSelectedNmId((current) => (current === nmId ? null : nmId))
  }, [])
  const selectedSeries = series?.product.nm_id === selectedNmId ? series : null

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <div className={styles.titleRow}>
            <h1>Динамика СПП</h1>
            <span className={styles.marketplaceBadge}>
              <span aria-hidden="true" />
              WB
            </span>
          </div>
          <p>Изменения СПП по артикулам за период на основе витринных снимков Wildberries.</p>
        </div>
      </header>

      <section className={styles.metricGrid} aria-label="Сводка">
        <div className={styles.metricCard}>
          <span>Товаров со СПП</span>
          <strong>{summary ? formatInt(summary.products_with_spp) : '-'}</strong>
        </div>
        <div className={styles.metricCard}>
          <span>С изменениями</span>
          <strong>{summary ? formatInt(summary.products_with_events) : '-'}</strong>
        </div>
        <div className={styles.metricCard}>
          <span>Средний СПП</span>
          <strong>
            {summary ? `${formatPercent(summary.avg_spp_start)} → ${formatPercent(summary.avg_spp_end)}` : '-'}
          </strong>
        </div>
        <div className={styles.metricCard}>
          <span>Макс. скачок</span>
          <strong>{summary ? formatDelta(summary.max_abs_delta_spp) : '-'}</strong>
        </div>
      </section>

      <SppFilters filters={filters} categories={categories} onChange={updateQuery} />

      {error && (
        <div className={styles.errorCard}>
          <p>
            <strong>Ошибка:</strong> {error}
          </p>
        </div>
      )}

      <main className={styles.listColumn}>
        <div className={styles.listHeader}>
          <span>{loading ? 'Загрузка...' : `${formatInt(total)} товаров`}</span>
          <div className={styles.pagination}>
            <button type="button" disabled={filters.page <= 1} onClick={() => updateQuery({ page: filters.page - 1 })}>
              Назад
            </button>
            <span>
              {filters.page} / {pages}
            </span>
            <button type="button" disabled={filters.page >= pages} onClick={() => updateQuery({ page: filters.page + 1 })}>
              Вперед
            </button>
          </div>
        </div>
        {loading && <p className={styles.loadingText}>Загрузка данных...</p>}
        {!loading && !error && (
          <SppTable
            items={itemsData?.items || []}
            selectedNmId={selectedNmId}
            series={selectedSeries}
            seriesLoading={seriesLoading || (selectedNmId !== null && !selectedSeries)}
            onToggle={toggleItem}
          />
        )}
      </main>
    </div>
  )
}
