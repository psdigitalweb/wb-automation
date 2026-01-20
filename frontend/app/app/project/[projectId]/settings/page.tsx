'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { apiGet, apiPost } from '../../../../../lib/apiClient'

interface ProjectMember {
  id: number
  user_id: number
  role: string
  username?: string | null
  email?: string | null
}

interface ProjectDetail {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string
  members: ProjectMember[]
}

export default function ProjectSettingsPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  const [loading, setLoading] = useState(true)
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [wbEnabled, setWbEnabled] = useState(false)

  interface WBMarketplaceStatus {
    is_enabled: boolean
    has_token: boolean
    brand_id: number | null
    connected: boolean
    updated_at: string
  }

  interface ProjectMarketplace {
    id: number
    marketplace_id: number
    is_enabled: boolean
    marketplace_code: string
    marketplace_name: string
  }

  const [wbStatus, setWbStatus] = useState<WBMarketplaceStatus | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const [projectData, wbStatusData] = await Promise.all([
          apiGet<ProjectDetail>(`/v1/projects/${projectId}`),
          apiGet<WBMarketplaceStatus>(`/v1/projects/${projectId}/marketplaces/wildberries`).catch(() => null),
        ])
        setProject(projectData.data)

        if (wbStatusData) {
          setWbStatus(wbStatusData.data)
        } else {
          setWbStatus(null)
        }
      } catch (e: any) {
        setError(e?.detail || 'Failed to load project')
      } finally {
        setLoading(false)
      }
    }
    load()
    checkWbEnabled()
  }, [projectId])

  const checkWbEnabled = async () => {
    try {
      const { data: marketplaces } = await apiGet<ProjectMarketplace[]>(`/v1/projects/${projectId}/marketplaces`)
      const wb = marketplaces.find(m => m.marketplace_code === 'wildberries')
      setWbEnabled(wb?.is_enabled || false)
    } catch (error) {
      console.error('Failed to check WB status:', error)
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
    } catch (error: any) {
      setToast(`Error: ${error.detail || error.message}`)
      setTimeout(() => setToast(null), 3000)
    }
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Project Settings</h1>
        <Link href="/app/projects">← Back to projects</Link>
      </div>

      {toast && <div className="toast">{toast}</div>}

      {loading ? (
        <p>Loading...</p>
      ) : error ? (
        <div className="card">
          <p style={{ color: 'crimson' }}>{error}</p>
        </div>
      ) : !project ? (
        <div className="card">
          <p>Project not found</p>
        </div>
      ) : (
        <>
          <div className="card" style={{ padding: '20px' }}>
            <h2 style={{ marginTop: 0 }}>{project.name}</h2>
            {project.description && <p style={{ color: '#666' }}>{project.description}</p>}
            <div style={{ marginTop: '12px', color: '#999', fontSize: '0.9rem' }}>
              <div>Updated: {new Date(project.updated_at).toLocaleString()}</div>
              <div>Members: {project.members?.length ?? 0}</div>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <h2 style={{ marginTop: 0 }}>Quick actions</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              <Link href={`/app/project/${projectId}/dashboard`}>
                <button>Open dashboard</button>
              </Link>
              <Link href={`/app/project/${projectId}/marketplaces`}>
                <button>Marketplaces</button>
              </Link>
              <Link href={`/app/project/${projectId}/members`}>
                <button>Members</button>
              </Link>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
              <h2 style={{ marginTop: 0, marginBottom: 0 }}>Wildberries</h2>
              <span
                style={{
                  padding: '4px 8px',
                  borderRadius: '999px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  backgroundColor: wbStatus?.connected ? '#d4edda' : '#e2e3e5',
                  color: wbStatus?.connected ? '#155724' : '#383d41',
                }}
              >
                {wbStatus?.connected ? 'Подключено' : 'Не подключено'}
              </span>
            </div>
            <p style={{ color: '#666', marginBottom: 0 }}>
              {wbStatus?.connected
                ? 'Маркетплейс подключён. Токен сохранён.'
                : 'Маркетплейс не подключён. Подключение выполняется в разделе Маркетплейсы.'}
            </p>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Управление загрузкой данных</h2>
            <p style={{ color: '#666', marginBottom: '20px', fontSize: '0.95rem' }}>
              Ручной запуск загрузки данных из внешних источников.
            </p>

            {!wbEnabled && (
              <div style={{ 
                padding: '12px', 
                marginBottom: '20px', 
                backgroundColor: '#fff3cd', 
                border: '1px solid #ffc107',
                borderRadius: '4px'
              }}>
                <p style={{ margin: 0, color: '#856404' }}>
                  <strong>WB не включен.</strong> Включите его в разделе{' '}
                  <Link href={`/app/project/${projectId}/marketplaces`} style={{ color: '#0070f3' }}>
                    Маркетплейсы
                  </Link>
                  {' '}для использования функций загрузки Wildberries.
                </p>
              </div>
            )}

            {/* Группа Wildberries */}
            <div style={{ marginBottom: '24px' }}>
              <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '1.1rem' }}>Wildberries</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                <button onClick={() => triggerIngest('products')} disabled={!wbEnabled}>
                  Загрузка каталога товаров
                </button>
                <button onClick={() => triggerIngest('warehouses')} disabled={!wbEnabled}>
                  Загрузка складов
                </button>
                <button onClick={() => triggerIngest('stocks')} disabled={!wbEnabled}>
                  Загрузка остатков FBS
                </button>
                <button onClick={() => triggerIngest('supplier-stocks')} disabled={!wbEnabled}>
                  Загрузка остатков FBO
                </button>
                <button onClick={() => triggerIngest('prices')} disabled={!wbEnabled}>
                  Загрузка цен WB
                </button>
                <button onClick={triggerFrontendPricesIngest} disabled={!wbEnabled}>
                  Загрузка цен с витрины
                </button>
              </div>
            </div>

            {/* Группа Внутренние данные */}
            <div>
              <h3 style={{ marginTop: 0, marginBottom: '12px', fontSize: '1.1rem' }}>Внутренние данные</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                <button onClick={triggerRrpXmlIngest}>
                  Загрузка XML цен (1С)
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}



