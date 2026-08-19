'use client'

import React, { useMemo, useState } from 'react'
import {
  getWBUnitPnlDynamics,
  type ApiError,
  type WBUnitPnlDynamicsPoint,
} from '@/lib/apiClient'
import styles from './unit-pnl.module.css'

type MetricKey =
  | 'sale'
  | 'total_to_pay'
  | 'commission_and_related'
  | 'logistics_cost'
  | 'storage_cost'
  | 'acceptance_cost'

const METRICS: Array<{ key: MetricKey; label: string; color: string }> = [
  { key: 'sale', label: 'Выручка', color: '#2563eb' },
  { key: 'total_to_pay', label: 'К выплате', color: '#15803d' },
  { key: 'commission_and_related', label: 'Комиссия', color: '#9333ea' },
  { key: 'logistics_cost', label: 'Логистика', color: '#ea580c' },
  { key: 'storage_cost', label: 'Хранение', color: '#0891b2' },
  { key: 'acceptance_cost', label: 'Приёмка', color: '#ca8a04' },
]

const DEFAULT_METRICS: MetricKey[] = ['sale', 'total_to_pay', 'commission_and_related']

function calendarMonthCount(from: string, to: string): number {
  const [fromYear, fromMonth] = from.split('-').map(Number)
  const [toYear, toMonth] = to.split('-').map(Number)
  if (![fromYear, fromMonth, toYear, toMonth].every(Number.isFinite)) return 0
  return (toYear - fromYear) * 12 + toMonth - fromMonth + 1
}

function formatMonth(value: string): string {
  const [year, month] = value.slice(0, 7).split('-').map(Number)
  return new Intl.DateTimeFormat('ru-RU', { month: 'short', year: '2-digit' })
    .format(new Date(year, month - 1, 1))
    .replace('.', '')
}

function formatCompactRub(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function formatRub(value: number): string {
  return `${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)} ₽`
}

function formatRevenueShare(value: number, revenue: number): string {
  if (revenue === 0) return 'доля от выручки —'
  const share = (value / revenue) * 100
  return `${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(share)}% от выручки`
}

export function MonthlyDynamics({
  projectId,
  rrDtFrom,
  rrDtTo,
}: {
  projectId: string
  rrDtFrom: string
  rrDtTo: string
}) {
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [points, setPoints] = useState<WBUnitPnlDynamicsPoint[] | null>(null)
  const [activeMetrics, setActiveMetrics] = useState<MetricKey[]>(DEFAULT_METRICS)

  if (calendarMonthCount(rrDtFrom, rrDtTo) < 2) return null

  const load = async () => {
    if (points || loading) return
    try {
      setLoading(true)
      setError(null)
      const response = await getWBUnitPnlDynamics(projectId, {
        rr_dt_from: rrDtFrom,
        rr_dt_to: rrDtTo,
      })
      setPoints(response.points)
    } catch (e) {
      const apiError = e as ApiError
      setError(apiError?.detail || 'Не удалось загрузить динамику')
    } finally {
      setLoading(false)
    }
  }

  const toggleExpanded = () => {
    const next = !expanded
    setExpanded(next)
    if (next) void load()
  }

  const toggleMetric = (key: MetricKey) => {
    setActiveMetrics((current) => {
      if (current.includes(key)) {
        return current.length === 1 ? current : current.filter((metric) => metric !== key)
      }
      return [...current, key]
    })
  }

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div>
          <h2>Динамика показателей</h2>
          <p className={styles.dynamicsHint}>Помесячные суммы по дате строки отчёта, без фильтров списка SKU</p>
        </div>
        <button type="button" className={styles.buttonSecondary} onClick={toggleExpanded}>
          {expanded ? 'Скрыть график' : 'Показать график'}
        </button>
      </div>
      {expanded && (
        <div className={styles.cardBody}>
          {loading && <div className={styles.stateText}>Загрузка динамики…</div>}
          {error && (
            <div className={styles.dynamicsError} role="alert">
              <span>{error}</span>
              <button type="button" className={styles.buttonSecondary} onClick={() => void load()}>
                Повторить
              </button>
            </div>
          )}
          {points && points.length > 0 && (
            <>
              <div className={styles.dynamicsLegend} aria-label="Показатели графика">
                {METRICS.map((metric) => {
                  const active = activeMetrics.includes(metric.key)
                  return (
                    <button
                      key={metric.key}
                      type="button"
                      className={`${styles.dynamicsLegendItem} ${active ? styles.dynamicsLegendItemActive : ''}`.trim()}
                      aria-pressed={active}
                      onClick={() => toggleMetric(metric.key)}
                    >
                      <span style={{ background: metric.color }} />
                      {metric.label}
                    </button>
                  )
                })}
              </div>
              <DynamicsChart points={points} activeMetrics={activeMetrics} />
            </>
          )}
          {points && points.length === 0 && (
            <div className={styles.stateText}>За выбранный период данных нет.</div>
          )}
        </div>
      )}
    </div>
  )
}

function DynamicsChart({
  points,
  activeMetrics,
}: {
  points: WBUnitPnlDynamicsPoint[]
  activeMetrics: MetricKey[]
}) {
  const width = 960
  const height = 320
  const padding = { top: 18, right: 24, bottom: 48, left: 76 }
  const plotWidth = width - padding.left - padding.right
  const plotHeight = height - padding.top - padding.bottom

  const scale = useMemo(() => {
    const values = points.flatMap((point) => activeMetrics.map((metric) => point[metric]))
    const minValue = Math.min(0, ...values)
    const maxValue = Math.max(0, ...values)
    const span = maxValue - minValue || 1
    const margin = span * 0.08
    return { min: minValue - margin, max: maxValue + margin }
  }, [activeMetrics, points])

  const xAt = (index: number) =>
    points.length === 1
      ? padding.left + plotWidth / 2
      : padding.left + (index / (points.length - 1)) * plotWidth
  const yAt = (value: number) =>
    padding.top + ((scale.max - value) / (scale.max - scale.min)) * plotHeight
  const gridValues = Array.from({ length: 5 }, (_, index) =>
    scale.max - (index / 4) * (scale.max - scale.min)
  )

  return (
    <div className={styles.dynamicsChartScroll}>
      <svg
        className={styles.dynamicsChart}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Помесячная динамика финансовых показателей"
      >
        {gridValues.map((value) => {
          const y = yAt(value)
          return (
            <g key={value}>
              <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className={styles.chartGridLine} />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className={styles.chartAxisLabel}>
                {formatCompactRub(value)}
              </text>
            </g>
          )
        })}
        {points.map((point, index) => (
          <text
            key={point.month}
            x={xAt(index)}
            y={height - 18}
            textAnchor="middle"
            className={styles.chartAxisLabel}
          >
            {formatMonth(point.month)}
          </text>
        ))}
        {METRICS.filter((metric) => activeMetrics.includes(metric.key)).map((metric) => {
          const path = points
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${xAt(index)} ${yAt(point[metric.key])}`)
            .join(' ')
          return (
            <g key={metric.key}>
              <path d={path} fill="none" stroke={metric.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
              {points.map((point, index) => (
                <circle key={point.month} cx={xAt(index)} cy={yAt(point[metric.key])} r="4" fill={metric.color}>
                  <title>{`${metric.label}, ${formatMonth(point.month)}: ${formatRub(point[metric.key])} · ${formatRevenueShare(point[metric.key], point.sale)}`}</title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
