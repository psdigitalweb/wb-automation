'use client'

import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useParams } from 'next/navigation'
import {
  getWBProductLookup,
  getWBSalesTrends,
  type ApiError,
  type SalesTrendSeries,
  type SalesTrendsResponse,
  type WBProductLookupItem,
} from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useConstrainedReportPeriod } from '@/hooks/useReportFilterOptions'
import { ReportDataCoverage } from '@/components/ui-v2/ReportDataCoverage'
import styles from './sales-trends.module.css'

type Metric = 'revenue' | 'orders'

const COLORS = ['#17623c', '#2563eb', '#a855f7', '#d97706', '#dc2626', '#0891b2', '#4f46e5', '#65a30d', '#c026d3', '#475569']

function defaultPeriod() {
  const periodTo = new Date()
  const periodFrom = new Date(periodTo)
  periodFrom.setDate(periodFrom.getDate() - 89)
  return {
    from: periodFrom.toISOString().slice(0, 10),
    to: periodTo.toISOString().slice(0, 10),
  }
}

function productLabel(product: Pick<WBProductLookupItem, 'nm_id' | 'vendor_code' | 'title'>) {
  return product.vendor_code || product.title || String(product.nm_id)
}

function formatValue(value: number, metric: Metric, compact = false) {
  return new Intl.NumberFormat('ru-RU', {
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: metric === 'orders' ? 1 : 0,
  }).format(value)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short' }).format(new Date(`${value}T00:00:00`))
}

function metricValue(series: SalesTrendSeries, index: number, metric: Metric, moving: boolean) {
  const point = series.points[index]
  if (!point) return 0
  if (metric === 'revenue') return moving ? point.moving_average_revenue : point.revenue
  return moving ? point.moving_average_orders : point.orders
}

function SalesChart({ data, metric, showDaily }: { data: SalesTrendsResponse; metric: Metric; showDaily: boolean }) {
  const width = 980
  const height = 390
  const margin = { top: 24, right: 24, bottom: 48, left: 72 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const pointCount = Math.max(...data.series.map((item) => item.points.length), 1)
  const allValues = data.series.flatMap((series) =>
    series.points.flatMap((_, index) => [
      metricValue(series, index, metric, true),
      showDaily ? metricValue(series, index, metric, false) : 0,
    ])
  )
  const yMax = Math.max(...allValues, 1)
  const x = (index: number) => margin.left + (index / Math.max(pointCount - 1, 1)) * plotWidth
  const y = (value: number) => margin.top + plotHeight - (value / yMax) * plotHeight
  const path = (series: SalesTrendSeries, moving: boolean) =>
    series.points.map((_, index) => `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${y(metricValue(series, index, metric, moving)).toFixed(1)}`).join(' ')
  const xTickIndexes = Array.from(new Set([0, ...Array.from({ length: 4 }, (_, index) => Math.round(((index + 1) * (pointCount - 1)) / 4))]))

  return (
    <div className={styles.chartScroll}>
      <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График динамики продаж и скользящего среднего">
        {Array.from({ length: 5 }, (_, index) => {
          const value = (yMax * index) / 4
          const yPos = y(value)
          return (
            <g key={index}>
              <line x1={margin.left} x2={width - margin.right} y1={yPos} y2={yPos} className={styles.gridLine} />
              <text x={margin.left - 12} y={yPos + 4} textAnchor="end" className={styles.axisText}>
                {formatValue(value, metric, true)}
              </text>
            </g>
          )
        })}
        {xTickIndexes.map((index) => {
          const date = data.series[0]?.points[index]?.date
          if (!date) return null
          return (
            <text key={index} x={x(index)} y={height - 16} textAnchor="middle" className={styles.axisText}>
              {formatDate(date)}
            </text>
          )
        })}
        {data.series.map((series, seriesIndex) => (
          <g key={series.nm_id}>
            {showDaily && (
              <path d={path(series, false)} fill="none" stroke={COLORS[seriesIndex]} strokeWidth="1.25" opacity="0.25" />
            )}
            <path d={path(series, true)} fill="none" stroke={COLORS[seriesIndex]} strokeWidth="2.75" strokeLinejoin="round" strokeLinecap="round" />
            {series.points.map((point, index) => (
              <circle key={point.date} cx={x(index)} cy={y(metricValue(series, index, metric, true))} r="5" fill="transparent">
                <title>{`${productLabel(series)} · ${point.date}: ${formatValue(metricValue(series, index, metric, true), metric)}`}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>
    </div>
  )
}

export default function SalesTrendsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Динамика продаж', projectId)
  const initialPeriod = useMemo(defaultPeriod, [])
  const [periodFrom, setPeriodFrom] = useState(initialPeriod.from)
  const [periodTo, setPeriodTo] = useState(initialPeriod.to)
  const [windowDays, setWindowDays] = useState(7)
  const [metric, setMetric] = useState<Metric>('revenue')
  const [showDaily, setShowDaily] = useState(true)
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<WBProductLookupItem[]>([])
  const [selected, setSelected] = useState<WBProductLookupItem[]>([])
  const [data, setData] = useState<SalesTrendsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { options: reportOptions } = useConstrainedReportPeriod(
    projectId, 'sales-trends', periodFrom, periodTo, setPeriodFrom, setPeriodTo,
  )

  useEffect(() => {
    const normalized = query.trim()
    if (!normalized) {
      setSuggestions([])
      return
    }
    const timeout = window.setTimeout(async () => {
      try {
        const response = await getWBProductLookup(projectId, { q: normalized, limit: 8 })
        setSuggestions(response.items.filter((item) => !selected.some((chosen) => chosen.nm_id === item.nm_id)))
      } catch {
        setSuggestions([])
      }
    }, 250)
    return () => window.clearTimeout(timeout)
  }, [projectId, query, selected])

  const addProduct = (product: WBProductLookupItem) => {
    if (selected.length >= 10 || selected.some((item) => item.nm_id === product.nm_id)) return
    setSelected((current) => [...current, product])
    setQuery('')
    setSuggestions([])
  }

  const addNumericProduct = () => {
    const value = Number(query.trim())
    if (!Number.isInteger(value) || value <= 0) return
    addProduct({ nm_id: value, vendor_code: null, title: null, wb_category: null })
  }

  const load = async () => {
    if (selected.length === 0) {
      setError('Выберите хотя бы один артикул')
      return
    }
    if (!periodFrom || !periodTo || periodFrom > periodTo) {
      setError('Проверьте выбранный период')
      return
    }
    try {
      setLoading(true)
      setError(null)
      const response = await getWBSalesTrends(projectId, {
        period_from: periodFrom,
        period_to: periodTo,
        nm_ids: selected.map((item) => item.nm_id),
        window_days: windowDays,
      })
      setData(response)
      if (response.series.length === 0) setError('Для выбранных артикулов данные не найдены')
    } catch (caught: unknown) {
      const apiError = caught as ApiError
      setError(apiError.detail || 'Не удалось загрузить отчёт')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Wildberries · Отчёты</div>
          <h1>Динамика продаж</h1>
          <p>Сравнение продаж одного или нескольких артикулов со скользящим средним.</p>
        </div>
      </header>

      <section className={styles.filters}>
        <div className={styles.productField}>
          <label htmlFor="sales-product-search">Артикулы или nmId</label>
          <div className={styles.searchWrap}>
            <input
              id="sales-product-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  if (suggestions[0]) addProduct(suggestions[0])
                  else addNumericProduct()
                }
              }}
              placeholder="Начните вводить артикул"
              autoComplete="off"
            />
            {suggestions.length > 0 && (
              <div className={styles.suggestions}>
                {suggestions.map((item) => (
                  <button key={item.nm_id} type="button" onClick={() => addProduct(item)}>
                    <strong>{productLabel(item)}</strong>
                    <span>{item.title || `nmId ${item.nm_id}`}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className={styles.chips}>
            {selected.map((item, index) => (
              <span key={item.nm_id} className={styles.chip} style={{ '--series-color': COLORS[index] } as CSSProperties}>
                {productLabel(item)}
                <button type="button" aria-label={`Убрать ${productLabel(item)}`} onClick={() => setSelected((current) => current.filter((product) => product.nm_id !== item.nm_id))}>×</button>
              </span>
            ))}
            {selected.length === 0 && <span className={styles.hint}>Можно выбрать до 10 артикулов</span>}
          </div>
        </div>

        <label>
          Период с
          <input type="date" value={periodFrom} min={reportOptions?.date_filter.min_date ?? undefined} max={periodTo || reportOptions?.date_filter.max_date || undefined} onChange={(event) => setPeriodFrom(event.target.value)} />
        </label>
        <label>
          Период по
          <input type="date" value={periodTo} min={periodFrom || reportOptions?.date_filter.min_date || undefined} max={reportOptions?.date_filter.max_date ?? undefined} onChange={(event) => setPeriodTo(event.target.value)} />
        </label>
        <label>
          Окно среднего
          <select value={windowDays} onChange={(event) => setWindowDays(Number(event.target.value))}>
            {[3, 7, 14, 21, 28, 30, 60, 90].map((days) => <option key={days} value={days}>{days} дней</option>)}
          </select>
        </label>
        <button className={styles.primaryButton} type="button" onClick={load} disabled={loading}>
          {loading ? 'Строим…' : 'Построить график'}
        </button>
      </section>
      <ReportDataCoverage options={reportOptions} periodFrom={periodFrom} periodTo={periodTo} />

      {error && <div className={styles.error}>{error}</div>}

      <section className={styles.chartCard}>
        <div className={styles.chartHeader}>
          <div>
            <h2>{metric === 'revenue' ? 'Продажи, ₽' : 'Заказы, шт.'}</h2>
            <span>{data ? `Скользящее среднее за ${data.window_days} дней` : 'Выберите артикулы и постройте график'}</span>
          </div>
          <div className={styles.chartControls}>
            <div className={styles.segmented}>
              <button type="button" className={metric === 'revenue' ? styles.active : ''} onClick={() => setMetric('revenue')}>Выручка</button>
              <button type="button" className={metric === 'orders' ? styles.active : ''} onClick={() => setMetric('orders')}>Заказы</button>
            </div>
            <label className={styles.checkbox}>
              <input type="checkbox" checked={showDaily} onChange={(event) => setShowDaily(event.target.checked)} />
              Дневные значения
            </label>
          </div>
        </div>
        {data && data.series.length > 0 ? <SalesChart data={data} metric={metric} showDaily={showDaily} /> : <div className={styles.empty}>Здесь появится график динамики продаж</div>}
        {data && data.series.length > 0 && (
          <div className={styles.legend}>
            {data.series.map((series, index) => <span key={series.nm_id}><i style={{ background: COLORS[index] }} />{productLabel(series)}</span>)}
          </div>
        )}
      </section>

      {data && data.series.length > 0 && (
        <section className={styles.tableCard}>
          <table>
            <thead><tr><th>Артикул</th><th>nmId</th><th>Продажи за период</th><th>Заказы</th><th>Среднее в день</th><th>Последнее скользящее среднее</th></tr></thead>
            <tbody>
              {data.series.map((series) => {
                const totalRevenue = series.points.reduce((sum, point) => sum + point.revenue, 0)
                const totalOrders = series.points.reduce((sum, point) => sum + point.orders, 0)
                const last = series.points[series.points.length - 1]
                return <tr key={series.nm_id}><td><strong>{productLabel(series)}</strong><span>{series.title}</span></td><td className={styles.mono}>{series.nm_id}</td><td>{formatValue(totalRevenue, 'revenue')} ₽</td><td>{formatValue(totalOrders, 'orders')}</td><td>{formatValue(totalRevenue / Math.max(series.points.length, 1), 'revenue')} ₽</td><td>{formatValue(last?.moving_average_revenue || 0, 'revenue')} ₽</td></tr>
              })}
            </tbody>
          </table>
        </section>
      )}
    </main>
  )
}
