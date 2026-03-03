'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPost, apiGetData, getWBFinanceReportsLatest } from '../../../../../lib/apiClient'
import type { ApiDebug, ApiError } from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'

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
  internal_data?: {
    total: number
    with_stock: number
  }
  last_snapshots: {
    fbs_stock_at: string | null
    fbo_stock_at: string | null
    wb_prices_at: string | null
    storefront_at: string | null
    rrp_at: string | null
    internal_data_at?: string | null
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
  usePageTitle('Сводка данных', projectId)
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | string | null>(null)
  const [debug, setDebug] = useState<ApiDebug | null>(null)
  const [wbEnabled, setWbEnabled] = useState(false)
  const [otherMarketplacesEnabled, setOtherMarketplacesEnabled] = useState(false)
  const [checkingWb, setCheckingWb] = useState(true)
  const [project, setProject] = useState<Project | null>(null)
  const [priceDiscrepanciesCount, setPriceDiscrepanciesCount] = useState<number | null>(null)
  const [loadingDiscrepancies, setLoadingDiscrepancies] = useState(false)
  const [latestWbReport, setLatestWbReport] = useState<{
    report_id: number
    period_from: string | null
    period_to: string | null
  } | null>(null)
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

  useEffect(() => {
    if (wbEnabled && projectId) {
      loadPriceDiscrepanciesCount()
    }
  }, [wbEnabled, projectId])

  useEffect(() => {
    if (wbEnabled && projectId) {
      getWBFinanceReportsLatest(projectId).then((r) => {
        if (r) setLatestWbReport({ report_id: r.report_id, period_from: r.period_from, period_to: r.period_to })
        else setLatestWbReport(null)
      })
    } else {
      setLatestWbReport(null)
    }
  }, [wbEnabled, projectId])

  const loadProject = async () => {
    try {
      const { data } = await apiGet<Project>(`/api/v1/projects/${projectId}`)
      setProject(data)
    } catch (error) {
      console.error('Failed to load project:', error)
    }
  }

  const checkWbEnabled = async () => {
    try {
      const { data: marketplaces } = await apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
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
      const result = await apiGet<Kpis>(`/api/v1/dashboard/projects/${projectId}/kpis`)
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

  const loadPriceDiscrepanciesCount = async () => {
    try {
      setLoadingDiscrepancies(true)
      const resp = await apiGetData<{ meta: { total_count: number } }>(
        `/api/v1/projects/${projectId}/wildberries/price-discrepancies?only_below_rrp=true&page_size=1`
      )
      setPriceDiscrepanciesCount(resp.meta?.total_count || 0)
    } catch (error) {
      console.error('Failed to load price discrepancies count:', error)
      setPriceDiscrepanciesCount(0)
    } finally {
      setLoadingDiscrepancies(false)
    }
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <h1 style={{ marginBottom: 20 }}>{project?.name || 'Loading...'}</h1>
        <Link
          href={`/app/project/${projectId}/settings`}
          title="Настройки проекта"
          aria-label="Настройки проекта"
          style={{
            width: 32,
            height: 32,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 8,
            color: '#6b7280',
            textDecoration: 'none',
            userSelect: 'none',
            transition: 'background-color 120ms ease, color 120ms ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = '#f3f4f6'
            e.currentTarget.style.color = '#111827'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent'
            e.currentTarget.style.color = '#6b7280'
          }}
        >
          ⚙
        </Link>
      </div>

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
            {kpis.internal_data && kpis.internal_data.total > 0 && (
              <div style={{ marginBottom: 20 }}>
                <h3 style={{ marginTop: 0, marginBottom: 10 }}>Внутренние данные</h3>
                <div className="metrics">
                  <div className="metric-card" style={{ flex: '2 1 200px' }}>
                    <div className="metric-label" style={{ fontSize: 12, textTransform: 'uppercase', color: '#0d6efd' }}>
                      Товары в наличии
                    </div>
                    <Link href={`/app/project/${projectId}/settings`} style={{ textDecoration: 'none', color: 'inherit' }}>
                      <div className="metric-value" style={{ fontSize: 28, color: '#0d6efd', cursor: 'pointer', textDecoration: 'underline', opacity: 1, transition: 'opacity 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.opacity = '0.7'} onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}>
                        {kpis.internal_data.with_stock || 0}
                      </div>
                    </Link>
                    <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                      Всего товаров: {kpis.internal_data.total}
                    </div>
                    <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                      Обновлено: {formatDate(kpis.last_snapshots.internal_data_at)}
                    </div>
                    <div style={{ marginTop: 8 }}>
                      <Link
                        href={`/app/project/${projectId}/internal-data`}
                        style={{
                          display: 'inline-block',
                          padding: '6px 12px',
                          fontSize: 12,
                          backgroundColor: '#0d6efd',
                          color: 'white',
                          border: 'none',
                          borderRadius: 4,
                          cursor: 'pointer',
                          textDecoration: 'none',
                        }}
                      >
                        Посмотреть данные
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Wildberries — Данные */}
            <div style={{ marginBottom: 32 }}>
              <h3 style={{ marginTop: 0, marginBottom: 12, color: '#374151', fontWeight: 500 }}>Wildberries — Данные</h3>
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
                      <Link href={`/app/project/${projectId}/stocks`} style={{ textDecoration: 'none', color: 'inherit' }}>
                        <div className="metric-value" style={{ fontSize: 20, cursor: 'pointer', textDecoration: 'underline', opacity: 1, transition: 'opacity 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.opacity = '0.7'} onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}>
                          {kpis.stock.fbs_in_stock_products}
                        </div>
                      </Link>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, textTransform: 'uppercase', color: '#6c757d' }}>FBO</div>
                      <Link href={`/app/project/${projectId}/supplier-stocks`} style={{ textDecoration: 'none', color: 'inherit' }}>
                        <div className="metric-value" style={{ fontSize: 20, cursor: 'pointer', textDecoration: 'underline', opacity: 1, transition: 'opacity 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.opacity = '0.7'} onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}>
                          {kpis.stock.fbo_in_stock_products}
                        </div>
                      </Link>
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
                  <Link href={`/app/project/${projectId}/frontend-prices`} style={{ textDecoration: 'none', color: 'inherit' }}>
                    <div className="metric-value" style={{ fontSize: 22, cursor: 'pointer', textDecoration: 'underline', opacity: 1, transition: 'opacity 0.2s' }} onMouseEnter={(e) => e.currentTarget.style.opacity = '0.7'} onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}>
                      {kpis.storefront.storefront_products}
                    </div>
                  </Link>
                  <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                    товаров с ценами на витрине
                  </div>
                  <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
                    Обновлено: {formatDate(kpis.last_snapshots.storefront_at)}
                  </div>
                  {wbEnabled && priceDiscrepanciesCount !== null && priceDiscrepanciesCount > 0 && (
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
                      <span style={{ fontSize: 11, marginRight: 4 }}>⚠</span>
                      <span>{priceDiscrepanciesCount} товаров ниже РРЦ — </span>
                      <Link
                        href={`/app/project/${projectId}/wildberries/price-discrepancies?only_below_rrp=true`}
                        style={{ color: '#2563eb', textDecoration: 'none' }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.textDecoration = 'underline'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.textDecoration = 'none'
                        }}
                      >
                        Расхождения →
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Инструменты */}
            {wbEnabled && (
              <div style={{ marginBottom: 32 }}>
                <h3 style={{ marginTop: 0, marginBottom: 12, color: '#374151', fontWeight: 500 }}>Инструменты</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gridAutoRows: '1fr', gap: 16, alignItems: 'stretch', minHeight: 375 }}>
                  <Link
                    href={`/app/project/${projectId}/wildberries/price-discrepancies?only_below_rrp=true`}
                    style={{ textDecoration: 'none', color: 'inherit', display: 'block', minHeight: 0 }}
                  >
                    <div
                      className="card"
                      style={{
                        padding: 16,
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        background: '#fff',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                        height: '100%',
                        minHeight: 0,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = '#d1d5db'
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = '#e5e7eb'
                        e.currentTarget.style.boxShadow = 'none'
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                          <div style={{ fontSize: 20, flexShrink: 0 }}>📊</div>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>
                            Расхождения цен
                          </div>
                        </div>
                        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6, marginLeft: 30 }}>
                          РРЦ vs витрина Wildberries
                        </div>
                        <div style={{ fontSize: 13, color: '#374151', marginBottom: 8, marginLeft: 30 }}>
                          Контроль соблюдения РРЦ
                        </div>
                        {priceDiscrepanciesCount !== null && priceDiscrepanciesCount > 0 && (
                          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4, marginLeft: 30 }}>
                            <span style={{ fontSize: 11, marginRight: 4 }}>⚠</span>
                            <strong style={{ fontWeight: 600 }}>{priceDiscrepanciesCount}</strong> товаров ниже РРЦ
                          </div>
                        )}
                      </div>
                      <div
                        style={{
                          marginTop: 'auto',
                          fontSize: 13,
                          color: '#2563eb',
                          fontWeight: 500,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.textDecoration = 'underline'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.textDecoration = 'none'
                        }}
                      >
                        Посмотреть расхождения →
                      </div>
                    </div>
                  </Link>

                  <Link
                    href={`/app/project/${projectId}/wildberries/stock-without-photos`}
                    style={{ textDecoration: 'none', color: 'inherit', display: 'block', minHeight: 0 }}
                  >
                    <div
                      className="card"
                      style={{
                        padding: 16,
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        background: '#fff',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                        height: '100%',
                        minHeight: 0,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = '#d1d5db'
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = '#e5e7eb'
                        e.currentTarget.style.boxShadow = 'none'
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                          <div style={{ fontSize: 20, flexShrink: 0 }}>📷</div>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>
                            Остаток WB без фото
                          </div>
                        </div>
                        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6, marginLeft: 30 }}>
                          Товары, которые лежат на складах WB, но в карточке нет фото
                        </div>
                        <div style={{ fontSize: 13, color: '#374151', marginBottom: 8, marginLeft: 30 }}>
                          Контроль наличия фото для товаров с остатком
                        </div>
                      </div>
                      <div
                        style={{
                          marginTop: 'auto',
                          fontSize: 13,
                          color: '#2563eb',
                          fontWeight: 500,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.textDecoration = 'underline'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.textDecoration = 'none'
                        }}
                      >
                        Посмотреть товары →
                      </div>
                    </div>
                  </Link>

                  <div
                    className="card"
                    style={{
                      padding: 16,
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      background: '#fff',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                      height: '100%',
                      minHeight: 0,
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                        <div style={{ fontSize: 20, flexShrink: 0 }}>💰</div>
                        <div style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>
                          Прибыльность WB (Unit PnL)
                        </div>
                      </div>
                      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6, marginLeft: 30 }}>
                        Юнит-экономика по финансовым отчётам Wildberries
                      </div>
                      {latestWbReport && (
                        <div style={{ fontSize: 12, color: '#374151', marginBottom: 8, marginLeft: 30 }}>
                          Последний отчёт:{' '}
                          {latestWbReport.report_id} ·{' '}
                          {latestWbReport.period_from
                            ? new Date(latestWbReport.period_from).toLocaleDateString('ru-RU', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                              })
                            : '—'}
                          –
                          {latestWbReport.period_to
                            ? new Date(latestWbReport.period_to).toLocaleDateString('ru-RU', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                              })
                            : '—'}
                        </div>
                      )}
                      {!latestWbReport && (
                        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8, marginLeft: 30 }}>
                          Нет загруженных финансовых отчётов.{' '}
                          <Link
                            href={`/app/project/${projectId}/wildberries/finances/reports`}
                            style={{ color: '#2563eb', textDecoration: 'underline' }}
                          >
                            Перейти к списку отчётов
                          </Link>
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 'auto', flexWrap: 'wrap' }}>
                      {latestWbReport ? (
                        <Link
                          href={`/app/project/${projectId}/wildberries/finances/unit-pnl?report_id=${latestWbReport.report_id}`}
                          style={{
                            display: 'inline-block',
                            padding: '8px 14px',
                            fontSize: 13,
                            backgroundColor: '#0d6efd',
                            color: 'white',
                            border: 'none',
                            borderRadius: 4,
                            textDecoration: 'none',
                            fontWeight: 500,
                          }}
                        >
                          Открыть последний отчёт
                        </Link>
                      ) : (
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '8px 14px',
                            fontSize: 13,
                            backgroundColor: '#dee2e6',
                            color: '#6c757d',
                            border: 'none',
                            borderRadius: 4,
                            cursor: 'not-allowed',
                          }}
                        >
                          Открыть последний отчёт
                        </span>
                      )}
                      <Link
                        href={`/app/project/${projectId}/wildberries/finances/reports`}
                        style={{
                          display: 'inline-block',
                          padding: '8px 14px',
                          fontSize: 13,
                          backgroundColor: 'transparent',
                          color: '#0d6efd',
                          border: '1px solid #0d6efd',
                          borderRadius: 4,
                          textDecoration: 'none',
                          fontWeight: 500,
                        }}
                      >
                        Список отчётов
                      </Link>
                    </div>
                  </div>

                <Link
                  href={`/app/project/${projectId}/wildberries/funnel-signals`}
                  style={{ textDecoration: 'none', color: 'inherit', display: 'block', minHeight: 0 }}
                >
                    <div
                      className="card"
                      style={{
                        padding: 16,
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        background: '#fff',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                        height: '100%',
                        minHeight: 0,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = '#d1d5db'
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = '#e5e7eb'
                        e.currentTarget.style.boxShadow = 'none'
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                          <div style={{ fontSize: 20, flexShrink: 0 }}>📊</div>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>
                            Воронка: Сигналы
                          </div>
                        </div>
                        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6, marginLeft: 30 }}>
                          Сигналы по воронке: низкий трафик, add-to-cart, конверсия, масштабировать
                        </div>
                        <div style={{ fontSize: 13, color: '#374151', marginBottom: 8, marginLeft: 30 }}>
                          Рекомендации по улучшению воронки конверсии
                        </div>
                      </div>
                      <div
                        style={{
                          marginTop: 'auto',
                          fontSize: 13,
                          color: '#2563eb',
                          fontWeight: 500,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.textDecoration = 'underline'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.textDecoration = 'none'
                        }}
                      >
                        Посмотреть сигналы →
                      </div>
                    </div>
                  </Link>

                  <Link
                    href={`/app/project/${projectId}/wildberries/reviews`}
                    style={{ textDecoration: 'none', color: 'inherit', display: 'block', minHeight: 0 }}
                  >
                    <div
                      className="card"
                      style={{
                        padding: 16,
                        border: '1px solid #e5e7eb',
                        borderRadius: 8,
                        background: '#fff',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 8,
                        height: '100%',
                        minHeight: 0,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = '#d1d5db'
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = '#e5e7eb'
                        e.currentTarget.style.boxShadow = 'none'
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                          <div style={{ fontSize: 20, flexShrink: 0 }}>⭐</div>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>
                            Отзывы WB
                          </div>
                        </div>
                        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6, marginLeft: 30 }}>
                          Рейтинг и динамика отзывов по товарам
                        </div>
                        <div style={{ fontSize: 13, color: '#374151', marginBottom: 8, marginLeft: 30 }}>
                          Мониторинг качества товаров по отзывам покупателей
                        </div>
                      </div>
                      <div
                        style={{
                          marginTop: 'auto',
                          fontSize: 13,
                          color: '#2563eb',
                          fontWeight: 500,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.textDecoration = 'underline'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.textDecoration = 'none'
                        }}
                      >
                        Посмотреть отзывы →
                      </div>
                    </div>
                  </Link>
                </div>
              </div>
            )}

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
    </div>
  )
}

