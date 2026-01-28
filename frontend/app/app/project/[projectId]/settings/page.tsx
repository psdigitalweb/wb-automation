'use client'

import { useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import { apiGet, getWBIngestStatus, runWBIngest, WBIngestStatus } from '../../../../../lib/apiClient'
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

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const [projectData, cogsCoverageData] = await Promise.all([
          apiGet<ProjectDetail>(`/api/v1/projects/${projectId}`),
          apiGet<{
            internal_data_available: boolean
            internal_skus_total: number
            covered_total: number
            missing_total: number
            coverage_pct: number
          }>(`/api/v1/projects/${projectId}/cogs/coverage`).catch(() => null),
        ])
        setProject(projectData.data)

        if (cogsCoverageData) {
          setCogsCoverage(cogsCoverageData.data)
        } else {
          setCogsCoverage(null)
        }
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

  const runIngestWithParams = async (jobCode: string, params?: { date_from?: string; date_to?: string }) => {
    if (!wbEnabled) {
      setToast('WB marketplace is not enabled. Enable it in Marketplaces section.')
      setTimeout(() => setToast(null), 5000)
      return
    }

    try {
      // Optimistic update
      setRunningJobs(prev => new Set(prev).add(jobCode))
      setWbIngestStatuses(prev => prev.map(s => 
        s.job_code === jobCode 
          ? { ...s, is_running: true, last_status: 'queued' }
          : s
      ))

      setToast(`Запуск ${jobCode}...`)
      await runWBIngest(projectId, jobCode, params)
      
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
                              <div>{status.title}</div>
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
                            )}
                            {status.job_code !== 'wb_finances' && status.last_run_at ? (
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
        </>
      )}
    </div>
  )
}



