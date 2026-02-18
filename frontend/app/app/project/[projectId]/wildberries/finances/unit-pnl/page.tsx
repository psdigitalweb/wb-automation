'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
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
import PortalBackButton from '@/components/PortalBackButton'

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
      <img
        src={src}
        alt={alt}
        style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4, cursor: 'pointer' }}
      />
      {hover && (
        <div
          style={{
            position: 'fixed',
            left: pos.x,
            top: pos.y,
            zIndex: 1000,
            padding: 8,
            background: '#fff',
            borderRadius: 8,
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            border: '1px solid #e5e7eb',
            pointerEvents: 'none',
          }}
        >
          <img
            src={src}
            alt={alt}
            style={{ width: 260, height: 260, objectFit: 'contain' }}
          />
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

function formatQty(value: number): string {
  return new Intl.NumberFormat('ru-RU', { useGrouping: true }).format(value)
}

function formatInt(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0, useGrouping: true }).format(Math.round(value))
}

function rowWbTotalCostPct(row: WBUnitPnlRow): number | null {
  const sale = row.sale_amount ?? 0
  if (!sale || sale === 0) return null
  const wb =
    row.wb_total_signed ??
    (row.commission_vv_signed ?? 0) +
      (row.acquiring ?? 0) +
      (row.logistics_cost ?? 0) +
      (row.storage_cost ?? 0) +
      (row.acceptance_cost ?? 0) +
      (row.other_withholdings ?? 0) +
      (row.penalties ?? 0)
  return (wb / sale) * 100
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
    <div ref={containerRef} style={{ position: 'relative', minWidth: 0 }}>
      <label className="unitpnl-label block text-sm font-medium mb-1">Отчёт</label>
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
        className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400"
      />
      {reportDropdownOpen && reportSuggestions.length > 0 && (
        <ul
          className="unitpnl-report-dropdown"
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 'calc(100% + 4px)',
            zIndex: 50,
            margin: 0,
            padding: 0,
            listStyle: 'none',
            maxHeight: 256,
            overflowY: 'auto',
            borderRadius: 6,
            border: '1px solid #e5e7eb',
            background: '#fff',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          }}
        >
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
              className="unitpnl-report-dropdown-item"
              style={{
                cursor: 'pointer',
                padding: '10px 12px',
                fontSize: 14,
                borderBottom: '1px solid #f3f4f6',
              }}
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
  const projectId = params.projectId as string

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
  const reportInputRef = React.useRef<HTMLDivElement>(null)

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
      return `/app/project/${projectId}/wildberries/finances/unit-pnl?${qs.toString()}`
    },
    [projectId, mode, reportId, rrDtFrom, rrDtTo, search, category, filterHeader, sort, order]
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
    { key: 'total_to_pay', label: 'К выплате, ₽' },
    { key: 'margin_pct_of_revenue', label: 'Маржа, %' },
    { key: 'wb_pct_of_sale', label: '% WB итого (на ед)' },
  ] as const

  return (
    <div className="container">
      {isReportsHost && (
        <div style={{ marginBottom: 12 }}>
          <PortalBackButton fallbackHref="/client" />
        </div>
      )}
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Прибыльность по товарам (WB Unit PnL)</h1>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link href={reportsHref}>
            <button type="button">К списку отчётов</button>
          </Link>
        </div>
      </div>

      <div className="card mb-5">
        <div className="p-4">
          <h3 className="m-0 mb-3 text-base font-semibold">Условия отбора</h3>
          <div className="unitpnl-grid unitpnl-grid--scope grid grid-cols-1 gap-6 md:grid-cols-[360px_1fr_160px] items-end">
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Режим</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as 'report' | 'period')}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="report">По отчёту</option>
                <option value="period">По периоду</option>
              </select>
            </div>
            {mode === 'report' ? (
              <div className="unitpnl-col flex flex-col min-w-0">
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
              <div className="unitpnl-col unitpnl-period-dates min-w-0">
                <div className="flex flex-col min-w-0">
                  <label className="unitpnl-label block text-sm font-medium mb-1">Дата с</label>
                  <input
                    type="date"
                    value={rrDtFrom}
                    onChange={(e) => setRrDtFrom(e.target.value)}
                    className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="flex flex-col min-w-0">
                  <label className="unitpnl-label block text-sm font-medium mb-1">Дата по</label>
                  <input
                    type="date"
                    value={rrDtTo}
                    onChange={(e) => setRrDtTo(e.target.value)}
                    className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            )}
            <div className="unitpnl-col unitpnl-actions flex items-end md:justify-end">
              <button
                onClick={handleRefresh}
                disabled={
                  loading ||
                  (mode === 'report' && isNaN(reportId)) ||
                  (mode === 'period' && (!rrDtFrom || !rrDtTo))
                }
                className="unitpnl-btn h-10 px-6 w-full md:w-auto rounded border border-gray-300 bg-white text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {loading ? 'Загрузка…' : 'Обновить'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ padding: 15, marginBottom: 20, backgroundColor: '#f8d7da', color: '#721c24', borderRadius: 4 }}>
          {error}
        </div>
      )}

      {headerTotals && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ padding: 16 }}>
            <h3 style={{ margin: '0 0 12px 0' }}>
              {headerTotals.filter_header ? 'Сводка по отфильтрованным SKU' : 'Сводка по выборке'}
            </h3>
            <HeaderSummary headerTotals={headerTotals} items={items} />
            <div style={{ marginTop: 12, fontSize: 12, color: '#666' }}>
              Операций (строк отчёта): {headerTotals.scope_lines_total ?? headerTotals.lines_total ?? 0} · SKU в
              выборке: {headerTotals.skus_total ?? 0}
            </div>
          </div>
        </div>
      )}

      <div className="card mb-5 mt-6">
        <div className="p-4">
          <h3 className="m-0 mb-3 text-base font-semibold">Фильтры списка SKU</h3>
          <div className="unitpnl-grid unitpnl-grid--filters grid grid-cols-1 gap-6 md:grid-cols-[1fr_320px_280px_160px] items-end">
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Поиск</label>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="nm_id, артикул, название"
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400"
              />
            </div>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Категория WB</label>
              <select
                value={category === '' ? '' : String(category)}
                onChange={(e) => setCategory(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
            <div className="unitpnl-col unitpnl-checkbox-wrap flex items-center h-10 md:justify-center">
              <label className="flex cursor-pointer select-none items-center text-sm leading-tight">
                <input
                  type="checkbox"
                  checked={filterHeader}
                  onChange={(e) => setFilterHeader(e.target.checked)}
                  className="mr-2 rounded border-gray-300"
                />
                Фильтровать сводку по фильтрам SKU
              </label>
            </div>
            <div className="unitpnl-col unitpnl-actions flex items-end md:justify-end">
              <button
                onClick={handleApplyFilters}
                className="unitpnl-btn h-10 px-6 w-full md:w-auto rounded border border-gray-300 bg-white text-sm hover:bg-gray-50"
              >
                Применить
              </button>
            </div>
          </div>
          {subjects.length === 0 && (
            <div className="mt-2 text-xs text-gray-500">
              Нет данных о категориях (нужна загрузка products)
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <p>Загрузка...</p>
      ) : !canFetch ? (
        <p style={{ color: '#666' }}>Укажите ID отчёта или период (даты) и нажмите «Обновить».</p>
      ) : items.length === 0 ? (
        <div className="card">
          <p style={{ padding: 20, textAlign: 'center', color: '#666' }}>
            Нет данных за выбранные условия.
          </p>
        </div>
      ) : (
        <div className="card">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #dee2e6' }}>
                  <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Фото</th>
                  <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Название</th>
                  <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>РРЦ, ₽</th>
                  {SORTABLE_COLUMNS.map(({ key, label }) => (
                    <th
                      key={key}
                      style={{
                        padding: 12,
                        textAlign: 'right',
                        fontWeight: 600,
                        cursor: 'pointer',
                        userSelect: 'none',
                        whiteSpace: 'nowrap',
                        color: sort === key ? '#0ea5e9' : 'inherit',
                      }}
                      onClick={() => handleSortClick(key)}
                      title={`Сортировать по ${label}`}
                    >
                      {label}
                      {sort === key && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>
                          {order === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </th>
                  ))}
                  <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Прибыль, ₽/шт</th>
                  <th style={{ padding: 12, width: 40, textAlign: 'center' }}></th>
                </tr>
              </thead>
              <tbody>
                {items.map((row, idx) => {
                  const isExpanded = expandedNmId === row.nm_id
                  const details = detailsCache[row.nm_id]
                  const isLoadingDetails = detailsLoading === row.nm_id
                  const photoUrl = row.photos?.[0] || null
                  const wbPct = rowWbTotalCostPct(row)
                  const subLabel = row.vendor_code
                    ? `${row.nm_id} · ${row.vendor_code}`
                    : `${row.nm_id}`
                  return (
                    <React.Fragment key={row.nm_id}>
                      <tr
                        style={{
                          borderBottom: '1px solid #eee',
                          backgroundColor: idx % 2 === 0 ? '#fff' : '#f8f9fa',
                        }}
                      >
                        <td style={{ padding: 12 }}>
                          {photoUrl ? (
                            <PhotoWithHover src={photoUrl} alt="" />
                          ) : (
                            <span style={{ color: '#999' }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: 12, maxWidth: 260 }}>
                          <div style={{ fontWeight: 500 }}>{(row.title || row.vendor_code) || '—'}</div>
                          {subLabel && (
                            <div style={{ fontSize: 12, color: '#6b7280', fontFamily: 'ui-monospace, monospace', marginTop: 2 }}>
                              {subLabel}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: 12, textAlign: 'right' }}>
                          {row.rrp_price != null ? formatRUB(row.rrp_price) : '—'}
                        </td>
                        <td style={{ padding: 12, textAlign: 'right' }}>{formatInt(row.net_sales_cnt)}</td>
                        <td style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>
                          {formatRUB(row.total_to_pay)}
                        </td>
                        <td style={{ padding: 12, textAlign: 'right' }}>
                          {row.cogs_missing
                            ? '—'
                            : row.margin_pct_of_revenue != null
                              ? `${formatPct(row.margin_pct_of_revenue)}%`
                              : '—'}
                        </td>
                        <td style={{ padding: 12, textAlign: 'right' }}>
                          {(() => {
                            const fp = row.fact_price_avg ?? 0
                            const wb = row.wb_total_cost_per_unit
                            if (!fp || fp <= 0 || wb == null) return '—'
                            return `${formatPct((wb / fp) * 100)}%`
                          })()}
                        </td>
                        <td style={{ padding: 12, textAlign: 'right' }}>
                          {row.cogs_missing
                            ? '—'
                            : row.profit_per_unit != null
                              ? formatRUB(row.profit_per_unit)
                              : '—'}
                        </td>
                        <td
                          style={{
                            padding: 12,
                            textAlign: 'center',
                            cursor: isLoadingDetails ? 'wait' : 'pointer',
                            width: 40,
                          }}
                          onClick={() => toggleExpand(row.nm_id)}
                          title={isExpanded ? 'Свернуть' : 'Развернуть детали'}
                        >
                          {isLoadingDetails ? '…' : isExpanded ? '▾' : '▸'}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr style={{ borderBottom: '1px solid #eee', backgroundColor: '#f8fafc' }}>
                          <td colSpan={9} style={{ padding: '16px 20px' }}>
                            {details ? (
                              <DetailsPanel details={details} row={row} />
                            ) : (
                              <div style={{ padding: 24, textAlign: 'center', color: '#666' }}>
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
          <div
            style={{
              padding: 12,
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 16,
              fontSize: 13,
              color: '#666',
              borderTop: '1px solid #eee',
            }}
          >
            <span>
              Показано {rowsTotal > 0 ? `${pageStart}–${pageEnd}` : '0'} из {rowsTotal}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                type="button"
                onClick={goToFirst}
                disabled={!canGoPrev}
                style={{ padding: '4px 10px', fontSize: 12 }}
                title="В начало"
              >
                ««
              </button>
              <button
                type="button"
                onClick={goToPrev}
                disabled={!canGoPrev}
                style={{ padding: '4px 10px', fontSize: 12 }}
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
                style={{ padding: '4px 10px', fontSize: 12 }}
                title="Вперёд"
              >
                Вперёд »
              </button>
              <button
                type="button"
                onClick={goToLast}
                disabled={!canGoNext}
                style={{ padding: '4px 10px', fontSize: 12 }}
                title="В конец"
              >
                »»
              </button>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>На странице:</span>
              <select
                value={limit}
                onChange={(e) => changePageSize(parseInt(e.target.value, 10))}
                style={{ padding: '4px 8px', fontSize: 12 }}
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n === PAGE_SIZE_ALL ? 'Все (1000)' : n}
                  </option>
                ))}
                {!PAGE_SIZE_OPTIONS.includes(limit) && (
                  <option value={limit}>{limit}</option>
                )}
              </select>
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        .unitpnl-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 24px;
          align-items: end;
        }
        .unitpnl-col {
          min-width: 0;
        }
        .unitpnl-label {
          display: block;
          margin-bottom: 4px;
          font-size: 14px;
          line-height: 1.25;
          font-weight: 500;
        }
        .unitpnl-control {
          width: 100%;
          height: 40px;
          padding: 8px 12px;
          line-height: 20px;
        }
        .unitpnl-control::placeholder {
          color: #9ca3af;
        }
        .unitpnl-btn {
          height: 40px;
          padding: 0 24px;
          width: 100%;
          margin-right: 0;
          margin-bottom: 0;
          white-space: nowrap;
        }
        .unitpnl-actions {
          align-items: end;
        }
        .unitpnl-checkbox-wrap {
          align-items: center;
          min-height: 40px;
        }
        .unitpnl-report-dropdown {
          list-style: none !important;
          margin: 0 !important;
          padding: 0 !important;
        }
        .unitpnl-report-dropdown-item:hover {
          background-color: #f9fafb;
        }
        .unitpnl-report-dropdown-item:last-child {
          border-bottom: none !important;
        }
        .unitpnl-period-dates {
          display: grid;
          grid-template-columns: 1fr;
          gap: 16px;
          min-width: 0;
        }
        @media (min-width: 768px) {
          .unitpnl-period-dates {
            grid-template-columns: 1fr 1fr;
          }
          .unitpnl-grid--scope {
            grid-template-columns: minmax(220px, 280px) minmax(360px, 1fr) 170px;
          }
          .unitpnl-grid--filters {
            grid-template-columns: minmax(260px, 1fr) minmax(260px, 360px) minmax(300px, 1.2fr) 170px;
          }
          .unitpnl-actions {
            justify-content: flex-end;
          }
          .unitpnl-btn {
            width: auto;
          }
          .unitpnl-checkbox-wrap {
            justify-content: flex-start;
          }
        }
      `}</style>

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
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ color: '#6b7280' }}>{label}</span>
      <span style={{ fontFamily: 'ui-monospace, monospace', fontWeight: 400, color: '#374151', textAlign: 'right', whiteSpace: 'nowrap' }}>
        {value}
      </span>
    </div>
  )
}

function DetailsPanel({ details, row }: { details: WBUnitPnlDetailsResponse; row: WBUnitPnlRow }) {
  const { product, base_calc, wb_costs_per_unit, logistics_counts, profitability } = details

  const commissionVvSigned = details.commission_vv_signed ?? 0
  const acquiring = details.acquiring ?? 0
  const logistics = wb_costs_per_unit?.logistics_cost ?? 0
  const storage = wb_costs_per_unit?.storage_cost ?? 0
  const acceptance = wb_costs_per_unit?.acceptance_cost ?? 0
  const other = wb_costs_per_unit?.other_withholdings ?? 0
  const penalties = wb_costs_per_unit?.penalties ?? 0
  const wbTotalSigned =
    details.wb_total_signed ??
    commissionVvSigned + acquiring + logistics + storage + acceptance + other + penalties

  const salesCnt = row?.sales_cnt ?? 0
  const breakdown = wb_costs_per_unit?.breakdown
  const wbTotalCostPerUnit = wb_costs_per_unit?.total ?? breakdown?.total ?? null

  const profitUnit = profitability?.profit_per_unit ?? row?.profit_per_unit
  const marginPct = profitability?.margin_pct_of_revenue ?? row?.margin_pct_of_revenue

  const shortLabel = product?.vendor_code
    ? `${details.nm_id} · ${product.vendor_code}`
    : `${details.nm_id}`

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(280px, 1fr))',
        gap: 24,
      }}
    >
      <div style={{ gridColumn: '1 / -1', fontSize: 12, color: '#6b7280', fontFamily: 'ui-monospace, monospace' }}>
        {shortLabel}
      </div>

      {/* Цены и база расчётов */}
      <div>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600, color: '#333' }}>
          Цены и база расчётов
        </h3>
        <div
          style={{
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            background: '#fff',
            display: 'grid',
            gap: 6,
            fontSize: 13,
          }}
        >
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

      {/* 3) Расходы WB — абсолюты */}
      <div>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600, color: '#333' }}>
          Расходы WB — абсолюты
        </h3>
        <div
          style={{
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            background: '#fff',
            display: 'grid',
            gap: 6,
            fontSize: 13,
          }}
        >
          <MetricLine
            label="Комиссия WB"
            value={details.commission_vv_signed != null ? fmt(details.commission_vv_signed) : '—'}
          />
          <MetricLine
            label="Эквайринг"
            value={details.acquiring != null ? fmt(details.acquiring) : '—'}
          />
          <MetricLine label="Логистика" value={fmt(logistics)} />
          <MetricLine label="Хранение" value={fmt(storage)} />
          <MetricLine label="Приёмка" value={fmt(acceptance)} />
          <MetricLine label="Удержания" value={fmt(other)} />
          <MetricLine label="Штрафы" value={fmt(penalties)} />
          <MetricLine label="Итого WB" value={fmt(wbTotalSigned)} />
        </div>
      </div>

      {/* 4) Расходы WB — на единицу */}
      <div>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600, color: '#333' }}>
          Расходы WB — на единицу
        </h3>
        <div
          style={{
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            background: '#fff',
            display: 'grid',
            gap: 6,
            fontSize: 13,
          }}
        >
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
            <div style={{ color: '#666' }}>Нет продаж (sales_cnt = 0)</div>
          )}
        </div>
      </div>

      {/* 5) Логистика */}
      <div>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>
          Логистика
        </h3>
        <div
          style={{
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            background: '#fff',
            display: 'grid',
            gap: 6,
            fontSize: 13,
          }}
        >
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

      {/* 6) Доходность */}
      <div style={{ gridColumn: '1 / -1' }}>
        <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 700, color: '#111827' }}>
          Доходность
        </h3>
        {profitability?.rrp_missing || profitability?.cogs_missing ? (
          <div
            style={{
              padding: '14px 16px',
              borderRadius: 10,
              border: '1px solid #fde68a',
              background: '#fffbeb',
              color: '#92400e',
              fontSize: 13,
            }}
          >
            Загрузите Internal Data / каталог, чтобы видеть РРЦ и COGS.
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 10,
            }}
          >
            {/* ФАКТ */}
            <div
              style={{
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid #e5e7eb',
                background: '#fff',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  alignItems: 'baseline',
                  marginBottom: 8,
                }}
              >
                <span style={{ fontSize: 12, fontWeight: 800, color: '#111827', letterSpacing: 0.3 }}>ФАКТ</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>Фактическая доходность (от выручки)</span>
              </div>
              <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
                <MetricLine label="Прибыль, ₽ / шт" value={profitUnit != null ? formatRUB(profitUnit) : '—'} />
                <MetricLine
                  label="Маржа, % от выручки"
                  value={marginPct != null ? `${formatPct(marginPct)}%` : '—'}
                />
              </div>
            </div>
            {/* ПЛАН / МОДЕЛЬ */}
            <div
              style={{
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid #e5e7eb',
                background: '#f9fafb',
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 800, color: '#111827', letterSpacing: 0.3, marginBottom: 8 }}>
                ПЛАН / МОДЕЛЬ
              </div>
              <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
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
            {/* СПРАВОЧНО */}
            <div
              style={{
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid #e5e7eb',
                background: '#fff',
                opacity: 0.9,
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 800, color: '#111827', letterSpacing: 0.3, marginBottom: 8 }}>
                СПРАВОЧНО
              </div>
              <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
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
    </div>
  )
}
