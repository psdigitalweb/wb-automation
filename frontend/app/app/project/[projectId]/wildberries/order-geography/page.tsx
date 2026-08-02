'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  getApiErrorMessage,
  getOrderGeography,
  type OrderGeographyGroupBy,
  type OrderGeographyItem,
  type OrderGeographyResponse,
} from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import styles from './order-geography.module.css'
import { useConstrainedReportPeriod } from '@/hooks/useReportFilterOptions'
import { ReportDataCoverage } from '@/components/ui-v2/ReportDataCoverage'

const GROUP_OPTIONS: { value: OrderGeographyGroupBy; label: string }[] = [
  { value: 'region', label: 'Регион' },
  { value: 'city', label: 'Город' },
  { value: 'ppvz', label: 'ПВЗ' },
  { value: 'country', label: 'Страна' },
  { value: 'office', label: 'Склад WB' },
]

function defaultPeriod(): { period_from: string; period_to: string } {
  const to = new Date()
  const from = new Date(to)
  from.setDate(from.getDate() - 30)
  return {
    period_from: from.toISOString().slice(0, 10),
    period_to: to.toISOString().slice(0, 10),
  }
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU').format(value)
}

function formatRub(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function labelForItem(item: OrderGeographyItem, groupBy: OrderGeographyGroupBy): string {
  if (groupBy === 'country') return item.country || 'Не указано'
  if (groupBy === 'region') return item.region || 'Не определено'
  if (groupBy === 'city') return item.city || item.region || 'Не определено'
  if (groupBy === 'office') return item.office_name || 'Не указано'
  return item.ppvz_office_name || item.ppvz_office_id || 'Не указано'
}

function BarList({
  title,
  items,
  groupBy,
}: {
  title: string
  items: OrderGeographyItem[]
  groupBy: OrderGeographyGroupBy
}) {
  const maxOrders = Math.max(...items.map((item) => item.orders), 1)
  return (
    <div className={styles.chartCard}>
      <h2>{title}</h2>
      <div className={styles.barList}>
        {items.length === 0 ? (
          <div className={styles.emptyState}>Нет данных</div>
        ) : (
          items.map((item, index) => {
            const width = Math.max(3, Math.round((item.orders / maxOrders) * 100))
            return (
              <div key={`${labelForItem(item, groupBy)}-${index}`} className={styles.barItem}>
                <div className={styles.barMeta}>
                  <span title={labelForItem(item, groupBy)}>{labelForItem(item, groupBy)}</span>
                  <strong>{formatInt(item.orders)}</strong>
                </div>
                <div className={styles.barTrack}>
                  <div style={{ width: `${width}%` }} />
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default function OrderGeographyPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('География заказов', projectId)

  const initialPeriod = useMemo(defaultPeriod, [])
  const [periodFrom, setPeriodFrom] = useState(initialPeriod.period_from)
  const [periodTo, setPeriodTo] = useState(initialPeriod.period_to)
  const [groupBy, setGroupBy] = useState<OrderGeographyGroupBy>('region')
  const [country, setCountry] = useState('')
  const [nmId, setNmId] = useState('')
  const [vendorCode, setVendorCode] = useState('')
  const [officeName, setOfficeName] = useState('')
  const [limit, setLimit] = useState(100)
  const [data, setData] = useState<OrderGeographyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const initialLoadKeyRef = useRef<string | null>(null)
  const { options: reportOptions, loading: reportOptionsLoading } = useConstrainedReportPeriod(
    projectId, 'order-geography', periodFrom, periodTo, setPeriodFrom, setPeriodTo,
  )

  const load = useCallback(async () => {
    if (!periodFrom || !periodTo) {
      setError('Укажите период')
      return
    }
    if (periodFrom > periodTo) {
      setError('Дата начала должна быть меньше или равна дате окончания')
      return
    }
    try {
      setLoading(true)
      setError(null)
      const parsedNmId = nmId.trim() ? Number(nmId.trim()) : undefined
      const result = await getOrderGeography(projectId, {
        period_from: periodFrom,
        period_to: periodTo,
        group_by: groupBy,
        country: country.trim() || undefined,
        nm_id: parsedNmId != null && !Number.isNaN(parsedNmId) ? parsedNmId : undefined,
        vendor_code: vendorCode.trim() || undefined,
        office_name: officeName.trim() || undefined,
        limit,
      })
      setData(result)
    } catch (error: unknown) {
      setError(getApiErrorMessage(error, 'Не удалось загрузить отчёт'))
    } finally {
      setLoading(false)
    }
  }, [country, groupBy, limit, nmId, officeName, periodFrom, periodTo, projectId, vendorCode])

  useEffect(() => {
    if (reportOptionsLoading || !periodFrom || !periodTo) return
    const loadKey = `${projectId}:${periodFrom}:${periodTo}`
    if (initialLoadKeyRef.current === loadKey) return
    initialLoadKeyRef.current = loadKey
    void load()
  }, [load, periodFrom, periodTo, projectId, reportOptionsLoading])

  const topItems = data?.items.slice(0, 20) ?? []
  const tableItems = data?.items ?? []

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <div className={styles.titleRow}>
            <h1>География заказов</h1>
            <span className={styles.marketplaceBadge}>
              <span aria-hidden="true" />
              WB
            </span>
          </div>
          <p>Распределение реальных продаж WB по стране, региону, городу, ПВЗ или складу.</p>
        </div>
        <Link className={styles.backButton} href={`/app/project/${projectId}/wildberries`}>
          Назад
        </Link>
      </header>

      <section className={styles.filterToolbar} aria-label="Фильтры">
        <label className={styles.field}>
          <span>Период с</span>
          <input type="date" value={periodFrom} min={reportOptions?.date_filter.min_date ?? undefined} max={periodTo || reportOptions?.date_filter.max_date || undefined} onChange={(e) => setPeriodFrom(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>по</span>
          <input type="date" value={periodTo} min={periodFrom || reportOptions?.date_filter.min_date || undefined} max={reportOptions?.date_filter.max_date ?? undefined} onChange={(e) => setPeriodTo(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>Группировка</span>
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as OrderGeographyGroupBy)}>
            {GROUP_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span>Страна</span>
          <input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Россия" />
        </label>
        <label className={styles.field}>
          <span>nmId</span>
          <input value={nmId} onChange={(e) => setNmId(e.target.value)} inputMode="numeric" placeholder="123456789" />
        </label>
        <label className={styles.field}>
          <span>Артикул</span>
          <input value={vendorCode} onChange={(e) => setVendorCode(e.target.value)} placeholder="vendor code" />
        </label>
        <label className={styles.field}>
          <span>Склад WB</span>
          <input value={officeName} onChange={(e) => setOfficeName(e.target.value)} placeholder="Рязань" />
        </label>
        <label className={styles.field}>
          <span>Лимит</span>
          <input
            type="number"
            min={1}
            max={500}
            value={limit}
            onChange={(e) => setLimit(Math.max(1, Math.min(500, Number(e.target.value) || 100)))}
          />
        </label>
        <div className={styles.filterActions}>
          <button className={styles.primaryButton} type="button" onClick={load} disabled={loading}>
            {loading ? 'Загрузка...' : 'Применить'}
          </button>
          {error && <span className={styles.errorText}>{error}</span>}
        </div>
      </section>
      <ReportDataCoverage options={reportOptions} periodFrom={periodFrom} periodTo={periodTo} />

      <section className={styles.metricGrid} aria-label="Сводка">
        <Metric label="Заказы" value={formatInt(data?.summary.orders)} />
        <Metric label="Выручка" value={formatRub(data?.summary.gross_sales)} />
        <Metric label="Страны" value={formatInt(data?.summary.countries)} />
        <Metric label="Регионы" value={formatInt(data?.summary.regions)} />
        <Metric label="Города" value={formatInt(data?.summary.cities)} />
        <Metric label="ПВЗ" value={formatInt(data?.summary.ppvz_count)} />
      </section>

      <section className={styles.chartGrid} aria-label="Топы">
        <BarList title="Топ по заказам" items={topItems} groupBy={groupBy} />
        <BarList title="Топ по выручке" items={[...topItems].sort((a, b) => b.gross_sales - a.gross_sales).slice(0, 20)} groupBy={groupBy} />
      </section>

      <div className={styles.tableCard}>
        <div className={styles.tableWrap}>
          <table className={styles.geoTable}>
            <thead>
              <tr>
                <Th>Страна</Th>
                <Th>Регион</Th>
                <Th>Город</Th>
                <Th>ПВЗ</Th>
                <Th>Склад WB</Th>
                <Th align="right">Заказы</Th>
                <Th align="right">Доля</Th>
                <Th align="right">Выручка</Th>
                <Th align="right">SKU</Th>
                <Th align="right">Топ nmId</Th>
              </tr>
            </thead>
            <tbody>
              {loading && tableItems.length === 0 ? (
                <tr>
                  <td colSpan={10} className={styles.tableEmpty}>
                    Загрузка...
                  </td>
                </tr>
              ) : tableItems.length === 0 ? (
                <tr>
                  <td colSpan={10} className={styles.tableEmpty}>
                    Нет данных за выбранный период
                  </td>
                </tr>
              ) : (
                tableItems.map((item, index) => (
                  <tr key={`${index}-${item.country}-${item.region}-${item.ppvz_office_id}`}>
                    <Td>{item.country || '—'}</Td>
                    <Td>{item.region || '—'}</Td>
                    <Td>{item.city || '—'}</Td>
                    <Td title={item.ppvz_office_name || ''}>
                      {item.ppvz_office_name || item.ppvz_office_id || '—'}
                    </Td>
                    <Td>{item.office_name || '—'}</Td>
                    <Td align="right">{formatInt(item.orders)}</Td>
                    <Td align="right">{formatPct(item.share)}</Td>
                    <Td align="right">{formatRub(item.gross_sales)}</Td>
                    <Td align="right">{formatInt(item.unique_nm_ids)}</Td>
                    <Td align="right">{item.top_nm_id ? `${item.top_nm_id} (${formatInt(item.top_nm_orders)})` : '—'}</Td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metricCard}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Th({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return <th className={align === 'right' ? styles.alignRight : undefined}>{children}</th>
}

function Td({ children, align = 'left', title }: { children: React.ReactNode; align?: 'left' | 'right'; title?: string }) {
  return (
    <td title={title} className={align === 'right' ? styles.alignRight : undefined}>
      {children}
    </td>
  )
}
