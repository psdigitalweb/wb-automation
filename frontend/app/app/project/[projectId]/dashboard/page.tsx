'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPost } from '../../../../../lib/apiClient'
import type { ApiDebug, ApiError } from '../../../../../lib/apiClient'
import '../../../../globals.css'
import WBFinancesSection from '../../../../../components/WBFinancesSection'

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
  const [otherMarketplacesEnabled, setOtherMarketplacesEnabled] = useState(false)
  const [checkingWb, setCheckingWb] = useState(true)
  const [project, setProject] = useState<Project | null>(null)
  const DEBUG_UI = process.env.NEXT_PUBLIC_DEBUG === 'true'

  // Reset state when projectId changes to prevent showing data from previous project
  useEffect(() => {
    setKpis(null)
    setWbEnabled(false)
    setOtherMarketplacesEnabled(false)
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
      const otherEnabled = marketplaces.some(
        (m) => m.marketplace_code !== 'wildberries' && m.is_enabled
      )
      setOtherMarketplacesEnabled(otherEnabled)
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
        <h2>Сводка данных</h2>
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
          <>
            {/* Внутренние данные */}
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ marginTop: 0, marginBottom: 10 }}>Внутренние данные</h3>
              <div className="metrics">
                <div className="metric-card" style={{ flex: '2 1 200px' }}>
                  <div className="metric-label" style={{ fontSize: 12, textTransform: 'uppercase', color: '#0d6efd' }}>
                    Товары в наличии (1C XML)
                  </div>
                  <div className="metric-value" style={{ fontSize: 28, color: '#0d6efd' }}>
                    {kpis.rrp_xml.with_stock}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                    Всего товаров: {kpis.rrp_xml.total}
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                    Обновлено: {formatDate(kpis.last_snapshots.rrp_at)}
                  </div>
                </div>
              </div>
            </div>

            {/* Wildberries */}
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ marginTop: 0, marginBottom: 10 }}>Wildberries</h3>
              <div className="metrics">
                {/* Каталог / Витрина */}
                <div className="metric-card">
                  <div className="metric-label" style={{ fontSize: 12, textTransform: 'uppercase', color: '#6c757d' }}>
                    Каталог / Витрина
                  </div>
                  <div className="metric-value" style={{ fontSize: 22 }}>
                    {kpis.wb.products_total}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                    Витрина: {kpis.storefront.storefront_products} (ожидается {kpis.storefront.expected_storefront_products})
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                    Обновлено: {formatDate(kpis.last_snapshots.storefront_at)}
                  </div>
                </div>

                {/* Наличие (FBS / FBO) */}
                <div className="metric-card">
                  <div className="metric-label" style={{ fontSize: 12, textTransform: 'uppercase', color: '#6c757d' }}>
                    Наличие (FBS / FBO)
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 4 }}>
                    <div>
                      <div style={{ fontSize: 11, textTransform: 'uppercase', color: '#6c757d' }}>FBS</div>
                      <div className="metric-value" style={{ fontSize: 20 }}>
                        {kpis.stock.fbs_in_stock_products}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, textTransform: 'uppercase', color: '#6c757d' }}>FBO</div>
                      <div className="metric-value" style={{ fontSize: 20 }}>
                        {kpis.stock.fbo_in_stock_products}
                      </div>
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                    Обновлено (FBS): {formatDate(kpis.last_snapshots.fbs_stock_at)}
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>
                    Обновлено (FBO): {formatDate(kpis.last_snapshots.fbo_stock_at)}
                  </div>
                </div>

                {/* Цены */}
                <div className="metric-card">
                  <div className="metric-label" style={{ fontSize: 12, textTransform: 'uppercase', color: '#6c757d' }}>
                    Цены
                  </div>
                  <div className="metric-value" style={{ fontSize: 22 }}>
                    {kpis.prices.wb_prices_products}
                  </div>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                    товаров c загруженными ценами WB
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                    Обновлено: {formatDate(kpis.last_snapshots.wb_prices_at)}
                  </div>
                </div>
              </div>
            </div>

            {/* Другие маркетплейсы */}
            {otherMarketplacesEnabled && (
              <div>
                <h3 style={{ marginTop: 0, marginBottom: 10 }}>Другие маркетплейсы</h3>
                <div className="metrics">
                  <div className="metric-card" style={{ opacity: 0.8 }}>
                    <div className="metric-label" style={{ fontSize: 12, textTransform: 'uppercase', color: '#6c757d' }}>
                      Данные других маркетплейсов
                    </div>
                    <div style={{ fontSize: 13, color: '#666', marginTop: 4 }}>
                      Метрики будут добавлены по мере подключения модулей для других маркетплейсов.
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : (
          <p>Failed to load metrics</p>
        )}
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

      <WBFinancesSection
        projectId={projectId}
        title="Загрузка финансовых отчетов Wildberries"
      />
    </div>
  )
}

