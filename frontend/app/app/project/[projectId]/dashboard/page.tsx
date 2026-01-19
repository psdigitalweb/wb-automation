'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPost } from '../../../../../lib/apiClient'
import type { ApiDebug, ApiError } from '../../../../../lib/apiClient'
import '../../../../globals.css'

interface Kpis {
  wb: {
    products_total: number
    warehouses_fbs_total: number
  }
  stock: {
    fbs_in_stock_products: number
    fbo_in_stock_products: number
  }
  prices: {
    wb_prices_products: number
  }
  storefront: {
    storefront_products: number
    expected_storefront_products: number
  }
  rrp_xml: {
    total: number
    with_price: number
    with_stock: number
    with_price_and_stock: number
  }
  last_snapshots: {
    fbs_stock_at: string | null
    fbo_stock_at: string | null
    wb_prices_at: string | null
    storefront_at: string | null
    rrp_at: string | null
  }
}

interface ProjectMarketplace {
  id: number
  marketplace_id: number
  is_enabled: boolean
  marketplace_code: string
  marketplace_name: string
}

interface Project {
  id: number
  name: string
  description: string | null
}

export default function ProjectDashboard() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | string | null>(null)
  const [debug, setDebug] = useState<ApiDebug | null>(null)
  const [wbEnabled, setWbEnabled] = useState(false)
  const [checkingWb, setCheckingWb] = useState(true)
  const [project, setProject] = useState<Project | null>(null)
  const DEBUG_UI = process.env.NEXT_PUBLIC_DEBUG === 'true'

  // Reset state when projectId changes to prevent showing data from previous project
  useEffect(() => {
    setKpis(null)
    setWbEnabled(false)
    setCheckingWb(true)
    setError(null)
    setProject(null)
  }, [projectId])

  useEffect(() => {
    loadProject()
    checkWbEnabled()
    loadKpis()
    const interval = setInterval(loadKpis, 30000)
    return () => clearInterval(interval)
  }, [projectId]) // Include projectId in dependencies

  const loadProject = async () => {
    try {
      const { data } = await apiGet<Project>(`/v1/projects/${projectId}`)
      setProject(data)
    } catch (error) {
      console.error('Failed to load project:', error)
    }
  }

  const checkWbEnabled = async () => {
    try {
      const { data: marketplaces } = await apiGet<ProjectMarketplace[]>(`/v1/projects/${projectId}/marketplaces`)
      const wb = marketplaces.find(m => m.marketplace_code === 'wildberries')
      setWbEnabled(wb?.is_enabled || false)
      setCheckingWb(false)
    } catch (error) {
      console.error('Failed to check WB status:', error)
      setCheckingWb(false)
    }
  }

  const loadKpis = async () => {
    try {
      setError(null)
      setLoading(true)
      const result = await apiGet<Kpis>(`/v1/dashboard/projects/${projectId}/kpis`)
      console.log('kpis result:', result)
      setDebug(result.debug)
      setKpis(result.data)
    } catch (error) {
      console.error('Failed to load metrics:', error)
      setError(error as any)
      setDebug((error as any)?.debug || null)
    } finally {
      setLoading(false)
    }
  }

  const triggerIngest = async (type: string) => {
    if (!wbEnabled) {
      setToast('WB marketplace is not enabled. Enable it in Marketplaces section.')
      setTimeout(() => setToast(null), 5000)
      return
    }

    try {
      setToast(`Starting ${type} ingestion...`)
      const domainMap: Record<string, string> = {
        products: 'products',
        warehouses: 'warehouses',
        stocks: 'stocks',
        'supplier-stocks': 'supplier_stocks',
        prices: 'prices',
      }
      const domain = domainMap[type] || type
      const { data: resp } = await apiPost<{ task_id: string; domain: string; status: string }>(
        `/v1/projects/${projectId}/ingest/run`,
        { domain }
      )
      setToast(`${resp.domain} queued (task: ${resp.task_id})`)
      setTimeout(() => setToast(null), 3000)
      setTimeout(loadKpis, 2000)
    } catch (error: any) {
      setToast(`Error (${type}): ${error.detail || error.message}`)
      setTimeout(() => setToast(null), 3000)
    }
  }

  const triggerFrontendPricesIngest = async () => {
    if (!wbEnabled) {
      setToast('WB marketplace is not enabled. Enable it in Marketplaces section.')
      setTimeout(() => setToast(null), 5000)
      return
    }

    try {
      setToast('Queueing frontend_prices ingestion...')
      const { data: resp } = await apiPost<{ task_id: string; domain: string; status: string }>(
        `/v1/projects/${projectId}/ingest/run`,
        { domain: 'frontend_prices' }
      )
      setToast(`${resp.domain} queued (task: ${resp.task_id})`)
      setTimeout(() => setToast(null), 5000)
      setTimeout(loadKpis, 2000)
    } catch (error: any) {
      setToast(`Error: ${error.detail || error.message}`)
      setTimeout(() => setToast(null), 3000)
    }
  }

  const triggerRrpXmlIngest = async () => {
    try {
      setToast('Starting RRP XML ingestion...')
      const { data: resp } = await apiPost<{ task_id: string; domain: string; status: string }>(
        `/v1/projects/${projectId}/ingest/run`,
        { domain: 'rrp_xml' as any }
      )
      setToast(`${resp.domain} queued (task: ${resp.task_id})`)
      setTimeout(() => setToast(null), 5000)
      setTimeout(loadKpis, 2000)
    } catch (error: any) {
      setToast(`Error: ${error.detail || error.message}`)
      setTimeout(() => setToast(null), 3000)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A'
    return new Date(dateStr).toLocaleString('ru-RU')
  }

  return (
    <div className="container">
      <h1>{project?.name || 'Loading...'}</h1>

      {toast && <div className="toast">{toast}</div>}

      {error && (
        <div className="card" style={{ background: '#f8d7da', border: '1px solid #f5c2c7' }}>
          <p style={{ margin: 0 }}>
            <strong>Error:</strong>{' '}
            {typeof error === 'string' ? error : error.detail}
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

      {DEBUG_UI && debug && (
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

      {!checkingWb && !wbEnabled && (
        <div className="card" style={{ background: '#fff3cd', border: '1px solid #ffc107' }}>
          <p style={{ margin: 0 }}>
            <strong>WB not enabled.</strong> Enable it in{' '}
            <Link href={`/app/project/${projectId}/marketplaces`} style={{ color: '#0070f3', textDecoration: 'underline' }}>
              Marketplaces
            </Link>
            {' '}section to use ingestion features.
          </p>
        </div>
      )}

      <div className="card">
        <h2>KPIs</h2>
        {loading ? (
          <p>Loading...</p>
        ) : error ? (
          <div>
            <p style={{ color: 'red' }}>
              Error: {typeof error === 'string' ? error : error.detail}
            </p>
            <button onClick={loadKpis}>Retry</button>
          </div>
        ) : kpis ? (
          <div className="metrics">
            <div className="metric-card">
              <div className="metric-value">{kpis.wb.products_total}</div>
              <div className="metric-label">WB товары (карточки)</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{kpis.wb.warehouses_fbs_total}</div>
              <div className="metric-label">WB склад (FBS)</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{kpis.stock.fbs_in_stock_products}</div>
              <div className="metric-label">FBS товары в наличии</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{kpis.stock.fbo_in_stock_products}</div>
              <div className="metric-label">FBO товары в наличии</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{kpis.prices.wb_prices_products}</div>
              <div className="metric-label">WB цены (товаров)</div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{kpis.storefront.storefront_products}</div>
              <div className="metric-label">Витрина WB (товаров)</div>
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                expected: {kpis.storefront.expected_storefront_products}
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-value">{kpis.rrp_xml.total}</div>
              <div className="metric-label">Товары компании (1C XML)</div>
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                price: {kpis.rrp_xml.with_price} · stock: {kpis.rrp_xml.with_stock}
              </div>
            </div>
          </div>
        ) : (
          <p>Failed to load metrics</p>
        )}

        {kpis && (
          <div style={{ marginTop: '20px' }}>
            <p><strong>Last FBS Stock Snapshot:</strong> {formatDate(kpis.last_snapshots.fbs_stock_at)}</p>
            <p><strong>Last FBO Stock Snapshot:</strong> {formatDate(kpis.last_snapshots.fbo_stock_at)}</p>
            <p><strong>Last WB Prices Snapshot:</strong> {formatDate(kpis.last_snapshots.wb_prices_at)}</p>
            <p><strong>Last Storefront Snapshot:</strong> {formatDate(kpis.last_snapshots.storefront_at)}</p>
            <p><strong>Last RRP XML Snapshot:</strong> {formatDate(kpis.last_snapshots.rrp_at)}</p>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Ingestion Controls</h2>
        {!wbEnabled && (
          <p style={{ color: '#dc3545', marginBottom: '15px' }}>
            WB not enabled. Enable in{' '}
            <Link href={`/app/project/${projectId}/marketplaces`} style={{ color: '#0070f3' }}>
              Marketplaces
            </Link>
          </p>
        )}
        <button onClick={() => triggerIngest('products')} disabled={!wbEnabled}>
          Run Products Ingestion
        </button>
        <button onClick={() => triggerIngest('warehouses')} disabled={!wbEnabled}>
          Run Warehouses Ingestion
        </button>
        <button onClick={() => triggerIngest('stocks')} disabled={!wbEnabled}>
          Run FBS Stock Ingestion
        </button>
        <button onClick={() => triggerIngest('supplier-stocks')} disabled={!wbEnabled}>
          Run FBO Stock Ingestion
        </button>
        <button onClick={() => triggerIngest('prices')} disabled={!wbEnabled}>
          Run Prices Ingestion
        </button>
        <button onClick={triggerFrontendPricesIngest} disabled={!wbEnabled}>
          Run Frontend Prices Ingestion
        </button>
        <button onClick={triggerRrpXmlIngest}>
          Run RRP XML Ingestion (1C)
        </button>
      </div>

      <div className="card">
        <h2>Navigation</h2>
        <Link href={`/app/project/${projectId}/stocks`}>
          <button>View FBS Stock</button>
        </Link>
        <Link href={`/app/project/${projectId}/supplier-stocks`}>
          <button>View FBO Stock</button>
        </Link>
        <Link href={`/app/project/${projectId}/prices`}>
          <button>View Prices</button>
        </Link>
        <Link href={`/app/project/${projectId}/frontend-prices`}>
          <button>Frontend Prices</button>
        </Link>
        <Link href={`/app/project/${projectId}/articles-base`}>
          <button>Article Base</button>
        </Link>
        <Link href={`/app/project/${projectId}/rrp-snapshots`}>
          <button>RRP Snapshots (1C)</button>
        </Link>
      </div>
    </div>
  )
}

