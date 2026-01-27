'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPost, apiPut, apiDelete } from '../../../../../lib/apiClient'
import type { ApiError } from '../../../../../lib/apiClient'
import s from './ingestion.module.css'

type Schedule = {
  id: number
  project_id: number
  marketplace_code: string
  job_code: string
  cron_expr: string
  timezone: string
  is_enabled: boolean
  next_run_at: string | null
  created_at: string
  updated_at: string
}

type RunStatus = 'queued' | 'running' | 'success' | 'failed' | 'timeout' | 'skipped' | 'canceled'

type IngestRun = {
  id: number
  schedule_id: number | null
  project_id: number
  marketplace_code: string
  job_code: string
  triggered_by: 'schedule' | 'manual' | 'api'
  status: RunStatus
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error_message: string | null
  error_trace: string | null
  stats_json: any | null
  heartbeat_at?: string | null
  celery_task_id?: string | null
  meta_json?: any | null
  created_at: string
  updated_at: string
}

type RunListResponse = {
  items: IngestRun[]
}

type IngestJob = {
  job_code: string
  title: string
  source_code: 'wildberries' | 'internal' | string
  supports_schedule: boolean
  supports_manual: boolean
}

type TabKey = 'schedules' | 'runs'

export default function ProjectIngestionPage() {
  const params = useParams()
  const projectId = params.projectId as string

  const [activeTab, setActiveTab] = useState<TabKey>('schedules')

  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [loadingSchedules, setLoadingSchedules] = useState(false)

  const [runs, setRuns] = useState<IngestRun[]>([])
  const [loadingRuns, setLoadingRuns] = useState(false)

  const [jobs, setJobs] = useState<IngestJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(false)

  const [filtersMarketplace, setFiltersMarketplace] = useState<string>('wildberries')
  const [filtersJob, setFiltersJob] = useState<string>('')
  const [filtersStatus, setFiltersStatus] = useState<string>('')
  const [filtersPeriod, setFiltersPeriod] = useState<'7d' | '30d'>('7d')

  const [runDetails, setRunDetails] = useState<IngestRun | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [markTimeoutRunId, setMarkTimeoutRunId] = useState<number | null>(null)
  const [markingTimeout, setMarkingTimeout] = useState(false)

  // Create schedule form
  const [formJob, setFormJob] = useState<string>('')
  const [formCron, setFormCron] = useState<string>('0 3 * * *')
  const [formTimezone, setFormTimezone] = useState<string>('Europe/Istanbul')
  const [formEnabled, setFormEnabled] = useState<boolean>(true)
  const [creatingSchedule, setCreatingSchedule] = useState(false)

  // Simple schedule mode state
  type SimpleMode = 'daily' | 'every_hours' | 'every_minutes' | 'weekly'
  const [useAdvancedCron, setUseAdvancedCron] = useState(false)
  const [simpleMode, setSimpleMode] = useState<SimpleMode>('daily')
  const [simpleTime, setSimpleTime] = useState<string>('03:00')
  const [simpleEveryHours, setSimpleEveryHours] = useState<number>(3)
  const [simpleEveryMinutes, setSimpleEveryMinutes] = useState<number>(15)
  const [simpleWeekdays, setSimpleWeekdays] = useState<string[]>(['1','2','3','4','5']) // Mon-Fri (cron: 1-5)

  const [savingScheduleId, setSavingScheduleId] = useState<number | null>(null)
  const [runningScheduleId, setRunningScheduleId] = useState<number | null>(null)

  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [cronError, setCronError] = useState<string | null>(null)
  const [timezoneError, setTimezoneError] = useState<string | null>(null)
  const [showCronExamples, setShowCronExamples] = useState(false)
  const [simpleIntervalError, setSimpleIntervalError] = useState<string | null>(null)
  const [activePreset, setActivePreset] = useState<'daily_3' | 'hourly' | 'every_15' | 'mon_fri_9' | null>(null)

  useEffect(() => {
    if (activeTab === 'schedules') {
      loadSchedules()
    } else {
      loadRuns()
    }
  }, [activeTab, projectId])

  useEffect(() => {
    loadJobs()
  }, [])

  const handleApiError = (e: any, fallback: string) => {
    const err = e as ApiError
    const msg = err?.detail || fallback
    setErrorMessage(msg)
    setTimeout(() => setErrorMessage(null), 5000)
    // eslint-disable-next-line no-console
    console.error('Ingestion API error', err)
  }

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg)
    setTimeout(() => setSuccessMessage(null), 4000)
  }

  const loadSchedules = async () => {
    setLoadingSchedules(true)
    try {
      const { data } = await apiGet<Schedule[]>(`/api/v1/projects/${projectId}/ingest/schedules`)
      setSchedules(data)
    } catch (e: any) {
      handleApiError(e, 'Не удалось загрузить расписания')
    } finally {
      setLoadingSchedules(false)
    }
  }

  const computeFromTo = () => {
    const now = new Date()
    const to = now.toISOString()
    const from = new Date(now.getTime() - (filtersPeriod === '7d' ? 7 : 30) * 24 * 60 * 60 * 1000).toISOString()
    return { from, to }
  }

  const loadRuns = async () => {
    setLoadingRuns(true)
    try {
      const params = new URLSearchParams()
      if (filtersMarketplace) params.append('marketplace_code', filtersMarketplace)
      if (filtersJob) params.append('job_code', filtersJob)
      if (filtersStatus) params.append('status', filtersStatus)
      const { from, to } = computeFromTo()
      params.append('from', from)
      params.append('to', to)
      params.append('limit', '200')

      const { data } = await apiGet<RunListResponse>(
        `/api/v1/projects/${projectId}/ingest/runs?${params.toString()}`
      )
      setRuns(data.items || [])
    } catch (e: any) {
      handleApiError(e, 'Не удалось загрузить историю запусков')
    } finally {
      setLoadingRuns(false)
    }
  }

  const loadJobs = async () => {
    setLoadingJobs(true)
    try {
      const { data } = await apiGet<IngestJob[]>(`/api/v1/ingest/jobs`)
      setJobs(data)
      if (!formJob && data.length) {
        const firstSchedulable = data.find((j) => j.supports_schedule) || data[0]
        setFormJob(firstSchedulable.job_code)
      }
    } catch (e: any) {
      handleApiError(e, 'Не удалось загрузить список задач ingestion')
    } finally {
      setLoadingJobs(false)
    }
  }

  const validateCronExpr = (cron: string): string | null => {
    const trimmed = cron.trim()
    if (!trimmed) return 'Cron выражение не может быть пустым'
    const parts = trimmed.split(/\s+/)
    if (parts.length !== 5 || parts.some((p) => !p)) {
      return 'Cron must have 5 parts'
    }
    return null
  }

  const handleCreateSchedule = async () => {
    const cronToSend = effectiveCron.trim()

    if (useAdvancedCron) {
      const err = validateCronExpr(formCron)
      if (err) {
        setCronError(err)
        return
      }
    }

    if (!formTimezone.trim()) {
      const tzErr = 'Timezone не может быть пустым'
      setTimezoneError(tzErr)
      setErrorMessage(tzErr)
      setTimeout(() => setErrorMessage(null), 4000)
      return
    }

    const job = jobs.find((j) => j.job_code === formJob)
    const marketplace_code = job?.source_code || 'wildberries'

    setCreatingSchedule(true)
    try {
      await apiPost<Schedule>(`/api/v1/projects/${projectId}/ingest/schedules`, {
        marketplace_code,
        job_code: formJob,
        cron_expr: cronToSend,
        timezone: formTimezone.trim() || 'Europe/Istanbul',
        is_enabled: formEnabled,
      })
      await loadSchedules()
    } catch (e: any) {
      handleApiError(e, 'Не удалось создать расписание')
    } finally {
      setCreatingSchedule(false)
    }
  }

  const handleToggleSchedule = async (schedule: Schedule) => {
    setSavingScheduleId(schedule.id)
    try {
      await apiPut<Schedule>(`/api/v1/ingest/schedules/${schedule.id}`, {
        is_enabled: !schedule.is_enabled,
      })
      await loadSchedules()
    } catch (e: any) {
      handleApiError(e, 'Не удалось изменить статус расписания')
    } finally {
      setSavingScheduleId(null)
    }
  }

  const handleDeleteSchedule = async (schedule: Schedule) => {
    // eslint-disable-next-line no-alert
    const confirmed = window.confirm('Удалить расписание? История запусков сохранится.')
    if (!confirmed) return
    try {
      await apiDelete<{ ok: boolean }>(`/api/v1/ingest/schedules/${schedule.id}`)
      await loadSchedules()
    } catch (e: any) {
      handleApiError(e, 'Не удалось удалить расписание')
    }
  }

  const handleEditSchedule = async (schedule: Schedule, values: Partial<Pick<Schedule, 'cron_expr' | 'timezone'>>) => {
    setSavingScheduleId(schedule.id)
    try {
      await apiPut<Schedule>(`/api/v1/ingest/schedules/${schedule.id}`, {
        cron_expr: values.cron_expr ?? schedule.cron_expr,
        timezone: values.timezone ?? schedule.timezone,
      })
      await loadSchedules()
    } catch (e: any) {
      handleApiError(e, 'Не удалось обновить расписание')
    } finally {
      setSavingScheduleId(null)
    }
  }

  const handleRunNow = async (schedule: Schedule) => {
    setRunningScheduleId(schedule.id)
    try {
      await apiPost<IngestRun>(`/api/v1/ingest/schedules/${schedule.id}/run`, {})
      await loadRuns()
    } catch (e: any) {
      handleApiError(e, 'Не удалось запустить задачу')
    } finally {
      setRunningScheduleId(null)
      setActiveTab('runs')
    }
  }

  const loadRunDetails = async (runId: number) => {
    try {
      const { data } = await apiGet<IngestRun>(`/api/v1/ingest/runs/${runId}`)
      setRunDetails(data)
    } catch (e: any) {
      handleApiError(e, 'Не удалось загрузить детали запуска')
    }
  }

  const formatDateTime = (value: string | null) => {
    if (!value) return '-'
    return new Date(value).toLocaleString('ru-RU')
  }

  const formatRelativeMinutes = (value: string | null | undefined) => {
    if (!value) return '-'
    const ts = new Date(value).getTime()
    if (!Number.isFinite(ts)) return '-'
    const diffMs = Date.now() - ts
    const mins = Math.max(0, Math.floor(diffMs / 60000))
    if (mins < 1) return 'только что'
    if (mins === 1) return '1 мин назад'
    return `${mins} мин назад`
  }

  const getLastActivity = (r: IngestRun) => r.heartbeat_at ?? r.updated_at

  const formatDuration = (ms: number | null) => {
    if (!ms || ms <= 0) return '-'
    const sec = Math.round(ms / 1000)
    if (sec < 60) return `${sec} сек`
    const min = Math.floor(sec / 60)
    const rest = sec % 60
    return `${min} мин ${rest} сек`
  }

  const renderStatusBadge = (status: RunStatus) => {
    let bg = '#e5e7eb'
    let color = '#111827'
    if (status === 'queued') {
      bg = '#e0f2fe'
      color = '#0369a1'
    } else if (status === 'running') {
      bg = '#fef9c3'
      color = '#854d0e'
    } else if (status === 'success') {
      bg = '#dcfce7'
      color = '#166534'
    } else if (status === 'failed') {
      bg = '#fee2e2'
      color = '#b91c1c'
    } else if (status === 'timeout') {
      bg = '#ffedd5'
      color = '#9a3412'
    } else if (status === 'skipped') {
      bg = '#f3f4f6'
      color = '#4b5563'
    }
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '2px 8px',
          borderRadius: '999px',
          backgroundColor: bg,
          color,
          fontSize: 12,
          fontWeight: 500,
        }}
      >
        {status}
      </span>
    )
  }

  const handleMarkTimeout = async (runId: number) => {
    setMarkingTimeout(true)
    try {
      await apiPost(`/api/v1/projects/${projectId}/ingest/runs/${runId}/mark-timeout`, {
        reason_code: 'manual',
        reason_text: 'Marked timeout manually',
      })
      showSuccess('Run отмечен как TIMEOUT')
      await loadRuns()
      if (runDetails?.id === runId) {
        await loadRunDetails(runId)
      }
    } catch (e: any) {
      handleApiError(e, 'Не удалось отметить run как TIMEOUT')
    } finally {
      setMarkingTimeout(false)
      setMarkTimeoutRunId(null)
    }
  }

  const renderStatsSummary = (stats: any) => {
    if (!stats || typeof stats !== 'object') return '-'

    const asNum = (v: any): number | null => {
      const n = typeof v === 'number' ? v : parseInt(String(v ?? ''), 10)
      return Number.isFinite(n) ? n : null
    }

    const fmtPage = (page: any, total: any) => {
      const p = page != null ? String(page) : '?'
      const t = total != null ? String(total) : '?'
      return `${p}/${t}`
    }

    const lastReq = stats.last_request && typeof stats.last_request === 'object' ? stats.last_request : null
    const lastReqHint =
      lastReq?.status_code != null
        ? `http:${lastReq.status_code}`
        : lastReq?.error
          ? `err:${String(lastReq.error)}`
          : null

    // Universal: explicit reason/error
    if (stats.reason) return `reason:${String(stats.reason)}`.slice(0, 80)
    if (stats.error && stats.ok === false) return `error:${String(stats.error)}`.slice(0, 80)

    // Frontend prices / generic pagination retry
    if (stats.phase === 'retry_wait') {
      const sleepS = asNum(stats.sleep_s)
      const parts = [
        `retry p:${fmtPage(stats.page, stats.total_pages)}`,
        sleepS != null ? `sleep:${sleepS}s` : null,
        lastReqHint,
      ].filter(Boolean)
      return parts.join(' ').slice(0, 80)
    }

    // Live progress: stocks (FBS) chunks
    if (
      stats.phase === 'stocks_fetch' ||
      stats.warehouse_id != null ||
      stats.chunk_index != null ||
      stats.chunks_total != null
    ) {
      const wh = stats.warehouse_id != null ? `wh:${stats.warehouse_id}` : null
      const chunkIdx = stats.chunk_index != null ? `${stats.chunk_index}` : '?'
      const chunksTotal = stats.chunks_total != null ? `${stats.chunks_total}` : '?'
      const api = stats.api_records != null ? `api:${stats.api_records}` : null
      const ins = stats.inserted != null ? `ins:${stats.inserted}` : null
      const fail = stats.failed_chunks != null ? `fail:${stats.failed_chunks}` : null
      const empty = stats.empty_chunks != null ? `empty:${stats.empty_chunks}` : null
      const parts = [wh, `chunk:${chunkIdx}/${chunksTotal}`, api, ins, fail, empty].filter(Boolean)
      if (parts.length) return parts.join(' ').slice(0, 80)
    }

    // Supplier stocks progress
    if (stats.phase === 'supplier_stocks') {
      const parts = [
        stats.page != null ? `p:${stats.page}` : null,
        stats.received != null ? `recv:${stats.received}` : null,
        stats.inserted != null ? `ins:${stats.inserted}` : null,
      ].filter(Boolean)
      if (parts.length) return parts.join(' ').slice(0, 80)
    }

    // Generic "paged" progress
    if (stats.phase && (stats.page != null || stats.total_pages != null)) {
      const saved = stats.saved != null ? `saved:${stats.saved}` : null
      const distinct = stats.distinct_nm_id != null ? `uniq:${stats.distinct_nm_id}` : null
      const parts = [`p:${fmtPage(stats.page, stats.total_pages)}`, saved, distinct, lastReqHint].filter(Boolean)
      return parts.join(' ').slice(0, 80)
    }

    if ('inserted' in stats || 'updated' in stats) {
      const parts: string[] = []
      if (stats.inserted != null) parts.push(`ins:${stats.inserted}`)
      if (stats.updated != null) parts.push(`upd:${stats.updated}`)
      if (stats.deleted != null) parts.push(`del:${stats.deleted}`)
      if (parts.length) return parts.join(' ')
    }
    if (stats.ok === true) return 'ok'

    // Last resort: short key=value pairs (instead of full JSON)
    const skipKeys = new Set(['raw', 'error_trace', 'trace', 'details', 'failed_pages', 'last_request'])
    const kv: string[] = []
    for (const k of Object.keys(stats)) {
      if (skipKeys.has(k)) continue
      const v = stats[k]
      if (v == null) continue
      if (typeof v === 'object') continue
      kv.push(`${k}:${String(v)}`)
      if (kv.length >= 4) break
    }
    if (kv.length) return kv.join(' ').slice(0, 80)
    return JSON.stringify(stats).slice(0, 80)
  }

  const cronToHuman = (cronExpr: string): string => {
    const parts = cronExpr.trim().split(/\s+/)
    if (parts.length < 5) return 'По cron'
    const [min, hour, , , dow] = parts

    const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`)
    const parseIntSafe = (val: string) => {
      const n = parseInt(val, 10)
      return Number.isNaN(n) ? null : n
    }

    // Ежедневно в HH:MM
    if (min !== '*' && hour !== '*' && parts[2] === '*' && parts[3] === '*' && (dow === '*' || dow === '?')) {
      const hh = parseIntSafe(hour)
      const mm = parseIntSafe(min)
      if (hh !== null && mm !== null) {
        return `Ежедневно в ${pad(hh)}:${pad(mm)}`
      }
    }

    // Каждые N минут: "*/N * * * *"
    if (min.startsWith('*/') && hour === '*' && parts[2] === '*' && parts[3] === '*' && (dow === '*' || dow === '?')) {
      const n = parseIntSafe(min.slice(2))
      if (n && n > 0) {
        return `Каждые ${n} минут`
      }
    }

    // Каждые N часов: "0 */N * * *"
    if (min === '0' && hour.startsWith('*/') && parts[2] === '*' && parts[3] === '*' && (dow === '*' || dow === '?')) {
      const n = parseIntSafe(hour.slice(2))
      if (n && n > 0) {
        return `Каждые ${n} часов`
      }
    }

    // Пн–Пт в HH:00: "0 H * * 1-5" или "0 H * * 1,2,3,4,5"
    if (min === '0' && hour !== '*' && parts[2] === '*' && parts[3] === '*') {
      const hh = parseIntSafe(hour)
      if (hh !== null) {
        if (dow === '1-5') {
          return `Пн–Пт в ${pad(hh)}:00`
        }
        const workdays = ['1', '2', '3', '4', '5']
        const dowParts = dow.split(',')
        if (dowParts.length === 5 && dowParts.every((d) => workdays.includes(d))) {
          return `Пн–Пт в ${pad(hh)}:00`
        }
      }
    }

    return 'По cron'
  }

  // --- Simple schedule helpers ---

  const toggleWeekday = (val: string) => {
    setSimpleWeekdays((prev) =>
      prev.includes(val) ? prev.filter((d) => d !== val) : [...prev, val].sort()
    )
  }

  const clamp = (value: number, min: number, max: number) => {
    if (Number.isNaN(value)) return min
    return Math.max(min, Math.min(max, value))
  }

  const computeSimpleCron = (): string => {
    const [hhRaw, mmRaw] = simpleTime.split(':')
    const hours = clamp(parseInt(hhRaw || '0', 10), 0, 23)
    const minutes = clamp(parseInt(mmRaw || '0', 10), 0, 59)

    if (simpleMode === 'daily') {
      // "0 3 * * *"
      return `${minutes} ${hours} * * *`
    }

    if (simpleMode === 'every_hours') {
      const n = clamp(simpleEveryHours, 1, 24)
      // "0 */N * * *"
      return `0 */${n} * * *`
    }

    if (simpleMode === 'every_minutes') {
      const n = clamp(simpleEveryMinutes, 1, 60)
      // "*/N * * * *"
      return `*/${n} * * * *`
    }

    // weekly
    const days = simpleWeekdays.length > 0 ? simpleWeekdays.join(',') : '1-5'
    // "0 9 * * 1,2,3"
    return `${minutes} ${hours} * * ${days}`
  }

  const effectiveCron = useMemo(() => {
    if (useAdvancedCron) {
      return formCron
    }
    return computeSimpleCron()
  }, [useAdvancedCron, formCron, simpleMode, simpleTime, simpleEveryHours, simpleEveryMinutes, simpleWeekdays])

  const simpleSummary = useMemo(() => {
    const tz = formTimezone || 'Europe/Istanbul'
    if (simpleMode === 'daily') {
      return `ежедневно в ${simpleTime || '00:00'} (${tz})`
    }
    if (simpleMode === 'every_hours') {
      return `каждые ${clamp(simpleEveryHours, 1, 24)} ч (${tz})`
    }
    if (simpleMode === 'every_minutes') {
      return `каждые ${clamp(simpleEveryMinutes, 1, 60)} мин (${tz})`
    }
    const daysMap: Record<string, string> = {
      '1': 'Пн',
      '2': 'Вт',
      '3': 'Ср',
      '4': 'Чт',
      '5': 'Пт',
      '6': 'Сб',
      '7': 'Вс',
      '0': 'Вс',
    }
    const labels = (simpleWeekdays.length ? simpleWeekdays : ['1', '2', '3', '4', '5'])
      .map((d) => daysMap[d] || d)
      .join(', ')
    return `еженедельно (${labels}) в ${simpleTime || '00:00'} (${tz})`
  }, [simpleMode, simpleTime, simpleEveryHours, simpleEveryMinutes, simpleWeekdays, formTimezone])

  const selectedJob = useMemo(
    () => jobs.find((j) => j.job_code === formJob) || null,
    [jobs, formJob]
  )

  const jobSources = useMemo(
    () => Array.from(new Set(jobs.map((j) => j.source_code))),
    [jobs]
  )

  const isFormValid = useMemo(() => {
    if (!formJob || !selectedJob || !selectedJob.supports_schedule) return false
    if (!formTimezone.trim()) return false
    if (useAdvancedCron) {
      return !validateCronExpr(formCron)
    }
    if (simpleIntervalError) return false
    return !!effectiveCron.trim()
  }, [formJob, selectedJob, formTimezone, useAdvancedCron, formCron, effectiveCron, simpleIntervalError])

  useEffect(() => {
    if (useAdvancedCron) {
      setCronError(validateCronExpr(formCron))
    } else {
      setCronError(null)
    }
  }, [useAdvancedCron, formCron])

  const applyPreset = (preset: 'daily_3' | 'hourly' | 'every_15' | 'mon_fri_9') => {
    if (useAdvancedCron) {
      if (preset === 'daily_3') {
        setFormCron('0 3 * * *')
      } else if (preset === 'hourly') {
        setFormCron('0 * * * *')
      } else if (preset === 'every_15') {
        setFormCron('*/15 * * * *')
      } else if (preset === 'mon_fri_9') {
        setFormCron('0 9 * * 1-5')
      }
      setCronError(null)
      setActivePreset(preset)
      return
    }

    setUseAdvancedCron(false)
    if (preset === 'daily_3') {
      setSimpleMode('daily')
      setSimpleTime('03:00')
    } else if (preset === 'hourly') {
      setSimpleMode('every_hours')
      setSimpleEveryHours(1)
    } else if (preset === 'every_15') {
      setSimpleMode('every_minutes')
      setSimpleEveryMinutes(15)
    } else if (preset === 'mon_fri_9') {
      setSimpleMode('weekly')
      setSimpleTime('09:00')
      setSimpleWeekdays(['1', '2', '3', '4', '5'])
    }
    setActivePreset(preset)
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Управление загрузкой данных</h1>
        <Link href={`/app/project/${projectId}/settings`}>← Назад к настройкам</Link>
      </div>

      {errorMessage && (
        <div
          className="card"
          style={{ marginTop: 12, background: '#fef2f2', borderColor: '#fecaca', color: '#b91c1c' }}
        >
          {errorMessage}
        </div>
      )}

      {successMessage && (
        <div
          className="card"
          style={{ marginTop: 12, background: '#ecfdf5', borderColor: '#a7f3d0', color: '#065f46' }}
        >
          {successMessage}
        </div>
      )}

      <div style={{ marginTop: 20, marginBottom: 16 }}>
        <div
          style={{
            display: 'inline-flex',
            borderRadius: 8,
            border: '1px solid #e5e7eb',
            padding: 2,
            background: '#f9fafb',
            overflow: 'hidden',
          }}
        >
          <button
            onClick={() => setActiveTab('schedules')}
            style={{
              padding: '6px 14px',
              border: 'none',
              cursor: 'pointer',
              borderRadius: 6,
              background: activeTab === 'schedules' ? '#2563eb' : 'transparent',
              color: activeTab === 'schedules' ? '#ffffff' : '#374151',
              fontWeight: activeTab === 'schedules' ? 600 : 400,
              boxShadow: activeTab === 'schedules' ? '0 1px 2px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            Расписание
          </button>
          <button
            onClick={() => setActiveTab('runs')}
            style={{
              padding: '6px 14px',
              border: 'none',
              cursor: 'pointer',
              borderRadius: 6,
              background: activeTab === 'runs' ? '#2563eb' : 'transparent',
              color: activeTab === 'runs' ? '#ffffff' : '#374151',
              fontWeight: activeTab === 'runs' ? 600 : 400,
              boxShadow: activeTab === 'runs' ? '0 1px 2px rgba(0,0,0,0.1)' : 'none',
            }}
          >
            История запусков
          </button>
        </div>
      </div>

      {activeTab === 'schedules' && (
        <div>
          <div className="card" style={{ marginBottom: 24, padding: 24 }}>
            <h2>Создать расписание</h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 16,
                alignItems: 'stretch',
                marginTop: 16,
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Источник</label>
                <div
                  style={{
                    height: 38,
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '0 10px',
                    borderRadius: 999,
                    border: '1px solid #d1d5db',
                    background: '#f9fafb',
                    fontSize: 13,
                    color: '#374151',
                  }}
                >
                  {selectedJob
                    ? selectedJob.source_code === 'wildberries'
                      ? 'Wildberries'
                      : 'Внутренние данные'
                    : '—'}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Задача</label>
                <select
                  value={formJob}
                  onChange={(e) => setFormJob(e.target.value)}
                  disabled={loadingJobs || jobs.length === 0}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                >
                  {loadingJobs && <option value="">Загрузка…</option>}
                  {!loadingJobs && jobs.length === 0 && <option value="">Нет доступных задач</option>}
                  {!loadingJobs &&
                    jobs.length > 0 &&
                    Object.entries(
                      jobs.reduce<Record<string, IngestJob[]>>((acc, job) => {
                        if (!job.supports_schedule) return acc
                        const key = job.source_code
                        if (!acc[key]) acc[key] = []
                        acc[key].push(job)
                        return acc
                      }, {})
                    ).map(([source, group]) => (
                      <optgroup
                        key={source}
                        label={source === 'wildberries' ? 'Wildberries' : 'Внутренние данные'}
                      >
                        {group.map((job) => (
                          <option key={job.job_code} value={job.job_code}>
                            {job.title}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Таймзона</label>
                <input
                  type="text"
                  value={formTimezone}
                  onChange={(e) => {
                    const value = e.target.value
                    setFormTimezone(value)
                    if (value.trim()) {
                      setTimezoneError(null)
                    }
                  }}
                  placeholder="Europe/Istanbul"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                />
                {timezoneError && (
                  <div style={{ marginTop: 4, fontSize: 12, color: '#b91c1c' }}>{timezoneError}</div>
                )}
                <div style={{ marginTop: 2, fontSize: 12, color: '#6b7280' }}>
                  Время будет интерпретировано в этой таймзоне.
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignSelf: 'flex-end' }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Статус</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 38 }}>
                  <input
                    id="schedule-enabled"
                    type="checkbox"
                    checked={formEnabled}
                    onChange={(e) => setFormEnabled(e.target.checked)}
                    style={{ width: 16, height: 16 }}
                  />
                  <label htmlFor="schedule-enabled" style={{ fontSize: 13 }}>
                    Включено
                  </label>
                </div>
              </div>
            </div>

            {/* Schedule mode card */}
            <div
              style={{
                marginTop: 16,
                padding: 16,
                borderRadius: 8,
                border: '1px solid #e5e7eb',
                background: '#f9fafb',
                display: 'flex',
                flexDirection: 'column',
                gap: 16,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontWeight: 500 }}>Настройки расписания</div>
                <div
                  style={{
                    display: 'inline-flex',
                    borderRadius: 999,
                    border: '1px solid #d1d5db',
                    overflow: 'hidden',
                    fontSize: 13,
                    background: '#f3f4f6',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setUseAdvancedCron(false)}
                    style={{
                      padding: '6px 14px',
                      border: 'none',
                      cursor: 'pointer',
                      background: useAdvancedCron ? 'transparent' : '#0070f3',
                      color: useAdvancedCron ? '#374151' : '#ffffff',
                      boxShadow: useAdvancedCron ? 'none' : '0 1px 2px rgba(0,0,0,0.1)',
                    }}
                  >
                    Простое расписание
                  </button>
                  <button
                    type="button"
                    onClick={() => setUseAdvancedCron(true)}
                    style={{
                      padding: '6px 14px',
                      border: 'none',
                      cursor: 'pointer',
                      background: useAdvancedCron ? '#0070f3' : 'transparent',
                      color: useAdvancedCron ? '#ffffff' : '#374151',
                      boxShadow: useAdvancedCron ? '0 1px 2px rgba(0,0,0,0.1)' : 'none',
                    }}
                  >
                    Cron
                  </button>
                </div>
              </div>

              {!useAdvancedCron && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: 16,
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <label style={{ fontSize: 13, fontWeight: 500 }}>Частота</label>
                    <select
                      value={simpleMode}
                      onChange={(e) => setSimpleMode(e.target.value as SimpleMode)}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        borderRadius: 5,
                        border: '1px solid #d1d5db',
                        fontSize: 14,
                        height: 38,
                      }}
                    >
                      <option value="daily">Ежедневно</option>
                      <option value="every_hours">Каждые N часов</option>
                      <option value="every_minutes">Каждые N минут</option>
                      <option value="weekly">Еженедельно</option>
                    </select>
                  </div>

                  {(simpleMode === 'daily' || simpleMode === 'weekly') && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <label style={{ fontSize: 13, fontWeight: 500 }}>Время (HH:MM)</label>
                      <input
                        type="time"
                        value={simpleTime}
                        onChange={(e) => setSimpleTime(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '8px 10px',
                          borderRadius: 5,
                          border: '1px solid #d1d5db',
                          fontSize: 14,
                          height: 38,
                        }}
                      />
                    </div>
                  )}

                  {simpleMode === 'every_hours' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <label style={{ fontSize: 13, fontWeight: 500 }}>Интервал</label>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="number"
                          min={1}
                          max={24}
                          value={simpleEveryHours}
                          onChange={(e) => {
                            const raw = e.target.value
                            const n = parseInt(raw, 10)
                            if (!raw) {
                              setSimpleIntervalError('Укажите интервал в часах')
                            } else if (Number.isNaN(n) || n < 1 || n > 24) {
                              setSimpleIntervalError('Допустимое значение: от 1 до 24 часов')
                            } else {
                              setSimpleIntervalError(null)
                            }
                            setSimpleEveryHours(clamp(n || 0, 1, 24))
                          }}
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: 5,
                            border: '1px solid #d1d5db',
                            fontSize: 14,
                            height: 38,
                          }}
                        />
                        <span style={{ fontSize: 13, color: '#4b5563' }}>часов</span>
                      </div>
                    </div>
                  )}

                  {simpleMode === 'every_minutes' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <label style={{ fontSize: 13, fontWeight: 500 }}>Интервал</label>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="number"
                          min={1}
                          max={60}
                          value={simpleEveryMinutes}
                          onChange={(e) => {
                            const raw = e.target.value
                            const n = parseInt(raw, 10)
                            if (!raw) {
                              setSimpleIntervalError('Укажите интервал в минутах')
                            } else if (Number.isNaN(n) || n < 1 || n > 60) {
                              setSimpleIntervalError('Допустимое значение: от 1 до 60 минут')
                            } else {
                              setSimpleIntervalError(null)
                            }
                            setSimpleEveryMinutes(clamp(n || 0, 1, 60))
                          }}
                          style={{
                            width: '100%',
                            padding: '8px 10px',
                            borderRadius: 5,
                            border: '1px solid #d1d5db',
                            fontSize: 14,
                            height: 38,
                          }}
                        />
                        <span style={{ fontSize: 13, color: '#4b5563' }}>минут</span>
                      </div>
                    </div>
                  )}

                  {simpleMode === 'weekly' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <label style={{ fontSize: 13, fontWeight: 500 }}>Дни недели</label>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {[
                          { v: '1', l: 'Пн' },
                          { v: '2', l: 'Вт' },
                          { v: '3', l: 'Ср' },
                          { v: '4', l: 'Чт' },
                          { v: '5', l: 'Пт' },
                          { v: '6', l: 'Сб' },
                          { v: '7', l: 'Вс' },
                        ].map((d) => (
                          <button
                            key={d.v}
                            type="button"
                            onClick={() => toggleWeekday(d.v)}
                            style={{
                              padding: '4px 10px',
                              borderRadius: 999,
                              border: '1px solid #d1d5db',
                              background: simpleWeekdays.includes(d.v) ? '#2563eb' : '#fff',
                              color: simpleWeekdays.includes(d.v) ? '#fff' : '#111827',
                              fontSize: 12,
                            }}
                          >
                            {d.l}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {simpleIntervalError && (
                    <div style={{ gridColumn: '1 / -1', fontSize: 12, color: '#b91c1c' }}>{simpleIntervalError}</div>
                  )}
                </div>
              )}

              {useAdvancedCron && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 500 }}>Cron выражение (5 полей)</label>
                  <input
                    type="text"
                    value={formCron}
                    onChange={(e) => {
                      const value = e.target.value
                      setFormCron(value)
                      if (useAdvancedCron) {
                        setCronError(validateCronExpr(value))
                      }
                    }}
                    placeholder="0 3 * * *"
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: 5,
                      border: '1px solid #d1d5db',
                      fontSize: 14,
                      height: 38,
                    }}
                  />
                  {cronError && (
                    <div style={{ marginTop: 4, fontSize: 12, color: '#b91c1c' }}>{cronError}</div>
                  )}
                  <button
                    type="button"
                    onClick={() => setShowCronExamples((prev) => !prev)}
                    style={{
                      marginTop: 2,
                      fontSize: 12,
                      color: '#2563eb',
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      cursor: 'pointer',
                    }}
                  >
                    Показать примеры
                  </button>
                  {showCronExamples && (
                    <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
                      <code style={{ background: '#f3f4f6', padding: '2px 4px' }}>0 3 * * *</code> — ежедневно в 03:00
                      <br />
                      <code style={{ background: '#f3f4f6', padding: '2px 4px' }}>0 * * * *</code> — каждый час
                      <br />
                      <code style={{ background: '#f3f4f6', padding: '2px 4px' }}>*/15 * * * *</code> — каждые 15 минут
                    </div>
                  )}
                </div>
              )}

              {/* Presets */}
              <div style={{ marginTop: 8, fontSize: 12 }}>
                <span style={{ marginRight: 8 }}>Шаблоны:</span>
                <button
                  type="button"
                  onClick={() => applyPreset('daily_3')}
                  style={{
                    marginRight: 6,
                    padding: '4px 10px',
                    fontSize: 12,
                    borderRadius: 999,
                    border: `1px solid ${activePreset === 'daily_3' ? '#0070f3' : '#d1d5db'}`,
                    background: activePreset === 'daily_3' ? '#0070f3' : '#ffffff',
                    color: activePreset === 'daily_3' ? '#ffffff' : '#374151',
                    cursor: 'pointer',
                  }}
                >
                  Ежедневно 03:00
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset('hourly')}
                  style={{
                    marginRight: 6,
                    padding: '4px 10px',
                    fontSize: 12,
                    borderRadius: 999,
                    border: `1px solid ${activePreset === 'hourly' ? '#0070f3' : '#d1d5db'}`,
                    background: activePreset === 'hourly' ? '#0070f3' : '#ffffff',
                    color: activePreset === 'hourly' ? '#ffffff' : '#374151',
                    cursor: 'pointer',
                  }}
                >
                  Каждый час
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset('every_15')}
                  style={{
                    marginRight: 6,
                    padding: '4px 10px',
                    fontSize: 12,
                    borderRadius: 999,
                    border: `1px solid ${activePreset === 'every_15' ? '#0070f3' : '#d1d5db'}`,
                    background: activePreset === 'every_15' ? '#0070f3' : '#ffffff',
                    color: activePreset === 'every_15' ? '#ffffff' : '#374151',
                    cursor: 'pointer',
                  }}
                >
                  Каждые 15 минут
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset('mon_fri_9')}
                  style={{
                    padding: '4px 10px',
                    fontSize: 12,
                    borderRadius: 999,
                    border: `1px solid ${activePreset === 'mon_fri_9' ? '#0070f3' : '#d1d5db'}`,
                    background: activePreset === 'mon_fri_9' ? '#0070f3' : '#ffffff',
                    color: activePreset === 'mon_fri_9' ? '#ffffff' : '#374151',
                    cursor: 'pointer',
                  }}
                >
                  Пн–Пт 09:00
                </button>
              </div>

              {/* Preview */}
              <div
                style={{
                  marginTop: 16,
                  padding: 16,
                  borderRadius: 6,
                  background: '#f3f4f6',
                  border: '1px solid #e5e7eb',
                  fontSize: 13,
                  color: '#111827',
                }}
              >
                <div>
                  <strong>Будет запускаться:</strong>{' '}
                  {useAdvancedCron ? `по cron (${formTimezone || 'Europe/Istanbul'})` : simpleSummary}
                </div>
                <div style={{ marginTop: 4 }}>
                  <strong>Cron:</strong> <code>{effectiveCron || '-'}</code>
                </div>
              </div>

              <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
                <button onClick={handleCreateSchedule} disabled={creatingSchedule || !isFormValid}>
                  {creatingSchedule ? 'Создание…' : 'Создать'}
                </button>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>Расписание</h2>
            {loadingSchedules ? (
              <p>Загрузка…</p>
            ) : schedules.length === 0 ? (
              <p>Расписок нет. Создайте первое.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Marketplace</th>
                      <th>Job</th>
                      <th>Расписание</th>
                      <th>Timezone</th>
                      <th>Next run (UTC)</th>
                      <th>Статус</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedules.map((s) => (
                      <tr key={s.id}>
                        <td>{s.marketplace_code}</td>
                        <td>{s.job_code}</td>
                        <td>
                          <div style={{ fontSize: 13, color: '#111827' }}>{cronToHuman(s.cron_expr)}</div>
                          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                            cron: <code>{s.cron_expr}</code>
                          </div>
                        </td>
                        <td>
                          <input
                            type="text"
                            defaultValue={s.timezone}
                            style={{ width: '150px' }}
                            onBlur={(e) =>
                              e.target.value !== s.timezone &&
                              handleEditSchedule(s, { timezone: e.target.value })
                            }
                            disabled={savingScheduleId === s.id}
                          />
                        </td>
                        <td>{formatDateTime(s.next_run_at)}</td>
                        <td style={{ textAlign: 'center' }}>
                          <button
                            type="button"
                            onClick={() => handleToggleSchedule(s)}
                            disabled={savingScheduleId === s.id}
                            style={{
                              padding: '2px 10px',
                              borderRadius: 999,
                              border: '1px solid ' + (s.is_enabled ? '#16a34a' : '#d1d5db'),
                              background: s.is_enabled ? '#dcfce7' : '#f9fafb',
                              color: s.is_enabled ? '#166534' : '#4b5563',
                              fontSize: 12,
                              cursor: savingScheduleId === s.id ? 'default' : 'pointer',
                              minWidth: 70,
                            }}
                          >
                            {s.is_enabled ? 'Включено' : 'Выключено'}
                          </button>
                        </td>
                        <td>
                          <button
                            onClick={() => handleRunNow(s)}
                            disabled={runningScheduleId === s.id}
                            style={{ marginRight: 8 }}
                          >
                            {runningScheduleId === s.id ? 'Запуск…' : 'Run now'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteSchedule(s)}
                            style={{
                              backgroundColor: '#f9fafb',
                              color: '#b91c1c',
                              border: '1px solid #fecaca',
                            }}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'runs' && (
        <div>
              <div className="card" style={{ marginBottom: 24 }}>
            <h2>Фильтры</h2>
            <div className={s.filtersGrid}>
              <div className={s.field}>
                <label className={s.label} htmlFor="ingestion-filters-marketplace">
                  Источник
                </label>
                <select
                  id="ingestion-filters-marketplace"
                  className={s.select}
                  value={filtersMarketplace}
                  onChange={(e) => setFiltersMarketplace(e.target.value)}
                >
                  <option value="">Все</option>
                  {jobSources.map((src) => (
                    <option key={src} value={src}>
                      {src === 'wildberries' ? 'Wildberries' : 'Внутренние данные'}
                    </option>
                  ))}
                </select>
              </div>
              <div className={s.field}>
                <label className={s.label} htmlFor="ingestion-filters-job">
                  Задача
                </label>
                <select
                  id="ingestion-filters-job"
                  className={s.select}
                  value={filtersJob}
                  onChange={(e) => setFiltersJob(e.target.value)}
                >
                  <option value="">Все</option>
                  {jobs.map((job) => (
                    <option key={job.job_code} value={job.job_code}>
                      {job.title}
                    </option>
                  ))}
                </select>
              </div>
              <div className={s.field}>
                <label className={s.label} htmlFor="ingestion-filters-status">
                  Status
                </label>
                <select
                  id="ingestion-filters-status"
                  className={s.select}
                  value={filtersStatus}
                  onChange={(e) => setFiltersStatus(e.target.value)}
                >
                  <option value="">Все</option>
                  <option value="queued">queued</option>
                  <option value="running">running</option>
                  <option value="success">success</option>
                  <option value="failed">failed</option>
                  <option value="canceled">canceled</option>
                </select>
              </div>
              <div className={s.field}>
                <label className={s.label} htmlFor="ingestion-filters-period">
                  Период
                </label>
                <select
                  id="ingestion-filters-period"
                  className={s.select}
                  value={filtersPeriod}
                  onChange={(e) => setFiltersPeriod(e.target.value as '7d' | '30d')}
                >
                  <option value="7d">Последние 7 дней</option>
                  <option value="30d">Последние 30 дней</option>
                </select>
              </div>
              <div className={s.buttonCell}>
                <button className={s.button} onClick={loadRuns} disabled={loadingRuns}>
                  {loadingRuns ? 'Обновление…' : 'Обновить'}
                </button>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>История запусков</h2>
            {loadingRuns ? (
              <p>Загрузка…</p>
            ) : runs.length === 0 ? (
              <p>Запусков не найдено.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Started</th>
                      <th>Last activity</th>
                      <th>Duration</th>
                      <th>Status</th>
                      <th>Marketplace</th>
                      <th>Job</th>
                      <th>Triggered by</th>
                      <th>Stats</th>
                      <th>Error</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr
                        key={r.id}
                        style={{ cursor: 'pointer' }}
                        onClick={() => loadRunDetails(r.id)}
                      >
                        <td>{formatDateTime(r.started_at || r.created_at)}</td>
                        <td title={getLastActivity(r) ? new Date(getLastActivity(r) as string).toISOString() : ''}>
                          {formatRelativeMinutes(getLastActivity(r))}
                        </td>
                        <td>{formatDuration(r.duration_ms)}</td>
                        <td>{renderStatusBadge(r.status)}</td>
                        <td>{r.marketplace_code}</td>
                        <td>{r.job_code}</td>
                        <td>{r.triggered_by}</td>
                        <td>{renderStatsSummary(r.stats_json)}</td>
                        <td>
                          {r.error_message
                            ? r.error_message.length > 60
                              ? `${r.error_message.slice(0, 57)}…`
                              : r.error_message
                            : '-'}
                        </td>
                        <td onClick={(e) => e.stopPropagation()}>
                          {(r.status === 'queued' || r.status === 'running') && (
                            <button
                              type="button"
                              onClick={() => setMarkTimeoutRunId(r.id)}
                              disabled={markingTimeout}
                              style={{
                                backgroundColor: '#fff7ed',
                                color: '#9a3412',
                                border: '1px solid #fed7aa',
                                padding: '4px 10px',
                                borderRadius: 8,
                              }}
                            >
                              Завершить (timeout)
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {runDetails && (
            <div
              className="card"
              style={{
                marginTop: 24,
                borderColor: '#d1d5db',
                background: '#f9fafb',
              }}
            >
              <h3>
                Run #{runDetails.id} — {runDetails.marketplace_code}/{runDetails.job_code}
              </h3>
              <p>
                <strong>Status:</strong> {renderStatusBadge(runDetails.status)}
              </p>
              <p>
                <strong>Triggered by:</strong> {runDetails.triggered_by}
              </p>
              <p>
                <strong>Started:</strong> {formatDateTime(runDetails.started_at)}
              </p>
              <p>
                <strong>Last activity:</strong>{' '}
                {formatDateTime((runDetails.heartbeat_at as any) || runDetails.updated_at)}
              </p>
              <p>
                <strong>Finished:</strong> {formatDateTime(runDetails.finished_at)}
              </p>
              <p>
                <strong>Duration:</strong> {formatDuration(runDetails.duration_ms)}
              </p>

              <details style={{ marginTop: 8 }}>
                <summary style={{ cursor: 'pointer' }}>
                  <strong>Stats JSON</strong>
                </summary>
                <pre
                  style={{
                    marginTop: 8,
                    maxHeight: 260,
                    overflow: 'auto',
                    background: '#111827',
                    color: '#e5e7eb',
                    padding: 8,
                    fontSize: 12,
                  }}
                >
                  {JSON.stringify(runDetails.stats_json, null, 2)}
                </pre>
              </details>

              {runDetails.error_message && (
                <div style={{ marginTop: 12 }}>
                  <strong>Error message:</strong>
                  <div style={{ marginTop: 4, color: '#b91c1c' }}>{runDetails.error_message}</div>
                </div>
              )}

              {runDetails.error_trace && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: 'pointer', color: '#b91c1c' }}>
                    <strong>Error trace</strong>
                  </summary>
                  <pre
                    style={{
                      marginTop: 8,
                      maxHeight: 260,
                      overflow: 'auto',
                      background: '#111827',
                      color: '#e5e7eb',
                      padding: 8,
                      fontSize: 12,
                    }}
                  >
                    {runDetails.error_trace}
                  </pre>
                </details>
              )}

              <div style={{ marginTop: 12 }}>
                <button onClick={() => setRunDetails(null)}>Закрыть</button>
              </div>
            </div>
          )}
        </div>
      )}

      {markTimeoutRunId != null && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 50,
          }}
        >
          <div
            className="card"
            style={{
              width: '100%',
              maxWidth: 520,
              background: '#ffffff',
              borderColor: '#e5e7eb',
            }}
          >
            <h3 style={{ marginTop: 0 }}>Завершить run как TIMEOUT?</h3>
            <div style={{ color: '#374151', fontSize: 13, lineHeight: 1.5 }}>
              Это логически завершит run и разблокирует планировщик.
              <br />
              Реально выполняющаяся задача может продолжить работу в фоне.
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button type="button" onClick={() => setMarkTimeoutRunId(null)} disabled={markingTimeout}>
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleMarkTimeout(markTimeoutRunId)}
                disabled={markingTimeout}
                style={{
                  backgroundColor: '#9a3412',
                  border: '1px solid #9a3412',
                  color: '#ffffff',
                }}
              >
                {markingTimeout ? 'Отметить…' : 'Mark timeout'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

