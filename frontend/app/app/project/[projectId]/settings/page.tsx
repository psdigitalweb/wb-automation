'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import {
  apiGet,
  getWBIngestStatus,
  markIngestRunTimeout,
  runWBIngest,
  WBIngestStatus,
} from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'
import styles from './settings.module.css'

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

interface ProjectMarketplace {
  id: number
  marketplace_id: number
  is_enabled: boolean
  marketplace_code: string
  marketplace_name: string
  settings_json?: {
    brand_id?: number
    frontend_prices?: {
      brands?: { enabled?: boolean }[]
    }
  } | null
}

type RunParams = {
  date_from?: string
  date_to?: string
  mode?: 'daily' | 'backfill' | 'reviews_full_sync' | 'reviews_incremental_all_nm_ids'
  max_seconds?: number
  max_batches?: number
  cursor?: { date: string; nm_offset: number }
}

type WbCardStatsRunMode = 'daily' | 'last30' | 'custom'

function toDateInputValue(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function shiftedDateInputValue(days: number): string {
  const value = new Date()
  value.setDate(value.getDate() + days)
  return toDateInputValue(value)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('ru-RU')
  } catch {
    return value
  }
}

function marketplaceLabel(marketplace: ProjectMarketplace): string {
  if (marketplace.marketplace_code === 'wildberries') return 'Wildberries'
  if (marketplace.marketplace_code === 'ozon') return 'Ozon'
  if (marketplace.marketplace_code === 'ym') return 'YM'
  return marketplace.marketplace_name || marketplace.marketplace_code
}

function statusLabel(status: string | null, isRunning: boolean): string {
  if (isRunning) return 'выполняется'
  if (status === 'success') return 'успешно'
  if (status === 'failed') return 'ошибка'
  if (status === 'queued') return 'в очереди'
  if (status === 'running') return 'выполняется'
  return 'нет запусков'
}

function statusTone(status: string | null, isRunning: boolean): string {
  if (isRunning || status === 'running' || status === 'queued') return styles.infoBadge
  if (status === 'success') return styles.successBadge
  if (status === 'failed') return styles.dangerBadge
  return styles.neutralBadge
}

function normalizeStatuses(items: WBIngestStatus[]): WBIngestStatus[] {
  return [...items].sort((a, b) => String(a.job_code).localeCompare(String(b.job_code)))
}

function statusesHash(items: WBIngestStatus[]): string {
  return JSON.stringify(
    items.map((status) => ({
      job_code: status.job_code,
      title: status.title,
      has_schedule: status.has_schedule,
      schedule_summary: status.schedule_summary,
      last_run_at: status.last_run_at,
      last_status: status.last_status,
      is_running: status.is_running,
      progress_current: status.progress_current,
      progress_total: status.progress_total,
      progress_pct: status.progress_pct,
      progress_text: status.progress_text,
      progress_detail: status.progress_detail,
      active_run_id: status.active_run_id,
      active_mode: status.active_mode,
    })),
  )
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
  const [wbIngestStatuses, setWbIngestStatuses] = useState<WBIngestStatus[]>([])
  const [wbIngestLoading, setWbIngestLoading] = useState(false)
  const [runningJobs, setRunningJobs] = useState<Set<string>>(new Set())
  const [isPolling, setIsPolling] = useState(false)
  const [frontendPricesBrandCount, setFrontendPricesBrandCount] = useState(0)
  const [wbCardStatsRunMode, setWbCardStatsRunMode] = useState<WbCardStatsRunMode>('daily')
  const [wbCardStatsDateFrom, setWbCardStatsDateFrom] = useState(() => shiftedDateInputValue(-29))
  const [wbCardStatsDateTo, setWbCardStatsDateTo] = useState(() => toDateInputValue(new Date()))

  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastStatusesHashRef = useRef('')

  const projectMeta = useMemo(
    () => [
      { label: 'ID', value: project?.id != null ? String(project.id) : '—' },
      { label: 'Обновлён', value: formatDateTime(project?.updated_at) },
      { label: 'Участники', value: String(project?.members?.length ?? 0) },
    ],
    [project],
  )

  const showToast = (message: string, timeout = 4000) => {
    setToast(message)
    window.setTimeout(() => setToast(null), timeout)
  }

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    setIsPolling(false)
  }

  const loadWBIngestStatuses = async (opts?: { silent?: boolean }) => {
    if (!wbEnabled) {
      setWbIngestStatuses([])
      stopPolling()
      return
    }

    try {
      if (!opts?.silent) setWbIngestLoading(true)
      const statuses = normalizeStatuses(await getWBIngestStatus(projectId))
      const nextHash = statusesHash(statuses)

      if (nextHash !== lastStatusesHashRef.current) {
        lastStatusesHashRef.current = nextHash
        setWbIngestStatuses(statuses)
      }

      const running = new Set(statuses.filter((status) => status.is_running).map((status) => status.job_code))
      setRunningJobs((prev) => {
        if (prev.size === running.size && [...prev].every((jobCode) => running.has(jobCode))) return prev
        return running
      })

      if (running.size === 0) stopPolling()
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
    }, 10000)
  }

  useEffect(() => {
    let alive = true

    async function load() {
      try {
        setLoading(true)
        setError(null)

        const [projectResult, marketplacesResult] = await Promise.all([
          apiGet<ProjectDetail>(`/api/v1/projects/${projectId}`),
          apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`),
        ])

        if (!alive) return

        const marketplaces = marketplacesResult.data || []
        const enabledMarketplaces = marketplaces.filter((marketplace) => marketplace.is_enabled)
        const wbMarketplace = marketplaces.find((marketplace) => marketplace.marketplace_code === 'wildberries')
        const frontendPriceBrands = wbMarketplace?.settings_json?.frontend_prices?.brands
        const brandCount = Array.isArray(frontendPriceBrands)
          ? frontendPriceBrands.filter((brand) => brand.enabled !== false).length
          : wbMarketplace?.settings_json?.brand_id != null ? 1 : 0

        setProject(projectResult.data)
        setConnectedMarketplaces(enabledMarketplaces)
        setWbEnabled(!!wbMarketplace?.is_enabled)
        setFrontendPricesBrandCount(brandCount)
      } catch (error) {
        if (!alive) return
        setError((error as { detail?: string; message?: string })?.detail || 'Не удалось загрузить настройки проекта')
      } finally {
        if (alive) setLoading(false)
      }
    }

    load()

    return () => {
      alive = false
      stopPolling()
    }
  }, [projectId])

  useEffect(() => {
    if (wbEnabled) {
      loadWBIngestStatuses()
    } else {
      setWbIngestStatuses([])
      stopPolling()
    }
  }, [wbEnabled])

  const runIngestWithParams = async (jobCode: string, params?: RunParams) => {
    if (!wbEnabled) {
      showToast('WB не подключён. Включите Wildberries в разделе маркетплейсов.', 5000)
      return
    }

    try {
      setRunningJobs((prev) => new Set(prev).add(jobCode))
      setWbIngestStatuses((prev) =>
        prev.map((status) =>
          status.job_code === jobCode ? { ...status, is_running: true, last_status: 'queued' } : status,
        ),
      )

      await runWBIngest(projectId, jobCode, params)
      showToast(`Загрузка ${jobCode} запущена`)
      startPolling()
      window.setTimeout(() => loadWBIngestStatuses(), 1000)
    } catch (error) {
      setRunningJobs((prev) => {
        const next = new Set(prev)
        next.delete(jobCode)
        return next
      })
      setWbIngestStatuses((prev) =>
        prev.map((status) => (status.job_code === jobCode ? { ...status, is_running: false } : status)),
      )
      showToast(`Ошибка (${jobCode}): ${(error as { detail?: string; message?: string })?.detail || 'не удалось запустить'}`, 6000)
    }
  }

  const handleRunIngest = async (jobCode: string) => {
    if (jobCode === 'wb_finances') {
      showToast('Ручная загрузка финансовых отчётов перенесена на страницу «Финансовые отчёты».')
      return
    }

    await runIngestWithParams(
      jobCode,
      jobCode === 'wb_communications' ? { mode: 'reviews_full_sync' } : undefined,
    )
  }

  const handleStopIngest = async (status: WBIngestStatus) => {
    if (!status.active_run_id) return

    try {
      await markIngestRunTimeout(projectId, status.active_run_id, {
        reason_code: 'manual_stop',
        reason_text:
          status.job_code === 'wb_communications' && status.active_mode === 'reviews_full_sync'
            ? 'Остановлено пользователем: полный сбор отзывов'
            : `Остановлено пользователем: ${status.job_code}`,
      })

      showToast(`Загрузка ${status.job_code} остановлена`)
      window.setTimeout(() => loadWBIngestStatuses(), 500)
    } catch (error) {
      showToast(`Ошибка остановки: ${(error as { detail?: string; message?: string })?.detail || 'не удалось остановить'}`, 6000)
    }
  }

  const getWbCardStatsPlan = (): { params: RunParams; summary: string; invalid?: string } => {
    if (wbCardStatsRunMode === 'daily') {
      const day = shiftedDateInputValue(-1)
      return {
        params: {
          mode: 'daily',
          date_from: day,
          date_to: day,
        },
        summary: `Обычная дневная загрузка за ${day}`,
      }
    }

    const dateFrom = wbCardStatsRunMode === 'last30' ? shiftedDateInputValue(-29) : wbCardStatsDateFrom
    const dateTo = wbCardStatsRunMode === 'last30' ? toDateInputValue(new Date()) : wbCardStatsDateTo
    if (!dateFrom || !dateTo) {
      return {
        params: {},
        summary: 'backfill · даты не выбраны',
        invalid: 'Выберите date_from и date_to',
      }
    }
    if (dateFrom > dateTo) {
      return {
        params: {},
        summary: `Догрузка периода ${dateFrom}..${dateTo}`,
        invalid: 'date_from позже date_to',
      }
    }
    return {
      params: {
        mode: 'backfill',
        date_from: dateFrom,
        date_to: dateTo,
        max_seconds: 1500,
        max_batches: 200,
      },
      summary: `Догрузка периода ${dateFrom}..${dateTo}`,
    }
  }

  const runSelectedCardStats = async () => {
    const plan = getWbCardStatsPlan()
    if (plan.invalid) {
      showToast(plan.invalid, 5000)
      return
    }
    await runIngestWithParams('wb_card_stats_daily', plan.params)
  }

  return (
    <div className={styles.settingsPage}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Настройки</div>
          <h1>{project ? `Настройки проекта ${project.name}` : 'Настройки проекта'}</h1>
        </div>
        <Link className={styles.backLink} href="/app/projects">
          ← Проекты
        </Link>
      </header>

      {toast ? <div className={styles.toast}>{toast}</div> : null}

      {loading ? (
        <section className={styles.panel}>
          <div className={styles.skeletonTitle} />
          <div className={styles.skeletonGrid}>
            <div />
            <div />
            <div />
          </div>
        </section>
      ) : null}

      {!loading && error ? (
        <section className={styles.notice} role="alert">
          <strong>Не удалось загрузить настройки.</strong>
          <span>{error}</span>
        </section>
      ) : null}

      {!loading && !error && !project ? (
        <section className={styles.notice}>
          <strong>Проект не найден.</strong>
        </section>
      ) : null}

      {!loading && !error && project ? (
        <>
          <section className={styles.projectPanel}>
            <div>
              <h2>{project.name}</h2>
              {project.description ? <p>{project.description}</p> : null}
              <div className={styles.marketplaces}>
                {connectedMarketplaces.length > 0 ? (
                  connectedMarketplaces.map((marketplace) => (
                    <span key={`${marketplace.marketplace_code}-${marketplace.id}`} className={styles.marketplaceChip}>
                      {marketplaceLabel(marketplace)}
                    </span>
                  ))
                ) : (
                  <span className={styles.mutedText}>Маркетплейсы не подключены</span>
                )}
              </div>
            </div>
            <dl className={styles.metaGrid}>
              {projectMeta.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div>
                <div className={styles.eyebrow}>Wildberries</div>
                <h2>Загрузка данных WB</h2>
                <p>Состояние и ручной запуск существующих загрузок Wildberries.</p>
              </div>
              <div className={styles.headerActions}>
                {isPolling ? <span className={`${styles.badge} ${styles.infoBadge}`}>обновление</span> : null}
                <Link className={styles.secondaryLink} href={`/app/project/${projectId}/wildberries/finances/reports`}>
                  Финансовые отчёты
                </Link>
                <Link className={styles.secondaryLink} href={`/app/project/${projectId}/ingestion`}>
                  Расписание
                </Link>
              </div>
            </div>

            {!wbEnabled ? (
              <div className={styles.noticeInline}>
                <strong>WB не подключён.</strong>
                <span>Включите Wildberries в разделе маркетплейсов для управления загрузками.</span>
                <Link href={`/app/project/${projectId}/marketplaces`}>Маркетплейсы</Link>
              </div>
            ) : null}

            {wbIngestLoading ? (
              <div className={styles.tableEmpty}>Загружаем статусы...</div>
            ) : wbIngestStatuses.length === 0 ? (
              <div className={styles.tableEmpty}>Нет доступных загрузок</div>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.ingestTable}>
                  <thead>
                    <tr>
                      <th>Название</th>
                      <th>Расписание</th>
                      <th>Последний запуск</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wbIngestStatuses.map((status) => {
                      const isRunning = status.is_running || runningJobs.has(status.job_code)
                      const cardStatsPlan = status.job_code === 'wb_card_stats_daily' ? getWbCardStatsPlan() : null

                      return (
                        <tr key={status.job_code}>
                          <td>
                            <div className={styles.jobCell}>
                              <span className={`${styles.badge} ${statusTone(status.last_status, isRunning)}`}>
                                {statusLabel(status.last_status, isRunning)}
                              </span>
                              <div>
                                <div className={styles.jobTitle}>
                                  <span>{status.title}</span>
                                  {status.job_code === 'frontend_prices' ? (
                                    <span className={`${styles.badge} ${styles.neutralBadge}`}>
                                      {frontendPricesBrandCount > 0 ? `Брендов: ${frontendPricesBrandCount}` : 'Бренды не настроены'}
                                    </span>
                                  ) : null}
                                </div>
                                {status.job_code === 'frontend_prices' ? (
                                  <div className={styles.jobHint}>
                                    Перед витринными ценами автоматически обновляются цены WB.
                                  </div>
                                ) : null}
                                {status.progress_text ? (
                                  <div className={styles.progressBlock}>
                                    <div>
                                      {status.progress_text}
                                      {typeof status.progress_pct === 'number' ? ` (${status.progress_pct.toFixed(1)}%)` : ''}
                                    </div>
                                    {status.progress_detail ? <span>{status.progress_detail}</span> : null}
                                    {typeof status.progress_pct === 'number' ? (
                                      <div className={styles.progressBar}>
                                        <i style={{ width: `${Math.max(0, Math.min(100, status.progress_pct))}%` }} />
                                      </div>
                                    ) : null}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </td>
                          <td>{status.has_schedule ? status.schedule_summary || 'По расписанию' : 'Не настроено'}</td>
                          <td>{formatDateTime(status.last_run_at)}</td>
                          <td>
                            <div className={styles.rowActions}>
                              {status.job_code === 'wb_finances' ? (
                                <Link className={styles.inlineLink} href={`/app/project/${projectId}/wildberries/finances/reports`}>
                                  Финансовые отчёты
                                </Link>
                              ) : status.job_code === 'wb_communications' ? (
                                <>
                                  <button
                                    type="button"
                                    className={styles.smallPrimary}
                                    onClick={() => runIngestWithParams(status.job_code, { mode: 'reviews_full_sync' })}
                                    disabled={!wbEnabled || isRunning}
                                  >
                                    Полный сбор
                                  </button>
                                  <button
                                    type="button"
                                    className={styles.smallSecondary}
                                    onClick={() => runIngestWithParams(status.job_code, { mode: 'reviews_incremental_all_nm_ids' })}
                                    disabled={!wbEnabled || isRunning}
                                  >
                                    Догрузить новое
                                  </button>
                                </>
                              ) : status.job_code === 'wb_card_stats_daily' ? (
                                <div className={styles.cardStatsControls}>
                                  <label className={styles.inlineField}>
                                    <span>Что загрузить</span>
                                    <select
                                      value={wbCardStatsRunMode}
                                      onChange={(event) => setWbCardStatsRunMode(event.target.value as WbCardStatsRunMode)}
                                    >
                                      <option value="daily">Вчера</option>
                                      <option value="last30">Последние 30 дней</option>
                                      <option value="custom">Свой период</option>
                                    </select>
                                  </label>

                                  {wbCardStatsRunMode === 'custom' ? (
                                    <div className={styles.dateRangeControls}>
                                      <input
                                        type="date"
                                        value={wbCardStatsDateFrom}
                                        onChange={(event) => setWbCardStatsDateFrom(event.target.value)}
                                        aria-label="date_from"
                                      />
                                      <span>...</span>
                                      <input
                                        type="date"
                                        value={wbCardStatsDateTo}
                                        onChange={(event) => setWbCardStatsDateTo(event.target.value)}
                                        aria-label="date_to"
                                      />
                                    </div>
                                  ) : null}

                                  <div className={styles.runPlan} title={JSON.stringify(cardStatsPlan?.params ?? {})}>
                                    {cardStatsPlan?.summary}
                                  </div>

                                  <button
                                    type="button"
                                    className={styles.smallPrimary}
                                    onClick={runSelectedCardStats}
                                    disabled={!wbEnabled || isRunning || Boolean(cardStatsPlan?.invalid)}
                                  >
                                    {isRunning ? 'Выполняется...' : 'Запустить'}
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  className={styles.smallPrimary}
                                  onClick={() => handleRunIngest(status.job_code)}
                                  disabled={!wbEnabled || isRunning}
                                >
                                  {isRunning ? 'Выполняется...' : 'Загрузить сейчас'}
                                </button>
                              )}

                              {isRunning && status.active_run_id != null ? (
                                <button type="button" className={styles.smallDanger} onClick={() => handleStopIngest(status)}>
                                  Остановить
                                </button>
                              ) : null}

                              {(status.job_code === 'wb_search_report_tabular' || status.job_code === 'wb_stock_total_daily') ? (
                                <Link className={styles.inlineLink} href={`/app/project/${projectId}/wildberries/search-report`}>
                                  Открыть
                                </Link>
                              ) : null}

                              {status.job_code !== 'wb_finances' && (status.last_run_at || status.job_code === 'wb_card_stats_daily') ? (
                                <Link className={styles.inlineLink} href={`/app/project/${projectId}/ingestion?job_code=${status.job_code}`}>
                                  История
                                </Link>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

        </>
      ) : null}
    </div>
  )
}
