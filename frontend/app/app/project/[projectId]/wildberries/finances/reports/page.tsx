'use client'

import React, { useMemo, useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { apiGet, apiPost, type ApiError } from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import styles from './reports.module.css'

interface WBFinanceReport {
  report_id: number
  period_from: string | null
  period_to: string | null
  currency: string | null
  total_amount: number | null
  rows_count: number
  first_seen_at: string
  last_seen_at: string
}

interface WBFinancesIngestResponse {
  status: string
  task_id: string | null
  date_from: string
  date_to: string
}

export default function WBFinancesReportsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Финансовые отчёты WB', projectId)
  const [reports, setReports] = useState<WBFinanceReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [manualDateFrom, setManualDateFrom] = useState<string>('')
  const [manualDateTo, setManualDateTo] = useState<string>('')
  const [manualLoading, setManualLoading] = useState(false)
  const [manualError, setManualError] = useState<string | null>(null)
  const [manualSuccess, setManualSuccess] = useState<string | null>(null)

  useEffect(() => {
    loadReports()
  }, [projectId])

  // Default dates: first day of current month to today (как в других местах проекта)
  useEffect(() => {
    const today = new Date()
    const firstDayOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)
    setManualDateFrom(firstDayOfMonth.toISOString().split('T')[0])
    setManualDateTo(today.toISOString().split('T')[0])
  }, [projectId])

  const loadReports = async () => {
    try {
      setLoading(true)
      setError(null)
      const { data } = await apiGet<WBFinanceReport[]>(
        `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/reports`
      )
      setReports(data)
    } catch (e: unknown) {
      const err = e as ApiError
      if (err.status === 404) {
        setReports([])
      } else {
        setError(err.detail || 'Не удалось загрузить список отчётов')
      }
    } finally {
      setLoading(false)
    }
  }

  const sortedReports = useMemo(() => {
    // Sort by period_to (date_to) desc. Nulls go last.
    return [...reports].sort((a, b) => {
      const aKey = a.period_to || ''
      const bKey = b.period_to || ''
      // YYYY-MM-DD => string compare works
      return bKey.localeCompare(aKey)
    })
  }, [reports])

  const manualValidationError = useMemo(() => {
    if (!manualDateFrom) return 'Дата начала обязательна'
    if (!manualDateTo) return 'Дата окончания обязательна'
    // YYYY-MM-DD сравнивается лексикографически корректно
    if (manualDateFrom > manualDateTo) return 'Дата начала должна быть меньше или равна дате окончания'
    return null
  }, [manualDateFrom, manualDateTo])

  const handleManualIngest = async () => {
    setManualError(null)
    setManualSuccess(null)

    if (manualValidationError) {
      setManualError(manualValidationError)
      return
    }

    try {
      setManualLoading(true)
      const date_from = String(manualDateFrom).slice(0, 10)
      const date_to = String(manualDateTo).slice(0, 10)

      // Ручная загрузка финансовых отчётов WB — отдельный endpoint (НЕ общий /ingestions/*)
      const { data } = await apiPost<WBFinancesIngestResponse>(
        `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/ingest`,
        { date_from, date_to }
      )

      const runMsg = data?.task_id ? `Запуск создан: #${data.task_id}.` : 'Загрузка запущена.'
      setManualSuccess(`${runMsg} Таблица отчётов обновится автоматически.`)

      // refetch: сразу после успешного запуска
      await loadReports()
    } catch (e: unknown) {
      const err = e as ApiError
      const fallback = err?.bodyPreview ? `${err.detail || 'Ошибка'} (${err.status}): ${err.bodyPreview}` : null
      setManualError(err.detail || fallback || 'Не удалось запустить загрузку финансовых отчётов')
    } finally {
      setManualLoading(false)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleDateString('ru-RU')
  }

  const formatAmount = (amount: number | null, currency: string | null) => {
    if (amount == null) return '—'
    try {
      return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: currency || 'RUB',
        maximumFractionDigits: 0,
      }).format(amount)
    } catch {
      return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(amount)
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <div className={styles.eyebrow}>Wildberries · Финансы</div>
          <div className={styles.titleRow}>
            <h1>Финансовые отчёты</h1>
            <span className={styles.marketplaceBadge}><span />WB</span>
          </div>
          <p>Загрузка и история финансовых отчётов для расчёта Unit PNL.</p>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.buttonSecondary} type="button" onClick={loadReports} disabled={loading}>
            {loading ? 'Обновляем…' : 'Обновить'}
          </button>
          <Link className={styles.buttonSecondary} href={`/app/project/${projectId}/marketplaces`}>
            Настройки WB
          </Link>
        </div>
      </header>

      {error ? (
        <div className={`${styles.notice} ${styles.noticeError}`} role="alert">
          <strong>Не удалось загрузить отчёты</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <section className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <h2>Загрузка отчётов</h2>
            <p>Выберите период, за который нужно запросить финансовые данные WB.</p>
          </div>
          <span className={styles.cardMeta}>Запрос может занять несколько минут</span>
        </div>
        <div className={styles.cardBody}>
          <div className={styles.filterGrid}>
            <label className={styles.field} htmlFor="wb-finances-manual-date-from">
              <span>Период с</span>
              <input
                id="wb-finances-manual-date-from"
                type="date"
                value={manualDateFrom}
                onChange={(event) => setManualDateFrom(event.target.value)}
                disabled={manualLoading}
              />
            </label>

            <label className={styles.field} htmlFor="wb-finances-manual-date-to">
              <span>Период по</span>
              <input
                id="wb-finances-manual-date-to"
                type="date"
                value={manualDateTo}
                onChange={(event) => setManualDateTo(event.target.value)}
                disabled={manualLoading}
              />
            </label>

            <button
              className={styles.buttonPrimary}
              type="button"
              onClick={handleManualIngest}
              disabled={manualLoading || Boolean(manualValidationError)}
            >
              {manualLoading ? 'Запускаем…' : 'Загрузить отчёты'}
            </button>
          </div>

          {manualError ? (
            <div className={`${styles.notice} ${styles.noticeError}`} role="alert">
              <strong>Загрузка не запущена</strong>
              <span>{manualError}</span>
            </div>
          ) : null}

          {manualSuccess ? (
            <div className={`${styles.notice} ${styles.noticeSuccess}`} role="status" aria-live="polite">
              <strong>Загрузка запущена</strong>
              <span>{manualSuccess}</span>
            </div>
          ) : null}
        </div>
      </section>

      <section className={styles.tableCard}>
        <div className={styles.cardHeader}>
          <div>
            <h2>История отчётов</h2>
            <p>Последние полученные финансовые отчёты Wildberries.</p>
          </div>
          {!loading ? <span className={styles.countBadge}>{reports.length}</span> : null}
        </div>

        {loading ? (
          <div className={styles.loadingState} aria-label="Загрузка отчётов">
            <span />
            <span />
            <span />
          </div>
        ) : reports.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon} aria-hidden="true">₽</div>
            <strong>Финансовых отчётов пока нет</strong>
            <p>Выберите период выше и запустите первую загрузку.</p>
            <Link className={styles.buttonSecondary} href={`/app/project/${projectId}/marketplaces`}>
              Проверить подключение WB
            </Link>
          </div>
        ) : (
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>ID отчёта</th>
                  <th>Период с</th>
                  <th>Период по</th>
                  <th className={styles.numeric}>Строк</th>
                  <th className={styles.numeric}>Сумма</th>
                  <th><span className={styles.srOnly}>Действия</span></th>
                </tr>
              </thead>
              <tbody>
                {sortedReports.map((report) => (
                  <tr key={report.report_id}>
                    <td className={styles.mono}>#{report.report_id}</td>
                    <td>{formatDate(report.period_from)}</td>
                    <td>{formatDate(report.period_to)}</td>
                    <td className={`${styles.numeric} ${styles.mono}`}>{report.rows_count.toLocaleString('ru-RU')}</td>
                    <td className={styles.numeric}>{formatAmount(report.total_amount, report.currency)}</td>
                    <td className={styles.actionCell}>
                      <Link href={`/app/project/${projectId}/wildberries/finances/unit-pnl?report_id=${report.report_id}`}>
                        Открыть
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
