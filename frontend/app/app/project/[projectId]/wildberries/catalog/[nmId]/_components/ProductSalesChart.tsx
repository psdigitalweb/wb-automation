'use client'

import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import {
  getWBSalesTrends,
  type SalesTrendSeries,
  type SalesTrendsResponse,
} from '@/lib/apiClient'
import type { WBContentVersionSummary } from '@/lib/wbProductContentApi'
import styles from '../product.module.css'

type Metric = 'revenue' | 'orders'
type OverlayMetric = 'impressions' | 'card_clicks' | 'ctr_percent'
type ChangeDetail = { label: string; detail: string }
type ContentChangeEvent = {
  date: string
  versions: Array<{
    id: number
    versionNo: number
    observedAt: string
    details: ChangeDetail[]
  }>
}

const FIELD_LABELS: Record<string, string> = {
  vendorCode: 'Артикул продавца',
  subjectID: 'Категория',
  subjectName: 'Категория',
  dimensions: 'Габариты',
  sizes: 'Размеры',
  needKiz: 'Маркировка',
}

const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 })
const compactNumber = new Intl.NumberFormat('ru-RU', {
  notation: 'compact',
  maximumFractionDigits: 1,
})
const OVERLAY_METRICS: Array<{
  key: OverlayMetric
  label: string
  color: string
}> = [
  { key: 'impressions', label: 'Показы', color: '#ea580c' },
  { key: 'card_clicks', label: 'Клики', color: '#0891b2' },
  { key: 'ctr_percent', label: 'CTR', color: '#16a34a' },
]

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : {}
}

function truncate(value: unknown, limit = 76): string {
  if (value == null || value === '') return '—'
  const normalized = String(value).replace(/\s+/g, ' ').trim()
  return normalized.length > limit
    ? `${normalized.slice(0, limit - 1)}…`
    : normalized
}

function formatContentValue(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'number' || typeof value === 'string') {
    return truncate(value, 54)
  }
  if (Array.isArray(value)) {
    const formatted = value
      .map((item) => formatContentValue(item))
      .filter((item) => item !== '—')
    return formatted.length ? formatted.join(', ') : '—'
  }
  return truncate(JSON.stringify(value), 54)
}

function observedDate(value: string): string | null {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  const parts = new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(parsed)
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return values.year && values.month && values.day
    ? `${values.year}-${values.month}-${values.day}`
    : null
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
  }).format(new Date(`${value}T00:00:00`))
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Moscow',
  }).format(new Date(value))
}

function characteristicKey(item: unknown, index: number): string {
  const record = asRecord(item)
  return String(record.id ?? record.name ?? index)
}

function characteristicName(item: unknown, fallback: string): string {
  const record = asRecord(item)
  return String(record.name ?? record.title ?? fallback)
}

function characteristicValue(item: unknown): unknown {
  const record = asRecord(item)
  return record.value ?? record.values ?? record.valueText ?? item
}

function describeCharacteristics(change: Record<string, unknown>): string {
  const oldValues = Array.isArray(change.old) ? change.old : []
  const newValues = Array.isArray(change.new) ? change.new : []
  const oldByKey = new Map(
    oldValues.map((item, index) => [characteristicKey(item, index), item]),
  )
  const newByKey = new Map(
    newValues.map((item, index) => [characteristicKey(item, index), item]),
  )
  const changed = Array.from(
    new Set([...oldByKey.keys(), ...newByKey.keys()]),
  )
    .filter(
      (key) =>
        JSON.stringify(oldByKey.get(key)) !== JSON.stringify(newByKey.get(key)),
    )
    .map((key) => {
      const oldItem = oldByKey.get(key)
      const newItem = newByKey.get(key)
      const name = characteristicName(newItem ?? oldItem, key)
      return `${name}: ${formatContentValue(characteristicValue(oldItem))} → ${formatContentValue(characteristicValue(newItem))}`
    })

  if (!changed.length) return 'Состав характеристик изменён'
  const visible = changed.slice(0, 3)
  return `${visible.join(' · ')}${changed.length > 3 ? ` · ещё ${changed.length - 3}` : ''}`
}

function describeVersion(version: WBContentVersionSummary): ChangeDetail[] {
  const fields = version.changed_fields || {}
  const details: ChangeDetail[] = []

  if (fields.title) {
    const change = asRecord(fields.title)
    details.push({
      label: 'Заголовок',
      detail: `${truncate(change.old)} → ${truncate(change.new)}`,
    })
  }
  if (fields.description) {
    const change = asRecord(fields.description)
    details.push({
      label: 'Описание',
      detail: `${truncate(change.old, 68)} → ${truncate(change.new, 68)}`,
    })
  }
  if (fields.characteristics) {
    details.push({
      label: 'Характеристики',
      detail: describeCharacteristics(asRecord(fields.characteristics)),
    })
  }
  if (fields.photos || fields.mainPhotoFile) {
    const photos = asRecord(fields.photos)
    const added = Array.isArray(photos.added) ? photos.added.length : 0
    const removed = Array.isArray(photos.removed) ? photos.removed.length : 0
    const parts: string[] = []
    if (fields.mainPhotoFile || photos.mainChanged === true) {
      parts.push('главное фото заменено')
    }
    if (added) parts.push(`добавлено ${added}`)
    if (removed) parts.push(`удалено ${removed}`)
    if (photos.orderChanged === true) parts.push('изменён порядок')
    details.push({
      label: 'Фото',
      detail: parts.length ? parts.join(' · ') : 'Состав фотографий изменён',
    })
  }

  for (const field of Object.keys(fields)) {
    if (
      ['title', 'description', 'characteristics', 'photos', 'mainPhotoFile'].includes(
        field,
      )
    ) {
      continue
    }
    const change = asRecord(fields[field])
    details.push({
      label: FIELD_LABELS[field] || field,
      detail: `${formatContentValue(change.old)} → ${formatContentValue(change.new)}`,
    })
  }

  return details.length
    ? details
    : [{ label: 'Контент', detail: 'Изменение содержимого карточки' }]
}

export function buildContentChangeEvents(
  versions: WBContentVersionSummary[],
  periodFrom: string,
  periodTo: string,
): ContentChangeEvent[] {
  const grouped = new Map<string, ContentChangeEvent['versions']>()
  for (const version of versions) {
    if (version.event_type !== 'changed') continue
    const date = observedDate(version.observed_at)
    if (!date || date < periodFrom || date > periodTo) continue
    const items = grouped.get(date) ?? []
    items.push({
      id: version.id,
      versionNo: version.version_no,
      observedAt: version.observed_at,
      details: describeVersion(version),
    })
    grouped.set(date, items)
  }
  return Array.from(grouped.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([date, versionsForDate]) => ({ date, versions: versionsForDate }))
}

function metricValue(
  series: SalesTrendSeries,
  index: number,
  metric: Metric,
  moving: boolean,
): number {
  const point = series.points[index]
  if (!point) return 0
  if (metric === 'revenue') {
    return moving ? point.moving_average_revenue : point.revenue
  }
  return moving ? point.moving_average_orders : point.orders
}

function formatMetric(value: number, metric: Metric, compact = false): string {
  const formatted = compact ? compactNumber.format(value) : number.format(value)
  return metric === 'revenue' ? `${formatted} ₽` : formatted
}

function overlayValue(
  series: SalesTrendSeries,
  index: number,
  metric: OverlayMetric,
): number {
  const point = series.points[index]
  if (!point) return 0
  if (metric === 'impressions') {
    return Number(point.moving_average_impressions ?? 0)
  }
  if (metric === 'card_clicks') {
    return Number(point.moving_average_card_clicks ?? 0)
  }
  return Number(point.moving_average_ctr_percent ?? 0)
}

function formatOverlayMetric(value: number, metric: OverlayMetric): string {
  if (metric === 'ctr_percent') return `${number.format(value)}%`
  return number.format(value)
}

function SalesChart({
  series,
  metric,
  showDaily,
  overlays,
  events,
}: {
  series: SalesTrendSeries
  metric: Metric
  showDaily: boolean
  overlays: OverlayMetric[]
  events: ContentChangeEvent[]
}) {
  const width = 980
  const height = 350
  const margin = { top: 24, right: 24, bottom: 52, left: 72 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const pointCount = Math.max(series.points.length, 1)
  const values = series.points.flatMap((_, index) => [
    metricValue(series, index, metric, true),
    showDaily ? metricValue(series, index, metric, false) : 0,
  ])
  const yMax = Math.max(...values, 1)
  const x = (index: number) =>
    margin.left + (index / Math.max(pointCount - 1, 1)) * plotWidth
  const y = (value: number) =>
    margin.top + plotHeight - (value / yMax) * plotHeight
  const path = (moving: boolean) =>
    series.points
      .map(
        (_, index) =>
          `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${y(
            metricValue(series, index, metric, moving),
          ).toFixed(1)}`,
      )
      .join(' ')
  const overlayPaths = OVERLAY_METRICS.filter((item) =>
    overlays.includes(item.key),
  ).map((item) => {
    const max = Math.max(
      ...series.points.map((_, index) => overlayValue(series, index, item.key)),
      1,
    )
    const overlayY = (value: number) =>
      margin.top + plotHeight - (value / max) * plotHeight
    return {
      ...item,
      path: series.points
        .map(
          (_, index) =>
            `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${overlayY(
              overlayValue(series, index, item.key),
            ).toFixed(1)}`,
        )
        .join(' '),
    }
  })
  const xTickIndexes = Array.from(
    new Set([
      0,
      ...Array.from({ length: 4 }, (_, index) =>
        Math.round(((index + 1) * (pointCount - 1)) / 4),
      ),
    ]),
  )
  const indexByDate = new Map(
    series.points.map((point, index) => [point.date, index]),
  )
  const visibleEvents = events.flatMap((event) => {
    const index = indexByDate.get(event.date)
    return index == null ? [] : [{ ...event, index }]
  })

  return (
    <div className={styles.salesChartScroll}>
      <div className={styles.salesChartCanvas}>
        <svg
          className={styles.salesChart}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Скользящее среднее продаж с датами изменений контента"
        >
          {Array.from({ length: 5 }, (_, index) => {
            const value = (yMax * index) / 4
            const yPosition = y(value)
            return (
              <g key={index}>
                <line
                  x1={margin.left}
                  x2={width - margin.right}
                  y1={yPosition}
                  y2={yPosition}
                  className={styles.salesGridLine}
                />
                <text
                  x={margin.left - 12}
                  y={yPosition + 4}
                  textAnchor="end"
                  className={styles.salesAxisText}
                >
                  {formatMetric(value, metric, true)}
                </text>
              </g>
            )
          })}
          {xTickIndexes.map((index) => {
            const date = series.points[index]?.date
            return date ? (
              <text
                key={index}
                x={x(index)}
                y={height - 16}
                textAnchor="middle"
                className={styles.salesAxisText}
              >
                {formatDate(date)}
              </text>
            ) : null
          })}
          {visibleEvents.map((event) => (
            <line
              key={event.date}
              x1={x(event.index)}
              x2={x(event.index)}
              y1={margin.top}
              y2={margin.top + plotHeight}
              className={styles.contentChangeLine}
            />
          ))}
          {showDaily ? (
            <path d={path(false)} fill="none" className={styles.dailySalesLine} />
          ) : null}
          <path
            d={path(true)}
            fill="none"
            className={styles.movingAverageLine}
          />
          {overlayPaths.map((overlay) => (
            <path
              key={overlay.key}
              d={overlay.path}
              fill="none"
              stroke={overlay.color}
              className={styles.salesOverlayLine}
            />
          ))}
          {series.points.map((point, index) => (
            <rect
              key={point.date}
              x={
                index === 0
                  ? margin.left
                  : (x(index - 1) + x(index)) / 2
              }
              y={margin.top}
              width={
                pointCount === 1
                  ? plotWidth
                  : index === 0 || index === pointCount - 1
                    ? (x(1) - x(0)) / 2
                    : (x(index + 1) - x(index - 1)) / 2
              }
              height={plotHeight}
              fill="transparent"
            >
              <title>
                {[
                  `${formatDate(point.date)}: ${formatMetric(
                    metricValue(series, index, metric, true),
                    metric,
                  )}`,
                  ...overlayPaths.map(
                    (overlay) =>
                      `${overlay.label}: ${formatOverlayMetric(
                        overlayValue(series, index, overlay.key),
                        overlay.key,
                      )}`,
                  ),
                ].join('\n')}
              </title>
            </rect>
          ))}
        </svg>

        {visibleEvents.map((event) => {
          const left = (x(event.index) / width) * 100
          const alignment = left < 24 ? 'start' : left > 76 ? 'end' : 'center'
          const detailsCount = event.versions.reduce(
            (sum, version) => sum + version.details.length,
            0,
          )
          return (
            <button
              key={event.date}
              type="button"
              className={styles.contentChangeMarker}
              data-align={alignment}
              style={
                {
                  '--marker-left': `${left}%`,
                  '--marker-top': `${((margin.top + plotHeight) / height) * 100}%`,
                } as CSSProperties
              }
              aria-label={`${formatDate(event.date)}: ${detailsCount} изменений контента`}
            >
              <span className={styles.contentChangeDot} aria-hidden="true" />
              <span className={styles.contentChangeTooltip}>
                <strong>Изменение контента · {formatDate(event.date)}</strong>
                {event.versions.map((version) => (
                  <span key={version.id} className={styles.contentChangeVersion}>
                    <small>
                      Версия {version.versionNo} ·{' '}
                      {formatDateTime(version.observedAt)}
                    </small>
                    {version.details.map((detail, index) => (
                      <span key={`${detail.label}-${index}`}>
                        <b>{detail.label}</b>
                        <em>{detail.detail}</em>
                      </span>
                    ))}
                  </span>
                ))}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function ProductSalesChart({
  projectId,
  nmId,
  periodFrom,
  periodTo,
  versions,
}: {
  projectId: string
  nmId: number
  periodFrom: string
  periodTo: string
  versions: WBContentVersionSummary[]
}) {
  const [windowDays, setWindowDays] = useState(7)
  const [metric, setMetric] = useState<Metric>('revenue')
  const [showDaily, setShowDaily] = useState(true)
  const [enabledOverlays, setEnabledOverlays] = useState<
    Record<OverlayMetric, boolean>
  >({
    impressions: false,
    card_clicks: false,
    ctr_percent: false,
  })
  const [data, setData] = useState<SalesTrendsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    void getWBSalesTrends(projectId, {
      period_from: periodFrom,
      period_to: periodTo,
      nm_ids: [nmId],
      window_days: windowDays,
    })
      .then((response) => {
        if (!cancelled) setData(response)
      })
      .catch(() => {
        if (!cancelled) {
          setData(null)
          setError('Не удалось загрузить динамику продаж')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [nmId, periodFrom, periodTo, projectId, windowDays])

  const events = useMemo(
    () => buildContentChangeEvents(versions, periodFrom, periodTo),
    [periodFrom, periodTo, versions],
  )
  const series = data?.series[0]
  const overlays = OVERLAY_METRICS.filter(
    (item) => enabledOverlays[item.key],
  ).map((item) => item.key)

  return (
    <section className={`${styles.section} ${styles.salesChartSection}`}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>Динамика продаж</h2>
          <p>
            Скользящее среднее за {windowDays} дней. Метки — даты обнаружения
            изменений контента. Дополнительные линии — каждая в своей шкале.
          </p>
        </div>
        <div className={styles.salesChartControls}>
          <div className={styles.salesMetricSwitch}>
            <button
              type="button"
              data-active={metric === 'revenue'}
              onClick={() => setMetric('revenue')}
            >
              Выручка
            </button>
            <button
              type="button"
              data-active={metric === 'orders'}
              onClick={() => setMetric('orders')}
            >
              Заказы
            </button>
          </div>
          <label>
            Среднее
            <select
              value={windowDays}
              onChange={(event) => setWindowDays(Number(event.target.value))}
            >
              {[3, 7, 14, 30].map((days) => (
                <option key={days} value={days}>
                  {days} дней
                </option>
              ))}
            </select>
          </label>
          <label className={styles.salesDailyToggle}>
            <input
              type="checkbox"
              checked={showDaily}
              onChange={(event) => setShowDaily(event.target.checked)}
            />
            По дням
          </label>
          {OVERLAY_METRICS.map((overlay) => (
            <label
              key={overlay.key}
              className={styles.salesOverlayToggle}
              style={{ '--series-color': overlay.color } as CSSProperties}
            >
              <input
                type="checkbox"
                checked={enabledOverlays[overlay.key]}
                onChange={(event) =>
                  setEnabledOverlays((current) => ({
                    ...current,
                    [overlay.key]: event.target.checked,
                  }))
                }
              />
              <i aria-hidden="true" />
              {overlay.label}
            </label>
          ))}
        </div>
      </div>

      {loading ? (
        <div className={styles.salesChartStatus}>Загружаем динамику…</div>
      ) : error ? (
        <div className={styles.salesChartError}>{error}</div>
      ) : series?.points.length ? (
        <>
          <SalesChart
            series={series}
            metric={metric}
            showDaily={showDaily}
            overlays={overlays}
            events={events}
          />
          <div className={styles.salesChartLegend}>
            <span>
              <i data-kind="average" />
              Скользящее среднее
            </span>
            {showDaily ? (
              <span>
                <i data-kind="daily" />
                Значение за день
              </span>
            ) : null}
            <span>
              <i data-kind="content" />
              Изменение контента
            </span>
            {OVERLAY_METRICS.filter((overlay) =>
              overlays.includes(overlay.key),
            ).map((overlay) => (
              <span key={overlay.key}>
                <i style={{ background: overlay.color }} />
                {overlay.label}
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className={styles.salesChartStatus}>
          За выбранный период нет данных о продажах.
        </div>
      )}
    </section>
  )
}
