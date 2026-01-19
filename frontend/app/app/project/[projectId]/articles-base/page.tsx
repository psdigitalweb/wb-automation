'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGetData, apiRequest } from '../../../../../lib/apiClient'
import type { ApiDebug, ApiError } from '../../../../../lib/apiClient'
import '../../../../globals.css'

interface ArticleRecord {
  'Артикул': string | null
  'NMid': number | null
  'ШК': string | null
  'Наша цена (РРЦ)': number | null
  'Цена на витрине': number | null
  'Скидка наша': number | null
  'СПП': number | null
  // deprecated
  'Остаток WB'?: number | null
  'Обновлено WB'?: string | null
  'Обновлено фронт': string | null
  'Обновлено WB API': string | null
  // new stock model (FBS/FBO)
  fbs_stock_qty?: number | null
  fbs_stock_updated_at?: string | null
  has_fbs_stock?: boolean | null
  fbo_stock_qty?: number | null
  fbo_stock_updated_at?: string | null
  has_fbo_stock?: boolean | null
}

interface ArticleBaseResponse {
  total: number
  page: number
  page_size: number
  items: ArticleRecord[]
  completeness?: {
    page_items: number
    with_rrp: number
    with_wb_price: number
    with_front: number
    with_wb_stock: number
  }
  elapsed_ms?: number
}

type SortColumn = 'Артикул' | 'NMid' | 'ШК' | 'Наша цена (РРЦ)' | 'Цена на витрине' | 'Скидка наша' | 'СПП' | 'Остаток WB' | 'Остаток 1С' | 'Обновлено WB' | 'Обновлено 1С'
type SortOrder = 'asc' | 'desc'

interface ArticlesBaseSummary {
  totals: {
    total_products: number
    total_vendor_code_norm: number
  }
  counts: {
    with_rrp_price: number
    with_rrp_stock: number
    with_wb_stock: number
    with_wb_price: number
    with_front_price: number
  }
  percents: Record<string, number>
  last_snapshots: {
    fbs_stock_at: string | null
    fbo_stock_at: string | null
    wb_prices_at: string | null
    frontend_prices_at: string | null
    rrp_at: string | null
    // deprecated aliases (may exist)
    wb_stocks_at?: string | null
    supplier_stocks_at?: string | null
  }
}

interface CoverageList<T> {
  total_count: number
  items: T[]
}

interface ArticlesBaseCoverage {
  in_products_missing_rrp: CoverageList<{ vendor_code_norm: string; vendor_code_raw_sample: string | null; nm_id_sample: number | null }>
  in_rrp_missing_products: CoverageList<{ vendor_code_norm: string }>
  in_products_missing_fbs_stock: CoverageList<{ nm_id: number; vendor_code_norm: string | null; vendor_code_raw_sample: string | null }>
  in_products_missing_fbo_stock: CoverageList<{ nm_id: number; vendor_code_norm: string | null; vendor_code_raw_sample: string | null }>
  in_products_missing_wb_price: CoverageList<{ nm_id: number; vendor_code_norm: string | null; vendor_code_raw_sample: string | null }>
  in_products_missing_front: CoverageList<{ nm_id: number; vendor_code_norm: string | null; vendor_code_raw_sample: string | null }>
  duplicates_vendor_code_norm: CoverageList<{ vendor_code_norm: string; cnt: number; vendor_code_raw_sample: string | null; nm_ids_sample: number[] }>
  // deprecated alias (may exist)
  in_products_missing_wb_stock?: CoverageList<{ nm_id: number; vendor_code_norm: string | null; vendor_code_raw_sample: string | null }>
}

export default function ArticlesBasePage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [data, setData] = useState<ArticleRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | string | null>(null)
  const [debug, setDebug] = useState<ApiDebug | null>(null)
  const [limit] = useState(25)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [sortBy, setSortBy] = useState<SortColumn>('NMid')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')
  const [onlyWithWbStock, setOnlyWithWbStock] = useState(false)
  const [onlyWithOurStock, setOnlyWithOurStock] = useState(false)

  // Quality/coverage
  const [summary, setSummary] = useState<ArticlesBaseSummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [showGaps, setShowGaps] = useState(false)
  const [coverage, setCoverage] = useState<ArticlesBaseCoverage | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(false)
  const [coverageError, setCoverageError] = useState<string | null>(null)

          // Server filters
          const [missingRrp, setMissingRrp] = useState(false)
          const [missingWbPrice, setMissingWbPrice] = useState(false)
          const [missingFront, setMissingFront] = useState(false)

          // Stock model filters (FBS/FBO)
          const [hasFbsStock, setHasFbsStock] = useState(false)
          const [missingFbsStock, setMissingFbsStock] = useState(false)
          const [hasFboStock, setHasFboStock] = useState(false)
          const [missingFboStock, setMissingFboStock] = useState(false)
          const [anyMissingStock, setAnyMissingStock] = useState(false)

  // Reset state when projectId changes
  useEffect(() => {
    setData([])
    setOffset(0)
    setTotal(0)
    setError(null)
    setLoading(true)
    setSummary(null)
    setSummaryError(null)
    setShowGaps(false)
    setCoverage(null)
    setCoverageError(null)
  }, [projectId])

  useEffect(() => {
    loadData()
  }, [
    offset,
    projectId,
    search,
    sortBy,
    sortOrder,
    onlyWithWbStock,
    onlyWithOurStock,
    missingRrp,
    missingWbPrice,
    missingFront,
    hasFbsStock,
    missingFbsStock,
    hasFboStock,
    missingFboStock,
    anyMissingStock,
  ])

  useEffect(() => {
    loadSummary()
  }, [projectId])

  useEffect(() => {
    if (showGaps) loadCoverage()
  }, [showGaps, projectId])

  const loadSummary = async (force: boolean = false) => {
    try {
      setSummaryLoading(true)
      setSummaryError(null)
      const qs = force ? '?force=1' : ''
      const data = await apiGetData<ArticlesBaseSummary>(`/v1/projects/${projectId}/articles-base/summary${qs}`)
      setSummary(data)
    } catch (e: any) {
      setSummaryError(e?.detail || e?.message || 'Failed to load summary')
    } finally {
      setSummaryLoading(false)
    }
  }

  const loadCoverage = async (force: boolean = false) => {
    try {
      setCoverageLoading(true)
      setCoverageError(null)
      const qs = new URLSearchParams()
      qs.set('limit', '50')
      if (force) qs.set('force', '1')
      const data = await apiGetData<ArticlesBaseCoverage>(`/v1/projects/${projectId}/articles-base/coverage?${qs}`)
      setCoverage(data)
    } catch (e: any) {
      setCoverageError(e?.detail || e?.message || 'Failed to load coverage')
    } finally {
      setCoverageLoading(false)
    }
  }

  const clearAllFilters = () => {
    setSearch('')
    setSearchInput('')
    setOnlyWithWbStock(false)
    setOnlyWithOurStock(false)
    setMissingRrp(false)
    setMissingWbPrice(false)
    setMissingFront(false)
    setHasFbsStock(false)
    setMissingFbsStock(false)
    setHasFboStock(false)
    setMissingFboStock(false)
    setAnyMissingStock(false)
    setOffset(0)
  }

  const applyMissingFilter = (kind: 'rrp' | 'fbs_stock' | 'fbo_stock' | 'wb_price' | 'front' | 'any_missing_stock') => {
    setMissingRrp(false)
    setMissingWbPrice(false)
    setMissingFront(false)
    setHasFbsStock(false)
    setMissingFbsStock(false)
    setHasFboStock(false)
    setMissingFboStock(false)
    setAnyMissingStock(false)
    if (kind === 'rrp') setMissingRrp(true)
    if (kind === 'fbs_stock') setMissingFbsStock(true)
    if (kind === 'fbo_stock') setMissingFboStock(true)
    if (kind === 'wb_price') setMissingWbPrice(true)
    if (kind === 'front') setMissingFront(true)
    if (kind === 'any_missing_stock') setAnyMissingStock(true)
    setOffset(0)
    setShowGaps(false)
  }

  const searchFromGap = (qvalue: string) => {
    setSearchInput(qvalue)
    setSearch(qvalue)
    setOffset(0)
    setShowGaps(false)
  }

  const loadData = async () => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 15000) // 15s safety timeout
    try {
      setLoading(true)
      setError(null)

      // Map UI params to backend endpoint
      const apiParams = new URLSearchParams()
      apiParams.set('page', (Math.floor(offset / limit) + 1).toString())
      apiParams.set('page_size', limit.toString())
      if (search) apiParams.set('q', search)
      if (onlyWithWbStock) apiParams.set('only_in_stock_wb', 'true')
      if (onlyWithOurStock) apiParams.set('only_in_stock_1c', 'true')
      if (missingRrp) apiParams.set('missing_rrp', 'true')
      if (missingWbPrice) apiParams.set('missing_wb_price', 'true')
      if (missingFront) apiParams.set('missing_front', 'true')
      if (hasFbsStock) apiParams.set('has_fbs_stock', 'true')
      if (missingFbsStock) apiParams.set('missing_fbs_stock', 'true')
      if (hasFboStock) apiParams.set('has_fbo_stock', 'true')
      if (missingFboStock) apiParams.set('missing_fbo_stock', 'true')
      if (anyMissingStock) apiParams.set('any_missing_stock', 'true')
      if (process.env.NEXT_PUBLIC_DEBUG === 'true') apiParams.set('debug', '1')

      // sort: map UI column labels to backend sort fields
      const sortMap: Record<string, string> = {
        'Артикул': 'vendor_code_norm',
        'NMid': 'nm_id',
        'Наша цена (РРЦ)': 'rrp_price',
        'Цена на витрине': 'wb_price', // closest stable field for now
        'СПП': 'spp',
        'Остаток WB': 'stock_wb',
        'Остаток 1С': 'stock_1c',
      }
      const sortField = sortMap[sortBy] || 'vendor_code_norm'
      apiParams.set('sort', `${sortField}:${sortOrder}`)

      const result = await apiRequest<ArticleBaseResponse>(
        `/v1/projects/${projectId}/articles-base?${apiParams}`,
        { method: 'GET', signal: controller.signal }
      )
      console.log('articles-base result:', result)
      setDebug(result.debug)
      setData(result.data.items || [])
      setTotal(result.data.total || 0)
    } catch (error: any) {
      console.error('Failed to load articles:', error)
      if (error?.name === 'AbortError') {
        setError('Request timed out (15s). Check API base URL / nginx proxy / network.')
      } else {
        setError(error?.detail || error?.message || 'Failed to load articles')
      }
      setDebug(error?.debug || null)
    } finally {
      window.clearTimeout(timeoutId)
      setLoading(false)
    }
  }

  const handleSearch = () => {
    setSearch(searchInput)
    setOffset(0)
  }

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const handleSort = (column: SortColumn) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(column)
      setSortOrder('asc')
    }
    setOffset(0)
  }

  const getSortIcon = (column: SortColumn) => {
    if (sortBy !== column) {
      return '↕️'
    }
    return sortOrder === 'asc' ? '↑' : '↓'
  }

  const formatNumber = (value: number | null): string => {
    if (value === null || value === undefined) return 'N/A'
    return value.toFixed(2)
  }

  const formatInt = (value: number | null): string => {
    if (value === null || value === undefined) return 'N/A'
    return value.toString()
  }

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return 'N/A'
    try {
      return new Date(dateStr).toLocaleString('ru-RU')
    } catch {
      return 'N/A'
    }
  }

  return (
    <div className="container">
      <h1>Article Base Showcase</h1>
      <Link href={`/app/project/${projectId}/dashboard`}>
        <button>← Back to Dashboard</button>
      </Link>

      <div className="card" style={{ marginTop: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h2 style={{ margin: 0 }}>Summary (project-wide)</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => loadSummary(true)} disabled={summaryLoading}>
              {summaryLoading ? 'Refreshing…' : 'Refresh'}
            </button>
            <button onClick={() => setShowGaps((v) => !v)}>
              {showGaps ? 'Hide Gaps' : 'Show Gaps'}
            </button>
          </div>
        </div>

        {summaryError && <p style={{ color: 'crimson' }}>{summaryError}</p>}
        {summaryLoading && !summary && <p>Loading summary…</p>}
        {summary && (
          <>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 10 }}>
              <div><strong>Total products:</strong> {summary.totals.total_products}</div>
              <div><strong>Total vendor_code_norm:</strong> {summary.totals.total_vendor_code_norm}</div>
            </div>
            <div style={{ marginTop: 10, fontSize: 14 }}>
              <div><strong>RRP price:</strong> {summary.counts.with_rrp_price} ({summary.percents.with_rrp_price}%)</div>
              <div><strong>RRP stock:</strong> {summary.counts.with_rrp_stock} ({summary.percents.with_rrp_stock}%)</div>
              <div><strong>FBS stock:</strong> {summary.counts.with_fbs_stock} ({summary.percents.with_fbs_stock}%)</div>
              <div><strong>FBO stock:</strong> {summary.counts.with_fbo_stock} ({summary.percents.with_fbo_stock}%)</div>
              <div><strong>WB price:</strong> {summary.counts.with_wb_price} ({summary.percents.with_wb_price}%)</div>
              <div><strong>Frontend price:</strong> {summary.counts.with_front_price} ({summary.percents.with_front_price}%)</div>
            </div>
            <div style={{ marginTop: 10, fontSize: 12, color: '#666' }}>
              <div><strong>Last FBS stock snapshot:</strong> {formatDate(summary.last_snapshots.fbs_stock_at)}</div>
              <div><strong>Last FBO stock snapshot:</strong> {formatDate(summary.last_snapshots.fbo_stock_at)}</div>
              <div><strong>Last WB prices:</strong> {formatDate(summary.last_snapshots.wb_prices_at)}</div>
              <div><strong>Last frontend prices:</strong> {formatDate(summary.last_snapshots.frontend_prices_at)}</div>
              <div><strong>Last RRP:</strong> {formatDate(summary.last_snapshots.rrp_at)}</div>
            </div>
          </>
        )}

        {showGaps && (
          <div style={{ marginTop: 14 }}>
            <h3 style={{ marginBottom: 8 }}>Gaps</h3>
            {coverageError && <p style={{ color: 'crimson' }}>{coverageError}</p>}
            {coverageLoading && !coverage && <p>Loading coverage…</p>}
            {coverage && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
                <div className="card">
                  <strong>Products missing RRP</strong> (total: {coverage.in_products_missing_rrp.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.in_products_missing_rrp.items.map((it, idx) => (
                          <tr key={`${it.vendor_code_norm}-${idx}`}>
                            <td>{it.vendor_code_raw_sample || '—'}</td>
                            <td>{it.vendor_code_norm}</td>
                            <td>{it.nm_id_sample ?? '—'}</td>
                            <td>Missing RRP</td>
                            <td>
                              <button onClick={() => searchFromGap(it.vendor_code_norm)}>Search</button>{' '}
                              <button onClick={() => applyMissingFilter('rrp')}>Apply filter</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card">
                  <strong>RRP missing Products</strong> (total: {coverage.in_rrp_missing_products.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.in_rrp_missing_products.items.map((it, idx) => (
                          <tr key={`${it.vendor_code_norm}-${idx}`}>
                            <td>—</td>
                            <td>{it.vendor_code_norm}</td>
                            <td>—</td>
                            <td>RRP has item not found in products</td>
                            <td>
                              <button onClick={() => searchFromGap(it.vendor_code_norm)}>Search</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card">
                  <strong>Products missing FBS stock</strong> (total: {coverage.in_products_missing_fbs_stock.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.in_products_missing_fbs_stock.items.map((it, idx) => (
                          <tr key={`${it.nm_id}-${idx}`}>
                            <td>{it.vendor_code_raw_sample || '—'}</td>
                            <td>{it.vendor_code_norm || '—'}</td>
                            <td>{it.nm_id}</td>
                            <td>Missing FBS stock (WB merchant availability)</td>
                            <td>
                              <button onClick={() => searchFromGap(String(it.nm_id))}>Search</button>{' '}
                              <button onClick={() => applyMissingFilter('fbs_stock')}>Apply filter</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card">
                  <strong>Products missing FBO stock</strong> (total: {coverage.in_products_missing_fbo_stock.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.in_products_missing_fbo_stock.items.map((it, idx) => (
                          <tr key={`${it.nm_id}-${idx}`}>
                            <td>{it.vendor_code_raw_sample || '—'}</td>
                            <td>{it.vendor_code_norm || '—'}</td>
                            <td>{it.nm_id}</td>
                            <td>Missing FBO stock (WB warehouses)</td>
                            <td>
                              <button onClick={() => searchFromGap(String(it.nm_id))}>Search</button>{' '}
                              <button onClick={() => applyMissingFilter('fbo_stock')}>Apply filter</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card">
                  <strong>Products missing WB price</strong> (total: {coverage.in_products_missing_wb_price.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.in_products_missing_wb_price.items.map((it, idx) => (
                          <tr key={`${it.nm_id}-${idx}`}>
                            <td>{it.vendor_code_raw_sample || '—'}</td>
                            <td>{it.vendor_code_norm || '—'}</td>
                            <td>{it.nm_id}</td>
                            <td>Missing WB price snapshot</td>
                            <td>
                              <button onClick={() => searchFromGap(String(it.nm_id))}>Search</button>{' '}
                              <button onClick={() => applyMissingFilter('wb_price')}>Apply filter</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card">
                  <strong>Products missing Frontend</strong> (total: {coverage.in_products_missing_front.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.in_products_missing_front.items.map((it, idx) => (
                          <tr key={`${it.nm_id}-${idx}`}>
                            <td>{it.vendor_code_raw_sample || '—'}</td>
                            <td>{it.vendor_code_norm || '—'}</td>
                            <td>{it.nm_id}</td>
                            <td>Missing frontend price</td>
                            <td>
                              <button onClick={() => searchFromGap(String(it.nm_id))}>Search</button>{' '}
                              <button onClick={() => applyMissingFilter('front')}>Apply filter</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="card">
                  <strong>Duplicates vendor_code_norm</strong> (total: {coverage.duplicates_vendor_code_norm.total_count})
                  <div style={{ overflowX: 'auto', marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Vendor Raw</th>
                          <th>Vendor Norm</th>
                          <th>NMID</th>
                          <th>Reason</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverage.duplicates_vendor_code_norm.items.map((it, idx) => (
                          <tr key={`${it.vendor_code_norm}-${idx}`}>
                            <td>{it.vendor_code_raw_sample || '—'}</td>
                            <td>{it.vendor_code_norm}</td>
                            <td>{(it.nm_ids_sample && it.nm_ids_sample.length > 0) ? it.nm_ids_sample[0] : '—'}</td>
                            <td>Duplicate vendor_code_norm (cnt={it.cnt})</td>
                            <td>
                              <button onClick={() => searchFromGap(it.vendor_code_norm)}>Search</button>{' '}
                              <button onClick={clearAllFilters}>Clear filters</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
            <div style={{ marginTop: 10 }}>
              <button onClick={() => loadCoverage(true)} disabled={coverageLoading}>
                {coverageLoading ? 'Refreshing…' : 'Refresh gaps'}
              </button>
            </div>
          </div>
        )}
      </div>

      {debug?.parsed?.completeness && (
        <div className="card" style={{ background: '#f6f8fa', border: '1px solid #e1e4e8' }}>
          <h3 style={{ marginTop: 0 }}>Data completeness (this page)</h3>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div><strong>Items:</strong> {debug.parsed.completeness.page_items}</div>
            <div><strong>WB price:</strong> {debug.parsed.completeness.with_wb_price}</div>
            <div><strong>Frontend:</strong> {debug.parsed.completeness.with_front}</div>
            <div><strong>FBS stock:</strong> {debug.parsed.completeness.with_fbs_stock}</div>
            <div><strong>FBO stock:</strong> {debug.parsed.completeness.with_fbo_stock}</div>
          </div>
          {typeof debug.parsed.elapsed_ms === 'number' && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
              backend elapsed_ms: {debug.parsed.elapsed_ms}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="card" style={{ background: '#f8d7da', border: '1px solid #f5c2c7' }}>
          <p style={{ margin: 0 }}>
            <strong>Error:</strong> {typeof error === 'string' ? error : error.detail}
          </p>
          {typeof error !== 'string' && (
            <div style={{ marginTop: 10, fontSize: 12 }}>
              <div><strong>Status:</strong> {error.status}</div>
              <div><strong>URL:</strong> {error.url}</div>
              <div style={{ marginTop: 8 }}>
                <strong>Body preview:</strong>
                <pre style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>{error.bodyPreview}</pre>
              </div>
            </div>
          )}
        </div>
      )}

      {process.env.NEXT_PUBLIC_DEBUG === 'true' && debug && (
        <div className="card" style={{ background: '#eef6ff', border: '1px solid #b6d4fe' }}>
          <h3 style={{ marginTop: 0 }}>Debug</h3>
          <div style={{ fontSize: 12 }}>
            <div><strong>Status:</strong> {debug.status}</div>
            <div><strong>URL:</strong> {debug.url}</div>
            <div><strong>isJson:</strong> {String(debug.isJson)}</div>
            <div><strong>parsed keys:</strong> {debug.parsed && typeof debug.parsed === 'object' ? Object.keys(debug.parsed).join(', ') : '(none)'}</div>
            <div><strong>total/items:</strong> {debug.parsed?.total ?? '(n/a)'} / {debug.parsed?.items?.length ?? '(n/a)'}</div>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: '20px', marginBottom: '20px' }}>
        <h2>Search & Filters</h2>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
          <input
            type="text"
            placeholder="Search by артикул or NMid..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyPress={handleKeyPress}
            style={{ flex: 1, padding: '8px', fontSize: '14px' }}
          />
          <button onClick={handleSearch}>Search</button>
          {search && (
            <button onClick={() => { setSearch(''); setSearchInput(''); setOffset(0); }}>
              Clear
            </button>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={onlyWithWbStock}
              onChange={(e) => {
                setOnlyWithWbStock(e.target.checked)
                setOffset(0)
              }}
            />
            <span>Только с наличием на ВБ</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={onlyWithOurStock}
              onChange={(e) => {
                setOnlyWithOurStock(e.target.checked)
                setOffset(0)
              }}
            />
            <span>Только с наличием на нашем складе</span>
          </label>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 10 }}>
          <strong>Missing filters (server):</strong>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={missingRrp} onChange={(e) => { setMissingRrp(e.target.checked); setOffset(0) }} />
            Missing RRP
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={missingWbPrice} onChange={(e) => { setMissingWbPrice(e.target.checked); setOffset(0) }} />
            Missing WB price
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={missingFront} onChange={(e) => { setMissingFront(e.target.checked); setOffset(0) }} />
            Missing Frontend
          </label>
          <span style={{ marginLeft: 6, fontSize: 12, color: '#666' }}>| Stock:</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={hasFbsStock} onChange={(e) => { setHasFbsStock(e.target.checked); setOffset(0) }} />
            Has FBS
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={missingFbsStock} onChange={(e) => { setMissingFbsStock(e.target.checked); setOffset(0) }} />
            Missing FBS
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={hasFboStock} onChange={(e) => { setHasFboStock(e.target.checked); setOffset(0) }} />
            Has FBO
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={missingFboStock} onChange={(e) => { setMissingFboStock(e.target.checked); setOffset(0) }} />
            Missing FBO
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={anyMissingStock} onChange={(e) => { setAnyMissingStock(e.target.checked); setOffset(0) }} />
            Missing both (FBS+FBO)
          </label>
          <button onClick={clearAllFilters}>Clear filters</button>
        </div>
        {search && (
          <p style={{ marginTop: '10px', color: '#666' }}>
            Searching for: <strong>{search}</strong>
          </p>
        )}
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          <div className="card">
            <div style={{ marginBottom: '10px' }}>
              <strong>Total: {total}</strong> | Showing {data.length} records
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th title="RRP / WB Stock / WB Price / Frontend">Flags</th>
                    <th onClick={() => handleSort('Артикул')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      Артикул {getSortIcon('Артикул')}
                    </th>
                    <th onClick={() => handleSort('NMid')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      NMid {getSortIcon('NMid')}
                    </th>
                    <th onClick={() => handleSort('ШК')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      ШК {getSortIcon('ШК')}
                    </th>
                    <th onClick={() => handleSort('Наша цена (РРЦ)')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      Наша цена (РРЦ) {getSortIcon('Наша цена (РРЦ)')}
                    </th>
                    <th onClick={() => handleSort('Цена на витрине')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      Цена на витрине {getSortIcon('Цена на витрине')}
                    </th>
                    <th onClick={() => handleSort('Скидка наша')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      Скидка наша {getSortIcon('Скидка наша')}
                    </th>
                    <th onClick={() => handleSort('СПП')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      СПП {getSortIcon('СПП')}
                    </th>
                    <th title="FBS: Товар у продавца. Количество, которое WB показывает покупателю для заказа по FBS.">
                      FBS
                    </th>
                    <th title="FBO: Товар на складах Wildberries (FBO).">
                      FBO
                    </th>
                    <th onClick={() => handleSort('Обновлено WB')} style={{ cursor: 'pointer', userSelect: 'none' }} title="Click to sort">
                      Обновлено WB {getSortIcon('Обновлено WB')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.length === 0 ? (
                    <tr>
                      <td colSpan={11} style={{ textAlign: 'center' }}>No data found</td>
                    </tr>
                  ) : (
                    data.map((row, idx) => (
                      <tr key={`${row['NMid']}-${row['Артикул']}-${idx}`}>
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                          {row.has_fbs_stock ? 'B' : '-'}
                          {row.has_fbo_stock ? 'W' : '-'}
                          {(row as any)['WB Price'] !== null ? 'P' : '-'}
                          {row['Цена на витрине'] !== null || row['СПП'] !== null ? 'F' : '-'}
                        </td>
                        <td>{row['Артикул'] || 'N/A'}</td>
                        <td>{row['NMid'] || 'N/A'}</td>
                        <td>{row['ШК'] || 'N/A'}</td>
                        <td>{formatNumber(row['Наша цена (РРЦ)'])}</td>
                        <td>{formatNumber(row['Цена на витрине'])}</td>
                        <td>{formatNumber(row['Скидка наша'])}</td>
                        <td>{formatInt(row['СПП'])}</td>
                        <td title={row.fbs_stock_updated_at ? `Updated: ${formatDate(row.fbs_stock_updated_at)}` : ''}>
                          {formatInt(row.fbs_stock_qty ?? null)}
                        </td>
                        <td title={row.fbo_stock_updated_at ? `Updated: ${formatDate(row.fbo_stock_updated_at)}` : ''}>
                          {formatInt(row.fbo_stock_qty ?? null)}
                        </td>
                        <td>{formatDate(row.fbs_stock_updated_at || row['Обновлено WB'] || null)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="pagination">
            <button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0}>
              Previous
            </button>
            <span>
              Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)} (Total: {total}, Showing: {data.length})
            </span>
            <button onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}




