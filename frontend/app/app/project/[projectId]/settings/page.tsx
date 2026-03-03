'use client'

import { useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import {
  apiGet,
  getProjectProxySettings,
  ProjectProxySettings,
  getWBIngestStatus,
  runWBIngest,
  WBIngestStatus,
} from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'

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
  usePageTitle('Настройки проекта', projectId)
  const [loading, setLoading] = useState(true)
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [wbEnabled, setWbEnabled] = useState(false)
  const [connectedMarketplaces, setConnectedMarketplaces] = useState<ProjectMarketplace[]>([])
  const [cogsCoverage, setCogsCoverage] = useState<{
    internal_data_available: boolean
    internal_skus_total: number
    covered_total: number
    missing_total: number
    coverage_pct: number
  } | null>(null)
  const [cogsLoading, setCogsLoading] = useState(false)

  interface ProjectMarketplace {
    id: number
    marketplace_id: number
    is_enabled: boolean
    marketplace_code: string
    marketplace_name: string
  }

  const [wbIngestStatuses, setWbIngestStatuses] = useState<WBIngestStatus[]>([])
  const [wbIngestLoading, setWbIngestLoading] = useState(false)
  const [runningJobs, setRunningJobs] = useState<Set<string>>(new Set())
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const lastStatusesHashRef = useRef<string>('')
  const [proxySettings, setProxySettings] = useState<ProjectProxySettings | null>(null)
  const [frontendPricesBrandCount, setFrontendPricesBrandCount] = useState<number>(1)
  const [backfillCustomOpen, setBackfillCustomOpen] = useState(false)
  const [backfillDateFrom, setBackfillDateFrom] = useState('')
  const [backfillDateTo, setBackfillDateTo] = useState('')
  const [backfillCustomLoading, setBackfillCustomLoading] = useState(false)
  const [wbCardStatsUseFastPath, setWbCardStatsUseFastPath] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const [projectData, cogsCoverageData, proxyData] = await Promise.all([
          apiGet<ProjectDetail>(`/api/v1/projects/${projectId}`),
          apiGet<{
            internal_data_available: boolean
            internal_skus_total: number
            covered_total: number
            missing_total: number
            coverage_pct: number
          }>(`/api/v1/projects/${projectId}/cogs/coverage`).catch(() => null),
          getProjectProxySettings(projectId).catch(() => null),
        ])
        setProject(projectData.data)

        if (cogsCoverageData) {
          setCogsCoverage(cogsCoverageData.data)
        } else {
          setCogsCoverage(null)
        }

        setProxySettings(proxyData)
      } catch (e: any) {
        setError(e?.detail || 'Failed to load project')
      } finally {
        setLoading(false)
      }
    }
    load()
    checkWbEnabled()
    
    // Cleanup polling on unmount
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    apiGet<{ marketplace_code?: string; settings_json?: { brand_id?: number; frontend_prices?: { brands?: { enabled?: boolean }[] } } }[]>(
      `/api/v1/projects/${projectId}/marketplaces`
    )
      .then(({ data }) => {
        const wb = Array.isArray(data) ? data.find((m: any) => m.marketplace_code === 'wildberries') : null
        const s = wb?.settings_json
        const brands = s?.frontend_prices?.brands
        const n = Array.isArray(brands)
          ? brands.filter((b: any) => b.enabled !== false).length
          : s?.brand_id != null ? 1 : 0
        setFrontendPricesBrandCount(n > 0 ? n : 1)
      })
      .catch(() => setFrontendPricesBrandCount(1))
  }, [projectId])

  // Load ingest statuses when wbEnabled changes
  useEffect(() => {
    if (wbEnabled) {
      loadWBIngestStatuses()
    } else {
      setWbIngestStatuses([])
      stopPolling()
    }
  }, [wbEnabled])

  const checkWbEnabled = async () => {
    try {
      const { data: marketplaces } = await apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
      const enabled = (marketplaces || []).filter((m) => m.is_enabled)
      setConnectedMarketplaces(enabled)
      const wb = marketplaces.find(m => m.marketplace_code === 'wildberries')
      setWbEnabled(wb?.is_enabled || false)
    } catch (error) {
      console.error('Failed to check WB status:', error)
    }
  }

  const normalizeStatuses = (items: WBIngestStatus[]) => {
    // Stable ordering to avoid row jumping on refresh
    return [...items].sort((a, b) => String(a.job_code).localeCompare(String(b.job_code)))
  }

  const computeStatusesHash = (items: WBIngestStatus[]) => {
    // Hash only fields that affect this table rendering
    return JSON.stringify(
      items.map((s) => ({
        job_code: s.job_code,
        title: s.title,
        has_schedule: s.has_schedule,
        schedule_summary: s.schedule_summary,
        last_run_at: s.last_run_at,
        last_status: s.last_status,
        is_running: s.is_running,
      }))
    )
  }

  const loadWBIngestStatuses = async (opts?: { silent?: boolean }) => {
    if (!wbEnabled) {
      setWbIngestStatuses([])
      return
    }
    try {
      if (!opts?.silent) setWbIngestLoading(true)
      const statuses = await getWBIngestStatus(projectId)

      const normalized = normalizeStatuses(statuses)
      const nextHash = computeStatusesHash(normalized)
      if (nextHash !== lastStatusesHashRef.current) {
        lastStatusesHashRef.current = nextHash
        setWbIngestStatuses(normalized)
      }
      
      // Update running jobs set
      const running = new Set<string>()
      normalized.forEach(s => {
        if (s.is_running) {
          running.add(s.job_code)
        }
      })
      setRunningJobs((prev) => {
        // Avoid rerender if unchanged
        if (prev.size === running.size && [...prev].every((x) => running.has(x))) return prev
        return running
      })
      
      // Start polling if any job is running
      if (running.size > 0 && !pollingIntervalRef.current) {
        startPolling()
      } else if (running.size === 0 && pollingIntervalRef.current) {
        stopPolling()
      }
    } catch (error) {
      console.error('Failed to load WB ingest statuses:', error)
    } finally {
      if (!opts?.silent) setWbIngestLoading(false)
    }
  }

  const startPolling = () => {
    if (pollingIntervalRef.current) return
    setIsPolling(true)
    pollingIntervalRef.current = setInterval(() => {
      loadWBIngestStatuses({ silent: true })
    }, 10000) // Poll every 10 seconds (stable UI)
  }

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    setIsPolling(false)
  }

  const handleRunIngest = async (jobCode: string) => {
    if (!wbEnabled) {
      setToast('WB marketplace is not enabled. Enable it in Marketplaces section.')
      setTimeout(() => setToast(null), 5000)
      return
    }

    // For wb_finances, manual запуск перенесён на страницу отчётов
    if (jobCode === 'wb_finances') {
      setToast('Ручная загрузка финансовых отчётов перенесена на страницу «Финансовые отчёты».')
      setTimeout(() => setToast(null), 5000)
      return
    }

    // For other jobs, run immediately
    await runIngestWithParams(jobCode)
  }

  const runIngestWithParams = async (
    jobCode: string,
    params?: {
      date_from?: string
      date_to?: string
      mode?: 'daily' | 'backfill'
      max_seconds?: number
      max_batches?: number
      cursor?: { date: string; nm_offset: number }
      use_fast_path?: boolean
    }
  ) => {
    if (!wbEnabled) {
      setToast('WB marketplace is not enabled. Enable it in Marketplaces section.')
      setTimeout(() => setToast(null), 5000)
      return
    }

    const finalParams =
      jobCode === 'wb_card_stats_daily'
        ? { ...params, use_fast_path: params?.use_fast_path ?? wbCardStatsUseFastPath }
        : params

    try {
      // Optimistic update
      setRunningJobs(prev => new Set(prev).add(jobCode))
      setWbIngestStatuses(prev => prev.map(s =>
        s.job_code === jobCode
          ? { ...s, is_running: true, last_status: 'queued' }
          : s
      ))

      setToast(`Запуск ${jobCode}...`)
      await runWBIngest(projectId, jobCode, finalParams)
      
      // Start polling to track progress
      if (!pollingIntervalRef.current) {
        startPolling()
      }
      
      // Reload statuses after a short delay
      setTimeout(() => {
        loadWBIngestStatuses()
      }, 1000)
      
      setToast(`Ингест ${jobCode} запущен`)
      setTimeout(() => setToast(null), 3000)
    } catch (error: any) {
      // Revert optimistic update
      setRunningJobs(prev => {
        const next = new Set(prev)
        next.delete(jobCode)
        return next
      })
      setWbIngestStatuses(prev => prev.map(s => 
        s.job_code === jobCode 
          ? { ...s, is_running: false }
          : s
      ))
      
      setToast(`Ошибка (${jobCode}): ${error.detail || error.message}`)
      setTimeout(() => setToast(null), 5000)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—'
    try {
      return new Date(dateStr).toLocaleString('ru-RU')
    } catch {
      return '—'
    }
  }

  const getStatusIcon = (status: string | null, isRunning: boolean) => {
    if (isRunning) {
      return <span style={{ color: '#2563eb' }}>⟳</span>
    }
    if (status === 'success') {
      return <span style={{ color: '#28a745' }}>✓</span>
    }
    if (status === 'failed') {
      return <span style={{ color: '#dc3545' }}>✗</span>
    }
    return <span style={{ color: '#999' }}>—</span>
  }

  const frontendPricesProxyEnabled = !!proxySettings?.enabled

  const formatDateTime = (value: string | null | undefined) => {
    if (!value) return '—'
    try {
      return new Date(value).toLocaleString('ru-RU')
    } catch {
      return value
    }
  }


  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>{project ? `Настройки проекта ${project.name}` : 'Project Settings'}</h1>
        <Link href="/app/projects">← Проекты</Link>
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
            <div style={{ marginTop: '14px' }}>
              <div style={{ fontSize: '0.9rem', color: '#666', marginBottom: '6px' }}>
                Подключённые маркетплейсы
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {connectedMarketplaces.length === 0 ? (
                  <span style={{ color: '#999', fontSize: '0.9rem' }}>—</span>
                ) : (
                  connectedMarketplaces.map((mp) => (
                    <span
                      key={`${mp.marketplace_code}-${mp.id}`}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '4px 10px',
                        borderRadius: '999px',
                        fontSize: '0.85rem',
                        fontWeight: 600,
                        backgroundColor: '#eef2ff',
                        color: '#1e40af',
                      }}
                    >
                      {mp.marketplace_name || mp.marketplace_code}
                    </span>
                  ))
                )}
              </div>
            </div>
            <div style={{ marginTop: '12px', color: '#999', fontSize: '0.9rem' }}>
              <div>Updated: {new Date(project.updated_at).toLocaleString()}</div>
              <div>Members: {project.members?.length ?? 0}</div>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <h2 style={{ marginTop: 0 }}>Быстрый доступ</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              <Link href={`/app/project/${projectId}/dashboard`}>
                <button>На страницу проекта</button>
              </Link>
              <Link href={`/app/project/${projectId}/marketplaces`}>
                <button>Подключение маркетплейсов</button>
              </Link>
              <Link href={`/app/project/${projectId}/members`}>
                <button>Пользователи</button>
              </Link>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
                <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Загрузка данных WB</h2>
                {isPolling && (
                  <span style={{ color: '#999', fontSize: '0.85rem' }}>⟳ обновление…</span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px' }}>
                <Link
                  href={`/app/project/${projectId}/wildberries/finances/reports`}
                  style={{
                    fontSize: '0.9rem',
                    color: '#1e40af',
                    textDecoration: 'none',
                    padding: '6px 10px',
                    borderRadius: '999px',
                    backgroundColor: '#eef2ff',
                    border: '1px solid #c7d2fe',
                    fontWeight: 600,
                  }}
                >
                  Финансовые отчёты →
                </Link>
                <Link
                  href={`/app/project/${projectId}/wildberries/finances/sku-pnl`}
                  style={{
                    fontSize: '0.9rem',
                    color: '#1e40af',
                    textDecoration: 'none',
                    padding: '6px 10px',
                    borderRadius: '999px',
                    backgroundColor: '#eef2ff',
                    border: '1px solid #c7d2fe',
                    fontWeight: 600,
                  }}
                >
                  SKU PnL →
                </Link>
                <Link
                  href={`/app/project/${projectId}/ingestion`}
                  style={{ fontSize: '0.9rem', color: '#2563eb', textDecoration: 'none' }}
                >
                  Настройка расписания загрузки данных →
                </Link>
              </div>
            </div>
            <p style={{ color: '#666', marginBottom: '20px', fontSize: '0.95rem' }}>
              Состояние и управление загрузками данных из Wildberries.
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

            {wbIngestStatuses.length === 0 ? (
              <p style={{ color: '#666' }}>Нет доступных ингестов</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #ddd' }}>
                      <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>Название</th>
                      <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>Расписание</th>
                      <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>Последнее обновление</th>
                      <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wbIngestStatuses.map((status) => (
                      <tr key={status.job_code} style={{ borderBottom: '1px solid #eee' }}>
                        <td style={{ padding: '12px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            {getStatusIcon(status.last_status, status.is_running)}
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span>{status.title}</span>
                                {status.job_code === 'frontend_prices' && (
                                  <span
                                    style={{
                                      display: 'inline-block',
                                      padding: '2px 8px',
                                      borderRadius: '999px',
                                      backgroundColor: '#f3f4f6',
                                      color: '#374151',
                                      fontSize: 11,
                                      fontWeight: 600,
                                    }}
                                  >
                                    Брендов: {frontendPricesBrandCount}
                                  </span>
                                )}
                                {status.job_code === 'frontend_prices' && frontendPricesProxyEnabled && (
                                  <span
                                    style={{
                                      display: 'inline-block',
                                      padding: '2px 8px',
                                      borderRadius: '999px',
                                      backgroundColor: '#e0f2fe',
                                      color: '#0369a1',
                                      fontSize: 11,
                                      fontWeight: 600,
                                    }}
                                  >
                                    proxy
                                  </span>
                                )}
                              </div>
                              {status.job_code === 'frontend_prices' && (
                                <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '2px' }}>
                                  Примечание: перед загрузкой витринных цен автоматически обновляются «Цены WB» (prices).
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: '12px', color: '#666' }}>
                          {status.has_schedule ? (
                            <span>{status.schedule_summary || 'По расписанию'}</span>
                          ) : (
                            <span style={{ color: '#999' }}>Не настроено</span>
                          )}
                        </td>
                        <td style={{ padding: '12px', color: '#666' }}>
                          {formatDate(status.last_run_at)}
                        </td>
                        <td style={{ padding: '12px' }}>
                          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                            {status.job_code === 'wb_finances' ? (
                              <Link
                                href={`/app/project/${projectId}/wildberries/finances/reports`}
                                style={{
                                  fontSize: '0.9rem',
                                  color: '#2563eb',
                                  textDecoration: 'none',
                                  fontWeight: 600,
                                }}
                              >
                                Финансовые отчёты →
                              </Link>
                            ) : (
                              <>
                                <button
                                  onClick={() => handleRunIngest(status.job_code)}
                                  disabled={!wbEnabled || status.is_running}
                                  style={{
                                    padding: '6px 12px',
                                    backgroundColor: status.is_running ? '#ccc' : '#2563eb',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: status.is_running ? 'not-allowed' : 'pointer',
                                    fontSize: '0.9rem',
                                  }}
                                >
                                  {status.is_running ? 'Выполняется…' : 'Загрузить сейчас'}
                                </button>
                                {status.job_code === 'wb_card_stats_daily' && (
                                  <>
                                    <label
                                      style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: 6,
                                        fontSize: '0.85rem',
                                        marginRight: 8,
                                      }}
                                      title="Быстрый сбор через batched WB endpoint (/sales-funnel/products)"
                                    >
                                      <input
                                        type="checkbox"
                                        checked={wbCardStatsUseFastPath}
                                        onChange={e => setWbCardStatsUseFastPath(e.target.checked)}
                                        style={{ margin: 0 }}
                                      />
                                      <span>Fast path</span>
                                    </label>
                                    <span style={{ fontSize: '0.75rem', color: '#6b7280', marginRight: 8 }}>
                                      Batched endpoint
                                    </span>
                                    <button
                                      onClick={async () => {
                                        if (!wbEnabled || status.is_running) return
                                        try {
                                          setRunningJobs(prev => new Set(prev).add('wb_card_stats_daily'))
                                          setWbIngestStatuses(prev =>
                                            prev.map(s =>
                                              s.job_code === 'wb_card_stats_daily'
                                                ? { ...s, is_running: true, last_status: 'queued' as const }
                                                : s
                                            )
                                          )
                                          await runWBIngest(projectId, 'wb_card_stats_daily', {
                                            mode: 'backfill',
                                            max_seconds: 900,
                                            max_batches: 200,
                                            use_fast_path: wbCardStatsUseFastPath,
                                          })
                                          setToast('Backfill started')
                                          setTimeout(() => setToast(null), 3000)
                                          if (!pollingIntervalRef.current) startPolling()
                                          setTimeout(() => loadWBIngestStatuses(), 1000)
                                        } catch (err: unknown) {
                                          setRunningJobs(prev => {
                                            const next = new Set(prev)
                                            next.delete('wb_card_stats_daily')
                                            return next
                                          })
                                          setWbIngestStatuses(prev =>
                                            prev.map(s =>
                                              s.job_code === 'wb_card_stats_daily' ? { ...s, is_running: false } : s
                                            )
                                          )
                                          setToast(`Ошибка: ${(err as { detail?: string }).detail || (err as Error).message}`)
                                          setTimeout(() => setToast(null), 5000)
                                        }
                                      }}
                                      disabled={!wbEnabled || status.is_running}
                                      style={{
                                        padding: '6px 12px',
                                        backgroundColor: status.is_running ? '#ccc' : '#f59e0b',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '4px',
                                        cursor: status.is_running ? 'not-allowed' : 'pointer',
                                        fontSize: '0.9rem',
                                      }}
                                    >
                                      Backfill 30 days
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        const today = new Date()
                                        setBackfillDateTo(today.toISOString().slice(0, 10))
                                        const from = new Date(today)
                                        from.setDate(from.getDate() - 29)
                                        setBackfillDateFrom(from.toISOString().slice(0, 10))
                                        setBackfillCustomOpen(true)
                                      }}
                                      disabled={!wbEnabled || status.is_running}
                                      style={{
                                        padding: '6px 12px',
                                        backgroundColor: status.is_running ? '#ccc' : '#6b7280',
                                        color: 'white',
                                        border: 'none',
                                        borderRadius: '4px',
                                        cursor: status.is_running ? 'not-allowed' : 'pointer',
                                        fontSize: '0.9rem',
                                      }}
                                    >
                                      Backfill custom…
                                    </button>
                                  </>
                                )}
                              </>
                            )}
                            {status.job_code !== 'wb_finances' && (status.last_run_at || status.job_code === 'wb_card_stats_daily') ? (
                              <Link
                                href={`/app/project/${projectId}/ingestion?job_code=${status.job_code}`}
                                style={{
                                  fontSize: '0.9rem',
                                  color: '#2563eb',
                                  textDecoration: 'none',
                                }}
                              >
                                История запусков
                              </Link>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card" style={{ padding: '20px', marginTop: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Прокси для витрины WB</h2>
                {proxySettings && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px 10px',
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 600,
                      backgroundColor: proxySettings.enabled ? '#dcfce7' : '#f3f4f6',
                      color: proxySettings.enabled ? '#166534' : '#4b5563',
                      border: '1px solid ' + (proxySettings.enabled ? '#a7f3d0' : '#e5e7eb'),
                    }}
                  >
                    {proxySettings.enabled ? 'включено' : 'выключено'}
                  </span>
                )}
              </div>
              <Link
                href={`/app/project/${projectId}/settings/proxy`}
                style={{ fontSize: '0.9rem', color: '#2563eb', textDecoration: 'none' }}
              >
                Открыть →
              </Link>
            </div>
            <p style={{ color: '#666', marginBottom: '12px', fontSize: '0.95rem' }}>
              Прокси применяется только для загрузки витринных цен (frontend_prices).
            </p>
            {proxySettings && (
              <div style={{ fontSize: '0.9rem', color: '#6b7280' }}>
                <div>
                  Последняя проверка: <strong>{formatDateTime(proxySettings.last_test_at)}</strong>{' '}
                  {proxySettings.last_test_ok === true ? (
                    <span style={{ color: '#166534' }}>OK</span>
                  ) : proxySettings.last_test_ok === false ? (
                    <span style={{ color: '#b91c1c' }}>Ошибка</span>
                  ) : (
                    <span style={{ color: '#6b7280' }}>—</span>
                  )}
                </div>
                {proxySettings.last_test_ok === false && proxySettings.last_test_error ? (
                  <div style={{ marginTop: 4, color: '#b91c1c' }}>{proxySettings.last_test_error}</div>
                ) : null}
              </div>
            )}
            <div style={{ marginTop: 14 }}>
              <Link href={`/app/project/${projectId}/settings/proxy`}>
                <button>Настроить прокси</button>
              </Link>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Загрузка каталога</h2>
            </div>
            <p style={{ color: '#666', marginBottom: '20px', fontSize: '0.95rem' }}>
              Настройка источников внутренних данных о товарах: загрузка из URL или файла, сопоставление полей, категории.
            </p>
            <div>
              <Link href={`/app/project/${projectId}/internal-data/settings`}>
                <button>Открыть настройки</button>
              </Link>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Настройка себестоимости</h2>
              <Link
                href={`/app/project/${projectId}/cogs`}
                style={{ fontSize: '0.9rem', color: '#2563eb', textDecoration: 'none' }}
              >
                Управление правилами расчета себестоимости →
              </Link>
            </div>
            <p style={{ color: '#666', marginBottom: '20px', fontSize: '0.95rem' }}>
              Настройка правил расчета себестоимости товаров.
            </p>

            {cogsLoading ? (
              <p style={{ color: '#666' }}>Загрузка статистики...</p>
            ) : !cogsCoverage ? (
              <div style={{ marginBottom: '20px' }}>
                <p style={{ color: '#666', fontSize: '0.9rem', marginBottom: '12px' }}>
                  Покрытие себестоимости: —
                </p>
                <div>
                  <Link href={`/app/project/${projectId}/cogs`}>
                    <button>Управление правилами расчета себестоимости</button>
                  </Link>
                </div>
              </div>
            ) : !cogsCoverage.internal_data_available ? (
              <div style={{ marginBottom: '20px' }}>
                <p style={{ color: '#666', fontSize: '0.9rem', marginBottom: '12px' }}>
                  Покрытие себестоимости: — (нет Internal Data)
                </p>
                <div>
                  <Link href={`/app/project/${projectId}/cogs`}>
                    <button>Управление правилами расчета себестоимости</button>
                  </Link>
                </div>
              </div>
            ) : (
              <div style={{ marginBottom: '20px' }}>
                <p style={{ color: '#666', fontSize: '0.9rem', marginBottom: '12px' }}>
                  Покрытие себестоимости: {cogsCoverage.coverage_pct.toFixed(1)}%
                </p>
                <div style={{ marginTop: '12px' }}>
                  <Link href={`/app/project/${projectId}/cogs`}>
                    <button>Управление правилами расчета себестоимости</button>
                  </Link>
                </div>
              </div>
            )}
          </div>

          <div className="card" style={{ padding: '20px', marginTop: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Управление расходами</h2>
              <Link
                href={`/app/project/${projectId}/additional-costs`}
                style={{ fontSize: '0.9rem', color: '#2563eb', textDecoration: 'none' }}
              >
                Открыть →
              </Link>
            </div>
            <p style={{ color: '#666', marginBottom: '20px', fontSize: '0.95rem' }}>
              Учет дополнительных расходов проекта: маркетинг, логистика, налоги и другие затраты.
            </p>
            <div>
              <Link href={`/app/project/${projectId}/additional-costs`}>
                <button>Открыть</button>
              </Link>
            </div>
          </div>

          <div className="card" style={{ padding: '20px', marginTop: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <h2 style={{ marginTop: 0, marginBottom: '8px' }}>Налоги</h2>
              <Link
                href={`/app/project/${projectId}/settings/taxes`}
                style={{ fontSize: '0.9rem', color: '#2563eb', textDecoration: 'none' }}
              >
                Управление налогами →
              </Link>
            </div>
            <p style={{ color: '#666', marginBottom: '20px', fontSize: '0.95rem' }}>
              Профили и расчёт налогов по периодам.
            </p>
            <div>
              <Link href={`/app/project/${projectId}/settings/taxes`}>
                <button>Открыть настройки налогов</button>
              </Link>
            </div>
          </div>

          {backfillCustomOpen && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 50,
              }}
              onClick={() => !backfillCustomLoading && setBackfillCustomOpen(false)}
            >
              <div
                className="card"
                style={{ padding: 24, minWidth: 320, maxWidth: 400 }}
                onClick={e => e.stopPropagation()}
              >
                <h3 style={{ marginTop: 0, marginBottom: 16 }}>Backfill wb_card_stats_daily</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
                  <label style={{ fontSize: 14, fontWeight: 500 }}>
                    date_from (YYYY-MM-DD)
                    <input
                      type="date"
                      value={backfillDateFrom}
                      onChange={e => setBackfillDateFrom(e.target.value)}
                      style={{ display: 'block', marginTop: 4, padding: '6px 10px', width: '100%' }}
                    />
                  </label>
                  <label style={{ fontSize: 14, fontWeight: 500 }}>
                    date_to (YYYY-MM-DD)
                    <input
                      type="date"
                      value={backfillDateTo}
                      onChange={e => setBackfillDateTo(e.target.value)}
                      style={{ display: 'block', marginTop: 4, padding: '6px 10px', width: '100%' }}
                    />
                  </label>
                </div>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={() => !backfillCustomLoading && setBackfillCustomOpen(false)}
                    disabled={backfillCustomLoading}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={backfillCustomLoading || !backfillDateFrom || !backfillDateTo}
                    onClick={async () => {
                      if (!backfillDateFrom || !backfillDateTo) return
                      setBackfillCustomLoading(true)
                      try {
                        setRunningJobs(prev => new Set(prev).add('wb_card_stats_daily'))
                        setWbIngestStatuses(prev =>
                          prev.map(s =>
                            s.job_code === 'wb_card_stats_daily'
                              ? { ...s, is_running: true, last_status: 'queued' as const }
                              : s
                          )
                        )
                        await runWBIngest(projectId, 'wb_card_stats_daily', {
                          mode: 'backfill',
                          date_from: backfillDateFrom,
                          date_to: backfillDateTo,
                          max_seconds: 900,
                          max_batches: 200,
                          use_fast_path: wbCardStatsUseFastPath,
                        })
                        setToast('Backfill started')
                        setTimeout(() => setToast(null), 3000)
                        setBackfillCustomOpen(false)
                        if (!pollingIntervalRef.current) startPolling()
                        setTimeout(() => loadWBIngestStatuses(), 1000)
                      } catch (err: unknown) {
                        setRunningJobs(prev => {
                          const next = new Set(prev)
                          next.delete('wb_card_stats_daily')
                          return next
                        })
                        setWbIngestStatuses(prev =>
                          prev.map(s =>
                            s.job_code === 'wb_card_stats_daily' ? { ...s, is_running: false } : s
                          )
                        )
                        setToast(`Ошибка: ${(err as { detail?: string }).detail || (err as Error).message}`)
                        setTimeout(() => setToast(null), 5000)
                      } finally {
                        setBackfillCustomLoading(false)
                      }
                    }}
                  >
                    {backfillCustomLoading ? 'Запуск…' : 'Start'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}



