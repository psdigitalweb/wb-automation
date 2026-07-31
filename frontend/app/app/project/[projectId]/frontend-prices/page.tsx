'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter, useSearchParams, usePathname } from 'next/navigation'
import Link from 'next/link'
import { apiGet } from '../../../../../lib/apiClient'

const PAGE_SIZE = 50

interface FrontendPrice {
  id: number
  snapshot_at: string
  vendor_code: string | null
  query_value: string
  page: number
  nm_id: number
  name: string | null
  price_basic: number | null
  price_product: number | null
  sale_percent: number | null
  discount_calc_percent: number | null
  rrp_price: number | null
  wb_price: number | null
  wb_discount: number | null
  spp_percent: number | null
  final_price: number | null
  total_discount_percent: number | null
}

interface IngestRunOption {
  id: number
  status: string
  started_at: string | null
  finished_at: string | null
  created_at: string
  rows_count?: number | null
}

interface ProjectFrontendPricesMeta {
  brand_id: string | null
  last_run_id: number | null
  last_run_at: string | null
  count_last_run: number
  selected_run_id: number | null
  selected_run_at: string | null
  runs: IngestRunOption[]
}

interface ProjectFrontendPricesResponse {
  meta: ProjectFrontendPricesMeta
  data: FrontendPrice[]
  limit: number
  offset: number
  count: number
  total: number
}

export default function FrontendPricesPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const pathname = usePathname()
  const projectId = params.projectId as string

  const runIdParam = searchParams.get('run_id')
  const selectedRunId = runIdParam ? Number(runIdParam) : null

  const [prices, setPrices] = useState<FrontendPrice[]>([])
  const [meta, setMeta] = useState<ProjectFrontendPricesMeta | null>(null)
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    loadPrices()
  }, [offset, projectId, runIdParam])

  useEffect(() => {
    // When run changes (query param), reset paging.
    setOffset(0)
  }, [runIdParam])

  const loadPrices = async () => {
    setLoading(true)
    try {
      const url =
        `/api/v1/projects/${projectId}/frontend-prices?limit=${PAGE_SIZE}&offset=${offset}` +
        (runIdParam ? `&run_id=${encodeURIComponent(runIdParam)}` : '')
      const res = await apiGet<ProjectFrontendPricesResponse>(url)
      setPrices(res.data.data)
      setMeta(res.data.meta)
      setTotal(res.data.total)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load frontend prices:', error)
      setLoading(false)
    }
  }

  const handleNextPage = () => {
    if (offset + PAGE_SIZE < total) {
      setOffset(prev => prev + PAGE_SIZE)
    }
  }

  const handlePrevPage = () => {
    if (offset > 0) {
      setOffset(prev => prev - PAGE_SIZE)
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU')
  }

  const fmtMoney = (v: number | null): string => {
    if (v === null || v === undefined) return ''
    if (!Number.isFinite(v)) return ''
    return v.toFixed(2)
  }

  const fmtPercent = (v: number | null): string => {
    if (v === null || v === undefined) return ''
    if (!Number.isFinite(v)) return ''
    return `${Math.round(v)}`
  }

  const fmtSpp = (v: number | null): string => {
    if (v === null || v === undefined) return ''
    if (!Number.isFinite(v)) return ''
    if (v < -5 || v > 95) return 'N/A'
    return `${Math.round(v)}`
  }

  const onSelectRun = (newRunId: string) => {
    const qp = new URLSearchParams(searchParams.toString())
    if (newRunId) {
      qp.set('run_id', newRunId)
    } else {
      qp.delete('run_id')
    }
    const qs = qp.toString()
    router.push(qs ? `${pathname}?${qs}` : `${pathname}`)
  }

  const runOptions = meta?.runs || []
  const lastRunAt = meta?.last_run_at
  const countLastRun = meta?.count_last_run ?? 0
  const selectedRunAt = meta?.selected_run_at

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <h1 style={{ margin: 0 }}>Цены на витрине Wildberries</h1>
        <Link href={`/app/project/${projectId}/dashboard`}>
          <span style={{ color: '#2563eb', textDecoration: 'none' }}>← Назад</span>
        </Link>
      </div>

      {loading ? (
        <p>Загрузка цен…</p>
      ) : (
        <>
          <div className="metrics" style={{ marginBottom: '16px' }}>
            <div className="metric-card">
              <div className="metric-value">{countLastRun}</div>
              <div className="metric-label">Цен в последней загрузке</div>
            </div>
            <div className="metric-card">
              <div className="metric-value" style={{ fontSize: '1.2rem' }}>
                {lastRunAt ? formatDate(lastRunAt) : '—'}
              </div>
              <div className="metric-label">Последнее обновление</div>
            </div>
            <div className="metric-card">
              <div className="metric-label" style={{ marginBottom: '8px' }}>
                Загрузка
              </div>
              <select
                value={selectedRunId ? String(selectedRunId) : ''}
                onChange={(e) => onSelectRun(e.target.value)}
                disabled={runOptions.length === 0}
              >
                {runOptions.length === 0 ? (
                  <option value="">Нет загрузок</option>
                ) : (
                  <>
                    <option value="">Последняя</option>
                    {runOptions.map((r) => {
                      const at = r.finished_at || r.started_at || r.created_at
                      const countPart = r.rows_count !== undefined && r.rows_count !== null ? ` • ${r.rows_count}` : ''
                      const label = `${r.id} • ${at ? formatDate(at) : '—'} • ${r.status}${countPart}`
                      return (
                        <option key={r.id} value={String(r.id)}>
                          {label}
                        </option>
                      )
                    })}
                  </>
                )}
              </select>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '8px' }}>
                Админские цены и скидка берутся по состоянию на выбранную загрузку витрины.
              </div>
            </div>
          </div>

          <div className="card">
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Страница</th>
                    <th>NM ID</th>
                    <th>Название</th>
                    <th>Цена на WB</th>
                    <th>Наша скидка %</th>
                    <th>СПП WB %</th>
                    <th>Финальная витринная цена</th>
                  </tr>
                </thead>
                <tbody>
                  {prices.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center' }}>
                        Нет данных для выбранной загрузки
                      </td>
                    </tr>
                  ) : (
                    prices.map((price) => (
                      <tr key={price.id}>
                        <td>{price.page}</td>
                        <td>{price.nm_id}</td>
                        <td>{price.name || ''}</td>
                        <td>{fmtMoney(price.wb_price)}</td>
                        <td>{fmtPercent(price.wb_discount)}</td>
                        <td>{fmtSpp(price.spp_percent)}</td>
                        <td>{fmtMoney(price.final_price)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
          <div className="pagination">
            <button onClick={handlePrevPage} disabled={offset === 0}>Назад</button>
            <span>
              Страница {offset / PAGE_SIZE + 1} из {Math.ceil(total / PAGE_SIZE)}
            </span>
            <button onClick={handleNextPage} disabled={offset + PAGE_SIZE >= total}>Вперёд</button>
          </div>
        </>
      )}
    </div>
  )
}




