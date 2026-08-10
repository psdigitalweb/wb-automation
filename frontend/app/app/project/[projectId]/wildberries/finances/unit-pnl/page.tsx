'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams, useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  getWBUnitPnl,
  getWBUnitPnlDetails,
  getWBProductSubjects,
  getWBFinanceReportsSearch,
  type WBUnitPnlRow,
  type WBUnitPnlResponse,
  type WBUnitPnlDetailsResponse,
  type WBProductSubjectItem,
  type WBFinanceReportSearchItem,
  type ApiError,
} from '@/lib/apiClient'
import { HeaderSummary } from './HeaderSummary'
import { HeaderSummaryFull } from './HeaderSummaryFull'
import PortalBackButton from '@/components/PortalBackButton'
import { usePageTitle } from '@/hooks/usePageTitle'
import styles from './unit-pnl.module.css'

function PhotoWithHover({ src, alt }: { src: string; alt: string }) {
  const [hover, setHover] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const ref = React.useRef<HTMLDivElement>(null)
  const handleEnter = () => {
    if (ref.current) {
      const r = ref.current.getBoundingClientRect()
      setPos({ x: r.right + 8, y: r.top })
    }
    setHover(true)
  }
  return (
    <div
      ref={ref}
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={handleEnter}
      onMouseLeave={() => setHover(false)}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className={styles.thumbnail}
      />
      {hover && (
        <div className={styles.photoPopover} style={{ left: pos.x, top: pos.y }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt={alt} />
        </div>
      )}
    </div>
  )
}

function formatRUB(value: number, fractionDigits: number = 2): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    useGrouping: true,
  }).format(value)
}

function formatInt(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0, useGrouping: true }).format(Math.round(value))
}

function formatPct(value: number): string {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}

function fmt(value: number | null | undefined): string {
  if (value == null) return '—'
  return formatRUB(value)
}

function formatReportLabel(r: WBFinanceReportSearchItem): string {
  const pf = r.period_from ? new Date(r.period_from).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'
  const pt = r.period_to ? new Date(r.period_to).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'
  return `${r.report_id} · ${pf}–${pt}`
}

function sortReportsByPeriodToDesc(reports: WBFinanceReportSearchItem[]): WBFinanceReportSearchItem[] {
  return [...reports].sort((a, b) => {
    const aDate = a.period_to ? new Date(a.period_to).getTime() : 0
    const bDate = b.period_to ? new Date(b.period_to).getTime() : 0
    if (bDate !== aDate) return bDate - aDate
    const aFallback = a.last_seen_at ? new Date(a.last_seen_at).getTime() : 0
    const bFallback = b.last_seen_at ? new Date(b.last_seen_at).getTime() : 0
    return bFallback - aFallback
  })
}

function ReportAutocomplete({
  projectId,
  reportId,
  selectedReport,
  reportSuggestions,
  reportSearchQuery,
  reportDropdownOpen,
  onReportIdChange,
  onSelectedReportChange,
  onSuggestionsChange,
  onSearchQueryChange,
  onDropdownOpenChange,
}: {
  projectId: string
  reportId: number
  selectedReport: WBFinanceReportSearchItem | null
  reportSuggestions: WBFinanceReportSearchItem[]
  reportSearchQuery: string
  reportDropdownOpen: boolean
  onReportIdChange: (id: number) => void
  onSelectedReportChange: (r: WBFinanceReportSearchItem | null) => void
  onSuggestionsChange: (r: WBFinanceReportSearchItem[]) => void
  onSearchQueryChange: (q: string) => void
  onDropdownOpenChange: (open: boolean) => void
}) {
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebounce(query || reportSearchQuery, 300)
  const containerRef = React.useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!reportDropdownOpen && !query) return
    getWBFinanceReportsSearch(projectId, { query: debouncedQuery || undefined, limit: 20 })
      .then((list) => onSuggestionsChange(sortReportsByPeriodToDesc(list)))
      .catch(() => onSuggestionsChange([]))
  }, [projectId, debouncedQuery, reportDropdownOpen, onSuggestionsChange])


  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onDropdownOpenChange(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onDropdownOpenChange])

  const displayValue = selectedReport ? formatReportLabel(selectedReport) : (reportId && !isNaN(reportId) ? String(reportId) : '')

  return (
    <div ref={containerRef} className={styles.field} style={{ position: 'relative' }}>
      <label className={styles.label}>Отчёт</label>
      <input
        type="text"
        value={reportDropdownOpen ? query : displayValue}
        onChange={(e) => {
          setQuery(e.target.value)
          onSearchQueryChange(e.target.value)
          onDropdownOpenChange(true)
          if (!e.target.value) {
            onReportIdChange(NaN)
            onSelectedReportChange(null)
          }
        }}
        onFocus={() => {
          onDropdownOpenChange(true)
          if (!query) setQuery('')
        }}
        placeholder="Поиск по ID, периоду..."
        className={styles.control}
      />
      {reportDropdownOpen && reportSuggestions.length > 0 && (
        <ul className={styles.reportDropdown}>
          {reportSuggestions.map((r) => (
            <li
              key={r.report_id}
              role="button"
              tabIndex={0}
              onMouseDown={(e) => {
                e.preventDefault()
                onReportIdChange(r.report_id)
                onSelectedReportChange(r)
                setQuery('')
                onSearchQueryChange('')
                onDropdownOpenChange(false)
              }}
              className={styles.reportDropdownItem}
            >
              {formatReportLabel(r)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debouncedValue
}

const PAGE_SIZE_OPTIONS = [50, 100, 200, 1000] as const
const PAGE_SIZE_ALL = 1000

export default function WBUnitPnlPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const useFullWbTakeSummary = pathname.includes('/unit-pnl-full')
  const reportPath = useFullWbTakeSummary ? 'unit-pnl-full' : 'unit-pnl'
  const projectId = params.projectId as string
  usePageTitle(useFullWbTakeSummary ? 'WB Unit P&L' : 'Разбор финансовых отчётов WB', projectId)

  const reportIdFromUrl = searchParams.get('report_id')
  const rrDtFromUrl = searchParams.get('rr_dt_from')
  const rrDtToUrl = searchParams.get('rr_dt_to')
  const limitFromUrl = parseInt(searchParams.get('limit') || '50', 10)
  const offsetFromUrl = parseInt(searchParams.get('offset') || '0', 10)

  const [mode, setMode] = useState<'report' | 'period'>(
    reportIdFromUrl ? 'report' : 'period'
  )
  const [reportId, setReportId] = useState(reportIdFromUrl ? parseInt(reportIdFromUrl, 10) : NaN)
  const [rrDtFrom, setRrDtFrom] = useState(rrDtFromUrl || '')
  const [rrDtTo, setRrDtTo] = useState(rrDtToUrl || '')
  const [limit, setLimit] = useState(isNaN(limitFromUrl) || limitFromUrl <= 0 ? 50 : Math.min(limitFromUrl, PAGE_SIZE_ALL))
  const [offset, setOffset] = useState(Math.max(0, isNaN(offsetFromUrl) ? 0 : offsetFromUrl))
  const [search, setSearch] = useState(searchParams.get('q') || '')
  const [category, setCategory] = useState<number | ''>(() => {
    const c = searchParams.get('category')
    if (!c) return ''
    const n = parseInt(c, 10)
    return isNaN(n) ? '' : n
  })
  const [sort, setSort] = useState(searchParams.get('sort') || 'total_to_pay')
  const [order, setOrder] = useState<'asc' | 'desc'>((searchParams.get('order') as 'asc' | 'desc') || 'desc')
  const [subjects, setSubjects] = useState<WBProductSubjectItem[]>([])
  const [selectedReport, setSelectedReport] = useState<WBFinanceReportSearchItem | null>(null)
  const [reportSuggestions, setReportSuggestions] = useState<WBFinanceReportSearchItem[]>([])
  const [reportSearchQuery, setReportSearchQuery] = useState('')
  const [reportDropdownOpen, setReportDropdownOpen] = useState(false)

  const [data, setData] = useState<WBUnitPnlResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedNmId, setExpandedNmId] = useState<number | null>(null)
  const [detailsCache, setDetailsCache] = useState<Record<number, WBUnitPnlDetailsResponse>>({})
  const [detailsLoading, setDetailsLoading] = useState<number | null>(null)

  const [filterHeader, setFilterHeader] = useState(searchParams.get('filter_header') === '1')
  const [reportsHref, setReportsHref] = useState(`/app/project/${projectId}/wildberries/finances/reports`)
  const [isReportsHost, setIsReportsHost] = useState(false)

  // Params for fetch: derived from URL so we only fetch when URL has valid scope
  const fetchParamsFromUrl = useMemo(() => {
    const reportId = searchParams.get('report_id')
    const rrFrom = searchParams.get('rr_dt_from')
    const rrTo = searchParams.get('rr_dt_to')
    const cat = searchParams.get('category')
    const lim = parseInt(searchParams.get('limit') || '50', 10)
    const off = parseInt(searchParams.get('offset') || '0', 10)
    const s = searchParams.get('sort') || 'total_to_pay'
    const ord = (searchParams.get('order') as 'asc' | 'desc') || 'desc'
    const q = searchParams.get('q') || undefined
    const categoryVal = cat ? (() => { const n = parseInt(cat, 10); return isNaN(n) ? undefined : n })() : undefined
    const filterHeaderVal = searchParams.get('filter_header') === '1'
    if (reportId) {
      const rid = parseInt(reportId, 10)
      if (!isNaN(rid)) {
        return { report_id: rid, limit: lim, offset: off, sort: s, order: ord, q, category: categoryVal, filter_header: filterHeaderVal }
      }
    }
    if (rrFrom && rrTo) {
      return { rr_dt_from: rrFrom, rr_dt_to: rrTo, limit: lim, offset: off, sort: s, order: ord, q, category: categoryVal, filter_header: filterHeaderVal }
    }
    return null
  }, [searchParams])

  const canFetch = fetchParamsFromUrl !== null

  const fetchData = useCallback(async () => {
    if (!fetchParamsFromUrl) return
    try {
      setLoading(true)
      setError(null)
      const res = await getWBUnitPnl(projectId, fetchParamsFromUrl)
      setData(res)
    } catch (e) {
      const err = e as ApiError
      setError(err?.detail || 'Не удалось загрузить данные')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [projectId, fetchParamsFromUrl])

  // Fetch only when URL has valid params (initial load, back/forward, or after Обновить)
  useEffect(() => {
    if (fetchParamsFromUrl) fetchData()
  }, [fetchParamsFromUrl, fetchData])

  useEffect(() => {
    if (reportIdFromUrl) {
      setMode('report')
      setReportId(parseInt(reportIdFromUrl, 10))
    }
    if (rrDtFromUrl && rrDtToUrl) {
      setMode('period')
      setRrDtFrom(rrDtFromUrl)
      setRrDtTo(rrDtToUrl)
    }
    const qFromUrl = searchParams.get('q')
    setSearch(qFromUrl ?? '')
  }, [reportIdFromUrl, rrDtFromUrl, rrDtToUrl, searchParams])

  // Sync limit/offset/sort/order/category from URL (e.g. browser back/forward)
  useEffect(() => {
    const l = parseInt(searchParams.get('limit') || '50', 10)
    const o = parseInt(searchParams.get('offset') || '0', 10)
    const s = searchParams.get('sort') || 'total_to_pay'
    const ord = (searchParams.get('order') as 'asc' | 'desc') || 'desc'
    const cat = searchParams.get('category')
    setLimit(isNaN(l) || l <= 0 ? 50 : Math.min(Math.max(l, 1), PAGE_SIZE_ALL))
    setOffset(Math.max(0, isNaN(o) ? 0 : o))
    setSort(s)
    setOrder(ord)
    if (cat) {
      const n = parseInt(cat, 10)
      setCategory(isNaN(n) ? '' : n)
    } else setCategory('')
    setFilterHeader(searchParams.get('filter_header') === '1')
  }, [searchParams])

  // Build URL with pagination/sort params for navigation (uses current scope from state, optional overrides)
  const buildUrl = useCallback(
    (newOffset: number, newLimit: number, overrides?: { sort?: string; order?: string }) => {
      const qs = new URLSearchParams()
      if (mode === 'report' && !isNaN(reportId)) qs.set('report_id', String(reportId))
      if (mode === 'period' && rrDtFrom) qs.set('rr_dt_from', rrDtFrom)
      if (mode === 'period' && rrDtTo) qs.set('rr_dt_to', rrDtTo)
      if (search) qs.set('q', search)
      if (category !== '') qs.set('category', String(category))
      if (filterHeader) qs.set('filter_header', '1')
      const sortVal = overrides?.sort ?? sort
      const orderVal = overrides?.order ?? order
      if (sortVal) qs.set('sort', sortVal)
      if (orderVal) qs.set('order', orderVal)
      qs.set('offset', String(newOffset))
      qs.set('limit', String(newLimit))
      return `/app/project/${projectId}/wildberries/finances/${reportPath}?${qs.toString()}`
    },
    [projectId, reportPath, mode, reportId, rrDtFrom, rrDtTo, search, category, filterHeader, sort, order]
  )

  const handleRefresh = useCallback(() => {
    setOffset(0)
    router.replace(buildUrl(0, limit))
  }, [buildUrl, limit, router])

  const handleApplyFilters = useCallback(() => {
    setOffset(0)
    router.replace(buildUrl(0, limit))
  }, [buildUrl, limit, router])

  const fetchDetails = useCallback(
    async (nmId: number) => {
      if (detailsCache[nmId]) return
      try {
        setDetailsLoading(nmId)
        const scopeParams =
          mode === 'report' && !isNaN(reportId)
            ? { report_id: reportId }
            : mode === 'period' && rrDtFrom && rrDtTo
              ? { rr_dt_from: rrDtFrom, rr_dt_to: rrDtTo }
              : {}
        const res = await getWBUnitPnlDetails(projectId, nmId, scopeParams)
        setDetailsCache((prev) => ({ ...prev, [nmId]: res }))
      } catch (e) {
        setExpandedNmId(null)
      } finally {
        setDetailsLoading(null)
      }
    },
    [projectId, mode, reportId, rrDtFrom, rrDtTo, detailsCache]
  )

  const toggleExpand = (nmId: number) => {
    if (expandedNmId === nmId) {
      setExpandedNmId(null)
    } else {
      setExpandedNmId(nmId)
      fetchDetails(nmId)
    }
  }

  const defaultPeriod = useMemo(() => {
    const today = new Date()
    const first = new Date(today.getFullYear(), today.getMonth(), 1)
    return {
      from: first.toISOString().slice(0, 10),
      to: today.toISOString().slice(0, 10),
    }
  }, [])

  useEffect(() => {
    if (mode === 'period' && !rrDtFrom && !rrDtTo) {
      setRrDtFrom(defaultPeriod.from)
      setRrDtTo(defaultPeriod.to)
    }
  }, [mode, defaultPeriod])

  useEffect(() => {
    getWBProductSubjects(projectId).then(setSubjects).catch(() => {})
  }, [projectId])

  useEffect(() => {
    if (typeof window !== 'undefined' && window.location.hostname === 'reports.zakka.ru') {
      setReportsHref('/reports')
      setIsReportsHost(true)
    }
  }, [])

  useEffect(() => {
    if (reportIdFromUrl && !selectedReport && mode === 'report') {
      getWBFinanceReportsSearch(projectId, { query: reportIdFromUrl, limit: 5 })
        .then((list) => {
          const sorted = sortReportsByPeriodToDesc(list)
          const match = sorted.find((r) => r.report_id === parseInt(reportIdFromUrl, 10))
          if (match) setSelectedReport(match)
        })
        .catch(() => {})
    }
  }, [projectId, reportIdFromUrl, selectedReport, mode])

  const headerTotals = data?.header_totals
  const items = data?.items ?? []
  const rowsTotal = data?.rows_total ?? 0
  const SummaryComponent = useFullWbTakeSummary ? HeaderSummaryFull : HeaderSummary
  const fullDataIssues = useMemo(() => {
    if (!useFullWbTakeSummary || !headerTotals || rowsTotal === 0) return []

    const skusTotal = headerTotals.skus_total ?? rowsTotal
    const issues: Array<{ title: string; detail: string; href: string; action: string }> = []
    const cogsMissing = headerTotals.cogs_missing_count ?? 0
    const packagingMissing = headerTotals.packaging_missing_count ?? 0

    if (cogsMissing > 0) {
      issues.push({
        title: 'Не задана себестоимость',
        detail: `${cogsMissing} из ${skusTotal} SKU`,
        href: `/app/project/${projectId}/cogs`,
        action: 'Настроить себестоимость',
      })
    }
    if (packagingMissing > 0) {
      issues.push({
        title: 'Не задана стоимость упаковки',
        detail: `${packagingMissing} из ${skusTotal} SKU`,
        href: `/app/project/${projectId}/additional-costs?tab=packaging`,
        action: 'Настроить упаковку',
      })
    }
    if (!headerTotals.tax_model_code) {
      issues.push({
        title: 'Не настроена налоговая модель',
        detail: 'Налоги не включены в расчёт прибыли',
        href: `/app/project/${projectId}/settings/taxes`,
        action: 'Настроить налоги',
      })
    }

    return issues
  }, [headerTotals, projectId, rowsTotal, useFullWbTakeSummary])

  const canGoPrev = offset > 0
  const canGoNext = offset + limit < rowsTotal
  const pageStart = rowsTotal > 0 ? offset + 1 : 0
  const pageEnd = rowsTotal > 0 ? Math.min(offset + limit, rowsTotal) : 0
  const totalPages = rowsTotal > 0 ? Math.ceil(rowsTotal / limit) : 1
  const currentPage = limit > 0 ? Math.floor(offset / limit) + 1 : 1

  const goToPrev = () => {
    const newOffset = Math.max(0, offset - limit)
    setOffset(newOffset)
    router.replace(buildUrl(newOffset, limit))
  }
  const goToNext = () => {
    const newOffset = offset + limit
    setOffset(newOffset)
    router.replace(buildUrl(newOffset, limit))
  }
  const goToFirst = () => {
    setOffset(0)
    router.replace(buildUrl(0, limit))
  }
  const goToLast = () => {
    const lastOffset = Math.max(0, rowsTotal - limit)
    setOffset(lastOffset)
    router.replace(buildUrl(lastOffset, limit))
  }
  const changePageSize = (newLimit: number) => {
    setLimit(newLimit)
    setOffset(0)
    router.replace(buildUrl(0, newLimit))
  }

  const handleSortClick = (columnKey: string) => {
    const newSort = columnKey
    const newOrder =
      sort === columnKey ? (order === 'desc' ? 'asc' : 'desc') : 'desc'
    setSort(newSort)
    setOrder(newOrder)
    setOffset(0)
    router.replace(buildUrl(0, limit, { sort: newSort, order: newOrder }))
  }

  const SORTABLE_COLUMNS = [
    { key: 'sold_units', label: 'Продано, шт' },
    { key: 'wb_total_cost_per_unit', label: 'WB/шт' },
  ] as const

  return (
    <div className={styles.page}>
      {isReportsHost && (
        <div className={styles.portalBack}>
          <PortalBackButton fallbackHref="/client" />
        </div>
      )}
      <div className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <div className={styles.titleRow}>
            <h1>{useFullWbTakeSummary ? 'Unit P&L' : 'Разбор финансовых отчётов'}</h1>
            <span className={styles.marketplaceBadge}><span />WB</span>
          </div>
          <p>
            {useFullWbTakeSummary
              ? 'Unit P&L по SKU: выплаты, затраты WB, себестоимость и прибыль на единицу.'
              : 'Детализация выплат, комиссий, логистики и других затрат по финансовым отчётам WB.'}
          </p>
        </div>
        <div className={styles.headerActions}>
          <Link href={reportsHref} className={styles.buttonSecondary}>
            К списку отчётов
          </Link>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2>Условия отбора</h2>
        </div>
        <div className={styles.cardBody}>
          <div className={styles.scopeGrid}>
            <div className={styles.field}>
              <label className={styles.label}>Режим</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as 'report' | 'period')}
                className={styles.control}
              >
                <option value="report">По отчёту</option>
                <option value="period">По периоду</option>
              </select>
            </div>
            {mode === 'report' ? (
              <div className={styles.field}>
                <ReportAutocomplete
                  projectId={projectId}
                  reportId={reportId}
                  selectedReport={selectedReport}
                  reportSuggestions={reportSuggestions}
                  reportSearchQuery={reportSearchQuery}
                  reportDropdownOpen={reportDropdownOpen}
                  onReportIdChange={(id) => setReportId(isNaN(id) ? NaN : id)}
                  onSelectedReportChange={setSelectedReport}
                  onSuggestionsChange={setReportSuggestions}
                  onSearchQueryChange={setReportSearchQuery}
                  onDropdownOpenChange={setReportDropdownOpen}
                />
              </div>
            ) : (
              <div className={styles.periodDates}>
                <div className={styles.field}>
                  <label className={styles.label}>Дата с</label>
                  <input
                    type="date"
                    value={rrDtFrom}
                    onChange={(e) => setRrDtFrom(e.target.value)}
                    className={styles.control}
                  />
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>Дата по</label>
                  <input
                    type="date"
                    value={rrDtTo}
                    onChange={(e) => setRrDtTo(e.target.value)}
                    className={styles.control}
                  />
                </div>
              </div>
            )}
            <div className={styles.actions}>
              <button
                onClick={handleRefresh}
                disabled={
                  loading ||
                  (mode === 'report' && isNaN(reportId)) ||
                  (mode === 'period' && (!rrDtFrom || !rrDtTo))
                }
                className={styles.buttonPrimary}
              >
                {loading ? 'Загрузка…' : 'Обновить'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className={styles.errorCard}>
          {error}
        </div>
      )}

      {headerTotals && (
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <h2>{headerTotals.filter_header ? 'Сводка по отфильтрованным SKU' : 'Сводка по выборке'}</h2>
          </div>
          <div className={styles.cardBody}>
            {fullDataIssues.length > 0 && (
              <div className={styles.dataQualityAlert} role="status">
                <div className={styles.dataQualityTitle}>Для полного расчёта не хватает данных</div>
                <p className={styles.dataQualityDescription}>
                  Итоговая прибыль и маржа могут быть неполными. Заполните недостающие данные:
                </p>
                <ul className={styles.dataQualityList}>
                  {fullDataIssues.map((issue) => (
                    <li key={issue.title} className={styles.dataQualityItem}>
                      <div>
                        <strong>{issue.title}</strong>
                        <span>{issue.detail}</span>
                      </div>
                      <Link href={issue.href}>{issue.action}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <SummaryComponent headerTotals={headerTotals} items={items} />
            <div className={styles.summaryMeta}>
              Операций (строк отчёта): {headerTotals.scope_lines_total ?? headerTotals.lines_total ?? 0} · SKU в
              выборке: {headerTotals.skus_total ?? 0}
            </div>
          </div>
        </div>
      )}

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2>Фильтры списка SKU</h2>
        </div>
        <div className={styles.cardBody}>
          <div className={styles.filterGrid}>
            <div className={styles.field}>
              <label className={styles.label}>Поиск</label>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="nm_id, артикул, название"
                className={styles.control}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Категория WB</label>
              <select
                value={category === '' ? '' : String(category)}
                onChange={(e) => setCategory(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
                className={styles.control}
                disabled={subjects.length === 0}
                title={subjects.length === 0 ? 'Нет данных о категориях (нужна загрузка products)' : undefined}
              >
                <option value="">— всё —</option>
                {subjects.map((s) => (
                  <option key={s.subject_id} value={s.subject_id}>
                    {s.subject_name}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.checkLabel}>
                <input
                  type="checkbox"
                  checked={filterHeader}
                  onChange={(e) => setFilterHeader(e.target.checked)}
                />
                Фильтровать сводку по фильтрам SKU
              </label>
            </div>
            <div className={styles.actions}>
              <button
                onClick={handleApplyFilters}
                className={styles.buttonSecondary}
              >
                Применить
              </button>
            </div>
          </div>
          {subjects.length === 0 && (
            <div className={styles.hint}>
              Нет данных о категориях (нужна загрузка products)
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <div className={styles.emptyCard}>Загрузка...</div>
      ) : !canFetch ? (
        <div className={styles.emptyCard}>Укажите ID отчёта или период (даты) и нажмите «Обновить».</div>
      ) : items.length === 0 ? (
        <div className={styles.emptyCard}>
          Нет данных за выбранные условия.
        </div>
      ) : (
        <div className={styles.tableCard}>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Фото</th>
                  <th>Название</th>
                  <th className={styles.numberCell}>РРЦ, ₽</th>
                  {SORTABLE_COLUMNS.map(({ key, label }) => (
                    <th
                      key={key}
                      className={`${styles.numberCell} ${styles.sortableHeader} ${sort === key ? styles.sortableHeaderActive : ''}`}
                      onClick={() => handleSortClick(key)}
                      title={`Сортировать по ${label}`}
                    >
                      {label}
                      {sort === key && (
                        <span style={{ marginLeft: 4 }}>
                          {order === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </th>
                  ))}
                  <th className={styles.numberCell}>Расходы/шт</th>
                  <th className={styles.numberCell}>Прибыль/шт</th>
                  <th className={styles.numberCell}>Маржа</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const isExpanded = expandedNmId === row.nm_id
                  const details = detailsCache[row.nm_id]
                  const isLoadingDetails = detailsLoading === row.nm_id
                  const photoUrl = row.photos?.[0] || null
                  const subLabel = row.vendor_code
                    ? `${row.nm_id} · ${row.vendor_code}`
                    : `${row.nm_id}`
                  const expenseParts = [
                    row.cogs_per_unit,
                    row.packaging_cost_per_unit,
                    row.additional_costs_per_unit ?? 0,
                  ]
                  const expensesPerUnit = !row.cogs_missing && !row.packaging_missing && expenseParts.every((value) => value != null)
                    ? expenseParts.reduce((sum, value) => sum + Number(value ?? 0), 0)
                    : null
                  return (
                    <React.Fragment key={row.nm_id}>
                      <tr
                        className={styles.clickableRow}
                        role="button"
                        tabIndex={0}
                        aria-expanded={isExpanded}
                        onClick={() => toggleExpand(row.nm_id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            toggleExpand(row.nm_id)
                          }
                        }}
                        title={isExpanded ? 'Свернуть детали' : 'Развернуть детали'}
                      >
                        <td>
                          {photoUrl ? (
                            <PhotoWithHover src={photoUrl} alt="" />
                          ) : (
                            <span className={styles.hint}>—</span>
                          )}
                        </td>
                        <td className={styles.productCell}>
                          <div className={styles.productTitle}>{(row.title || row.vendor_code) || '—'}</div>
                          {subLabel && (
                            <div className={styles.productMeta}>
                              {subLabel}
                            </div>
                          )}
                        </td>
                        <td className={styles.numberCell}>
                          {row.rrp_price != null ? formatRUB(row.rrp_price) : '—'}
                        </td>
                        <td className={styles.numberCell}>{formatInt(row.net_sales_cnt)}</td>
                        <td className={`${styles.numberCell} ${styles.strongCell}`}>
                          {row.wb_total_cost_per_unit != null ? formatRUB(row.wb_total_cost_per_unit) : '—'}
                        </td>
                        <td className={styles.numberCell}>
                          {expensesPerUnit != null ? formatRUB(expensesPerUnit) : '—'}
                        </td>
                        <td className={styles.numberCell}>
                          {row.full_profit_per_unit != null ? formatRUB(row.full_profit_per_unit) : '—'}
                        </td>
                        <td className={styles.numberCell}>
                          {row.full_margin_pct_of_revenue != null ? `${formatPct(row.full_margin_pct_of_revenue)}%` : '—'}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className={styles.expandedRow}>
                          <td colSpan={8}>
                            {details ? (
                              <DetailsPanel
                                details={details}
                                row={row}
                                showPnlSections={useFullWbTakeSummary}
                                hideMissingProfitability={useFullWbTakeSummary}
                              />
                            ) : (
                              <div className={styles.emptyCard}>
                                Загрузка…
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className={styles.tableFooter}>
            <span>
              Показано {rowsTotal > 0 ? `${pageStart}–${pageEnd}` : '0'} из {rowsTotal}
            </span>
            <div className={styles.pager}>
              <button
                type="button"
                onClick={goToFirst}
                disabled={!canGoPrev}
                title="В начало"
              >
                ««
              </button>
              <button
                type="button"
                onClick={goToPrev}
                disabled={!canGoPrev}
                title="Назад"
              >
                « Назад
              </button>
              <span style={{ whiteSpace: 'nowrap' }}>
                Страница {currentPage} из {totalPages}
              </span>
              <button
                type="button"
                onClick={goToNext}
                disabled={!canGoNext}
                title="Вперёд"
              >
                Вперёд »
              </button>
              <button
                type="button"
                onClick={goToLast}
                disabled={!canGoNext}
                title="В конец"
              >
                »»
              </button>
            </div>
            <div className={styles.pageSize}>
              <span>На странице:</span>
              <select
                value={limit}
                onChange={(e) => changePageSize(parseInt(e.target.value, 10))}
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n === PAGE_SIZE_ALL ? 'Все (1000)' : n}
                  </option>
                ))}
                {!(PAGE_SIZE_OPTIONS as readonly number[]).includes(limit) && (
                  <option value={limit}>{limit}</option>
                )}
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MetricLine({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <div className={styles.metricLine}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>
        {value}
      </span>
    </div>
  )
}

function DetailsPanel({
  details,
  row,
  showPnlSections = true,
  hideMissingProfitability = false,
}: {
  details: WBUnitPnlDetailsResponse
  row: WBUnitPnlRow
  showPnlSections?: boolean
  hideMissingProfitability?: boolean
}) {
  const { product, base_calc, wb_costs_per_unit, logistics_counts, profitability, extended_costs } = details
  const profitabilityMissing = Boolean(profitability?.rrp_missing || profitability?.cogs_missing)

  const commissionVvSigned = details.commission_vv_signed ?? 0
  const acquiring = details.acquiring ?? 0
  const settlementCost = wb_costs_per_unit?.settlement_cost ?? (commissionVvSigned + acquiring)
  const pvzReward = wb_costs_per_unit?.pvz_reward ?? 0
  const rebillLogisticCost = wb_costs_per_unit?.rebill_logistic_cost ?? 0
  const settlementAdjustment = wb_costs_per_unit?.settlement_adjustment ?? 0
  const commonWbAllocated =
    details.wb_common_allocated_total ?? wb_costs_per_unit?.common_wb_allocated_total ?? 0
  const logistics = wb_costs_per_unit?.logistics_cost ?? 0
  const storage = wb_costs_per_unit?.storage_cost ?? 0
  const acceptance = wb_costs_per_unit?.acceptance_cost ?? 0
  const other = wb_costs_per_unit?.other_withholdings ?? 0
  const penalties = wb_costs_per_unit?.penalties ?? 0
  const wbTotalSigned =
    details.wb_total_signed ??
    settlementCost + logistics + storage + acceptance + other + penalties + commonWbAllocated

  const salesCnt = row?.sales_cnt ?? 0
  const breakdown = wb_costs_per_unit?.breakdown
  const wbTotalCostPerUnit = wb_costs_per_unit?.total ?? breakdown?.total ?? null
  const perUnitFromTotal = (value: number | null | undefined) => (
    value != null && salesCnt > 0 ? formatRUB(value / salesCnt) : '—'
  )

  const profitUnit = profitability?.profit_per_unit ?? row?.profit_per_unit
  const marginPct = profitability?.margin_pct_of_revenue ?? row?.margin_pct_of_revenue

  const shortLabel = product?.vendor_code
    ? `${details.nm_id} · ${product.vendor_code}`
    : `${details.nm_id}`

  return (
    <div className={styles.detailsPanel}>
      <div className={styles.detailsMeta}>
        {shortLabel}
      </div>

      <div className={styles.detailsCard}>
        <h3 className={styles.detailsTitle}>Цены и база расчётов</h3>
        <div className={styles.metricList}>
          <MetricLine label="РРЦ" value={fmt(base_calc?.rrp_price)} />
          <MetricLine label="Ср. цена WB" value={fmt(base_calc?.wb_price_avg)} />
          <MetricLine
            label="СПП, %"
            value={base_calc?.spp_avg != null ? `${formatPct(base_calc.spp_avg)}%` : '—'}
          />
          <MetricLine label="Факт. цена ср." value={fmt(base_calc?.fact_price_avg)} />
          <MetricLine
            label="Δ ср.цены к РРЦ, %"
            value={
              base_calc?.delta_fact_to_rrp_pct != null
                ? `${formatPct(base_calc.delta_fact_to_rrp_pct)}%`
                : '—'
            }
          />
        </div>
      </div>

      <div className={styles.detailsCard}>
        <h3 className={styles.detailsTitle}>Расходы WB — абсолюты</h3>
        <div className={styles.metricList}>
          <MetricLine
            label="Комиссия WB"
            value={details.commission_vv_signed != null ? fmt(details.commission_vv_signed) : '—'}
          />
          <MetricLine
            label="Эквайринг"
            value={details.acquiring != null ? fmt(details.acquiring) : '—'}
          />
          <MetricLine label="Вознаграждение ПВЗ" value={fmt(pvzReward)} />
          <MetricLine label="Перевыставленная логистика" value={fmt(rebillLogisticCost)} />
          <MetricLine label="Сверочная корректировка" value={fmt(settlementAdjustment)} />
          <MetricLine label="Логистика" value={fmt(logistics)} />
          <MetricLine label="Хранение" value={fmt(storage)} />
          <MetricLine label="Приёмка" value={fmt(acceptance)} />
          <MetricLine label="Удержания" value={fmt(other)} />
          <MetricLine label="Штрафы" value={fmt(penalties)} />
          <MetricLine label="Общие расходы WB (распределение)" value={fmt(commonWbAllocated)} />
          <MetricLine label="Итого WB" value={fmt(wbTotalSigned)} />
        </div>
      </div>

      <div className={styles.detailsCard}>
        <h3 className={styles.detailsTitle}>Расходы WB — на единицу</h3>
        <div className={styles.metricList}>
          {salesCnt > 0 && breakdown ? (
            <>
              <MetricLine
                label="Комиссия WB / ед, ₽"
                value={breakdown.commission != null ? formatRUB(breakdown.commission) : '—'}
              />
              <MetricLine
                label="Эквайринг / ед, ₽"
                value={breakdown.acquiring != null ? formatRUB(breakdown.acquiring) : '—'}
              />
              <MetricLine
                label="Вознаграждение ПВЗ / ед, ₽"
                value={breakdown.pvz_reward != null ? formatRUB(breakdown.pvz_reward) : '—'}
              />
              <MetricLine
                label="Перевыставленная логистика / ед, ₽"
                value={
                  breakdown.rebill_logistic_cost != null
                    ? formatRUB(breakdown.rebill_logistic_cost)
                    : '—'
                }
              />
              <MetricLine
                label="Сверочная корректировка / ед, ₽"
                value={
                  breakdown.settlement_adjustment != null
                    ? formatRUB(breakdown.settlement_adjustment)
                    : '—'
                }
              />
              <MetricLine
                label="Логистика / ед, ₽"
                value={breakdown.logistics != null ? formatRUB(breakdown.logistics) : '—'}
              />
              <MetricLine
                label="Хранение / ед, ₽"
                value={breakdown.storage != null ? formatRUB(breakdown.storage) : '—'}
              />
              <MetricLine
                label="Приёмка / ед, ₽"
                value={breakdown.acceptance != null ? formatRUB(breakdown.acceptance) : '—'}
              />
              <MetricLine
                label="Удержания / ед, ₽"
                value={breakdown.withholdings != null ? formatRUB(breakdown.withholdings) : '—'}
              />
              <MetricLine
                label="Штрафы / ед, ₽"
                value={breakdown.penalties != null ? formatRUB(breakdown.penalties) : '—'}
              />
              <MetricLine
                label="Общие расходы WB / ед, ₽"
                value={
                  breakdown.common_wb_allocated != null
                    ? formatRUB(breakdown.common_wb_allocated)
                    : '—'
                }
              />
              <MetricLine
                label="WB итого / ед, ₽"
                value={breakdown.total != null ? formatRUB(breakdown.total) : '—'}
              />
            </>
          ) : salesCnt > 0 ? (
            <MetricLine
              label="Затраты WB / шт, ₽"
              value={wbTotalCostPerUnit != null ? formatRUB(wbTotalCostPerUnit) : '—'}
            />
          ) : (
            <div className={styles.stateText}>Нет продаж (sales_cnt = 0)</div>
          )}
        </div>
      </div>

      <div className={styles.detailsCard}>
        <h3 className={styles.detailsTitle}>Логистика</h3>
        <div className={styles.metricList}>
          <MetricLine
            label="Доставки, шт"
            value={logistics_counts?.deliveries_qty != null ? formatInt(logistics_counts.deliveries_qty) : '—'}
          />
          <MetricLine
            label="Возвраты, шт"
            value={logistics_counts?.returns_log_qty != null ? formatInt(logistics_counts.returns_log_qty) : '—'}
          />
          <MetricLine
            label="Выкуп, %"
            value={
              logistics_counts?.buyout_rate != null
                ? `${formatPct(logistics_counts.buyout_rate * 100)}%`
                : '—'
            }
          />
        </div>
      </div>

      {showPnlSections && (
        <div className={`${styles.detailsCard} ${styles.detailsFull}`}>
          <h3 className={styles.detailsTitle}>Полная экономика</h3>
          <div className={styles.detailsEconomyGrid}>
          <div>
            <div className={styles.sectionKicker}>На единицу</div>
            <div className={styles.metricList}>
              <MetricLine
                label="Упаковка"
                value={
                  extended_costs?.packaging_cost_per_unit != null
                    ? formatRUB(extended_costs.packaging_cost_per_unit)
                    : '—'
                }
              />
              <MetricLine
                label="Индивидуальные расходы SKU"
                value={perUnitFromTotal(extended_costs?.product_additional_costs_total)}
              />
              <MetricLine
                label="Логистика FBS и возвраты"
                value={perUnitFromTotal(extended_costs?.marketplace_additional_costs_total)}
              />
              <MetricLine
                label="ФОТ"
                value={perUnitFromTotal(extended_costs?.warehouse_labor_costs_total)}
              />
              <MetricLine
                label="Итого операционные расходы"
                value={formatRUB(extended_costs?.additional_costs_per_unit ?? 0)}
              />
              <MetricLine
                label="Полная прибыль"
                value={row.full_profit_per_unit != null ? formatRUB(row.full_profit_per_unit) : '—'}
              />
              <MetricLine
                label="Полная маржа"
                value={
                  row.full_margin_pct_of_revenue != null
                    ? `${formatPct(row.full_margin_pct_of_revenue)}%`
                    : '—'
                }
              />
            </div>
          </div>
          <div>
            <div className={styles.sectionKicker}>Итого по SKU</div>
            <div className={styles.metricList}>
              <MetricLine
                label="Упаковка"
                value={
                  extended_costs?.packaging_cost_total != null
                    ? formatRUB(extended_costs.packaging_cost_total)
                    : '—'
                }
              />
              <MetricLine
                label="Индивидуальные расходы SKU"
                value={formatRUB(extended_costs?.product_additional_costs_total ?? 0)}
              />
              <MetricLine
                label="Логистика FBS и возвраты"
                value={formatRUB(extended_costs?.marketplace_additional_costs_total ?? 0)}
              />
              <MetricLine
                label="ФОТ"
                value={formatRUB(extended_costs?.warehouse_labor_costs_total ?? 0)}
              />
              <MetricLine
                label="Итого операционные расходы"
                value={formatRUB(extended_costs?.additional_costs_total ?? 0)}
              />
              <MetricLine
                label="Полная прибыль"
                value={row.full_profit_total != null ? formatRUB(row.full_profit_total) : '—'}
              />
              <MetricLine
                label="Полная маржа"
                value={
                  row.full_margin_pct_of_revenue != null
                    ? `${formatPct(row.full_margin_pct_of_revenue)}%`
                    : '—'
                }
              />
            </div>
          </div>
          </div>
        </div>
      )}

      {showPnlSections && !(hideMissingProfitability && profitabilityMissing) && (
        <div className={`${styles.detailsCard} ${styles.detailsFull}`}>
          <h3 className={styles.detailsTitle}>Доходность</h3>
          {profitabilityMissing ? (
            <div className={styles.warningCard} style={{ marginTop: 10 }}>
              Загрузите Internal Data / каталог, чтобы видеть РРЦ и COGS.
            </div>
          ) : (
            <div className={styles.profitGrid} style={{ marginTop: 10 }}>
            <div className={styles.profitSubCard}>
              <div className={styles.sectionKicker}>Факт</div>
              <div className={styles.metricList}>
                <MetricLine label="Прибыль, ₽ / шт" value={profitUnit != null ? formatRUB(profitUnit) : '—'} />
                <MetricLine
                  label="Маржа, % от выручки"
                  value={marginPct != null ? `${formatPct(marginPct)}%` : '—'}
                />
              </div>
            </div>
            <div className={`${styles.profitSubCard} ${styles.profitSubCardMuted}`}>
              <div className={styles.sectionKicker}>План / модель</div>
              <div className={styles.metricList}>
                <MetricLine
                  label="Маржа, % от РРЦ"
                  value={
                    profitability?.margin_pct_of_rrp != null
                      ? `${formatPct(profitability.margin_pct_of_rrp)}%`
                      : '—'
                  }
                />
                <MetricLine
                  label="Правило COGS (текст)"
                  value={profitability?.cogs_rule_text || '—'}
                />
                <MetricLine
                  label="Средняя цена к РРЦ, %"
                  value={
                    (() => {
                      const fact = base_calc?.fact_price_avg
                      const rrp = base_calc?.rrp_price
                      if (fact == null || rrp == null || rrp === 0) return '—'
                      return `${formatPct((fact / rrp) * 100)}%`
                    })()
                  }
                />
              </div>
            </div>
            <div className={styles.profitSubCard}>
              <div className={styles.sectionKicker}>Справочно</div>
              <div className={styles.metricList}>
                <MetricLine
                  label="Наценка, % от себестоимости"
                  value={
                    profitability?.markup_pct_of_cogs != null
                      ? `${formatPct(profitability.markup_pct_of_cogs)}%`
                      : '—'
                  }
                />
              </div>
            </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
