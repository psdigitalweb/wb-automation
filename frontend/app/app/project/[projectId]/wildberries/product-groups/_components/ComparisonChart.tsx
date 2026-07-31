'use client'

import type { WBProductGroupSeriesItem, WBProductGroupSeriesPoint } from '@/lib/wbProductGroupsApi'
import styles from '../product-groups.module.css'

const COLORS = ['#246b4b', '#8b3f8f', '#2563a8', '#b66a1c', '#a33b45']

type Metric = 'price' | 'spp_percent' | 'impressions' | 'ctr_percent' | 'orders' | 'revenue'

const METRIC_LABELS: Record<Metric, string> = {
  price: 'Цена витрины',
  spp_percent: 'СПП',
  impressions: 'Показы',
  ctr_percent: 'CTR',
  orders: 'Заказы',
  revenue: 'Выручка',
}

function metricValue(point: WBProductGroupSeriesPoint, metric: Metric): number | null {
  const value = point[metric]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatValue(value: number, metric: Metric): string {
  if (metric === 'price' || metric === 'revenue') {
    return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`
  }
  if (metric === 'spp_percent') return `${value.toFixed(0)}%`
  if (metric === 'ctr_percent') return `${value.toFixed(1)}%`
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)
}

export default function ComparisonChart({
  metric,
  series,
}: {
  metric: Metric
  series: WBProductGroupSeriesItem[]
}) {
  const values = series.flatMap((item) =>
    item.points.map((point) => metricValue(point, metric)).filter((value): value is number => value != null)
  )
  if (values.length === 0) {
    return (
      <section className={styles.chartCard}>
        <h3>{METRIC_LABELS[metric]}</h3>
        <div className={styles.emptyChart}>Нет данных за выбранный период</div>
      </section>
    )
  }

  const width = 900
  const height = 220
  const left = 54
  const right = 16
  const top = 16
  const bottom = 34
  const minRaw = Math.min(...values)
  const maxRaw = Math.max(...values)
  const padding = maxRaw === minRaw ? Math.max(1, Math.abs(maxRaw) * 0.05) : (maxRaw - minRaw) * 0.08
  const min = Math.max(metric === 'revenue' ? -Infinity : 0, minRaw - padding)
  const max = maxRaw + padding
  const range = Math.max(1, max - min)
  const longest = Math.max(...series.map((item) => item.points.length), 1)
  const x = (index: number) => left + (index / Math.max(1, longest - 1)) * (width - left - right)
  const y = (value: number) => top + ((max - value) / range) * (height - top - bottom)

  return (
    <section className={styles.chartCard}>
      <div className={styles.chartHeader}>
        <h3>{METRIC_LABELS[metric]}</h3>
        <div className={styles.legend}>
          {series.map((item, index) => (
            <span key={item.nm_id}>
              <i style={{ background: COLORS[index % COLORS.length] }} />
              {item.vendor_code || item.nm_id}
            </span>
          ))}
        </div>
      </div>
      <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={METRIC_LABELS[metric]}>
        {[0, 0.5, 1].map((position) => {
          const value = max - range * position
          const gridY = top + (height - top - bottom) * position
          return (
            <g key={position}>
              <line x1={left} y1={gridY} x2={width - right} y2={gridY} className={styles.gridLine} />
              <text x={left - 8} y={gridY + 4} textAnchor="end" className={styles.axisLabel}>
                {formatValue(value, metric)}
              </text>
            </g>
          )
        })}
        {series.map((item, seriesIndex) => {
          const segments: string[] = []
          let current = ''
          item.points.forEach((point, index) => {
            const value = metricValue(point, metric)
            if (value == null) {
              if (current) segments.push(current)
              current = ''
              return
            }
            current += `${current ? ' L' : 'M'} ${x(index)} ${y(value)}`
          })
          if (current) segments.push(current)
          return (
            <g key={item.nm_id}>
              {segments.map((path, index) => (
                <path
                  key={`${item.nm_id}-${index}`}
                  d={path}
                  fill="none"
                  stroke={COLORS[seriesIndex % COLORS.length]}
                  strokeWidth="2.2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ))}
              {item.points.map((point, index) => {
                const value = metricValue(point, metric)
                if (value == null) return null
                return (
                  <circle
                    key={`${item.nm_id}-${point.date}`}
                    cx={x(index)}
                    cy={y(value)}
                    r="2.5"
                    fill={COLORS[seriesIndex % COLORS.length]}
                  >
                    <title>{`${point.date} · ${item.vendor_code || item.nm_id}: ${formatValue(value, metric)}`}</title>
                  </circle>
                )
              })}
            </g>
          )
        })}
        {series[0]?.points.length ? (
          <>
            <text x={left} y={height - 9} className={styles.axisLabel}>
              {series[0].points[0].date}
            </text>
            <text x={width - right} y={height - 9} textAnchor="end" className={styles.axisLabel}>
              {series[0].points[series[0].points.length - 1].date}
            </text>
          </>
        ) : null}
      </svg>
    </section>
  )
}
