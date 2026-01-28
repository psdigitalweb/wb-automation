'use client'

import React, { useMemo, useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPost, ApiError } from '@/lib/apiClient'

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
  const router = useRouter()
  const projectId = params.projectId as string
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
    } catch (e: any) {
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
    } catch (e: any) {
      const err = e as ApiError
      const fallback = err?.bodyPreview ? `${err.detail || 'Ошибка'} (${err.status}): ${err.bodyPreview}` : null
      setManualError(err.detail || fallback || 'Не удалось запустить загрузку финансовых отчётов')
    } finally {
      setManualLoading(false)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('ru-RU')
  }

  return (
    <div className="container">
      <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>WB Finances — Reports</h1>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button onClick={loadReports} disabled={loading}>
            {loading ? 'Обновление...' : 'Обновить список'}
          </button>
          <button onClick={() => router.push(`/app/project/${projectId}/marketplaces`)}>
            Назад к настройкам
          </button>
        </div>
      </div>

      {error && (
        <div style={{ 
          padding: '15px', 
          marginBottom: '20px', 
          backgroundColor: '#f8d7da', 
          color: '#721c24', 
          borderRadius: '4px'
        }}>
          <strong>Ошибка:</strong> {error}
        </div>
      )}

      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ padding: '16px 20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '16px' }}>
            <h2 style={{ margin: 0 }}>Ручная загрузка</h2>
            <div style={{ color: '#6c757d', fontSize: '0.85rem' }}>
              WB может отвечать долго; если долго — попробуем позже.
            </div>
          </div>

          {manualError && (
            <div
              style={{
                padding: '10px',
                marginTop: '12px',
                backgroundColor: '#f8d7da',
                color: '#721c24',
                borderRadius: '4px',
              }}
            >
              <strong>Ошибка:</strong> {manualError}
            </div>
          )}

          {manualSuccess && (
            <div
              style={{
                padding: '10px',
                marginTop: '12px',
                backgroundColor: '#d4edda',
                color: '#155724',
                borderRadius: '4px',
              }}
            >
              <strong>ОК:</strong> {manualSuccess}
            </div>
          )}

          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap', marginTop: '12px' }}>
            <div style={{ flex: '1', minWidth: '160px' }}>
              <label
                htmlFor="wb-finances-manual-date-from"
                style={{ display: 'block', marginBottom: '5px', fontWeight: 500 }}
              >
                date_from
              </label>
              <input
                id="wb-finances-manual-date-from"
                type="date"
                value={manualDateFrom}
                onChange={(e) => setManualDateFrom(e.target.value)}
                disabled={manualLoading}
                style={{ width: '100%', padding: '8px', fontSize: '14px' }}
              />
            </div>

            <div style={{ flex: '1', minWidth: '160px' }}>
              <label
                htmlFor="wb-finances-manual-date-to"
                style={{ display: 'block', marginBottom: '5px', fontWeight: 500 }}
              >
                date_to
              </label>
              <input
                id="wb-finances-manual-date-to"
                type="date"
                value={manualDateTo}
                onChange={(e) => setManualDateTo(e.target.value)}
                disabled={manualLoading}
                style={{ width: '100%', padding: '8px', fontSize: '14px' }}
              />
            </div>

            <button
              onClick={handleManualIngest}
              disabled={manualLoading || !!manualValidationError}
              style={{
                backgroundColor: '#2563eb',
                color: 'white',
                padding: '10px 18px',
                border: 'none',
                borderRadius: '4px',
                cursor: manualLoading ? 'not-allowed' : 'pointer',
                opacity: manualLoading || !!manualValidationError ? 0.6 : 1,
              }}
            >
              {manualLoading ? 'Загрузка…' : 'Загрузить'}
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <p>Загрузка...</p>
      ) : reports.length === 0 ? (
        <div className="card">
          <p style={{ padding: '20px', textAlign: 'center', color: '#6c757d' }}>
            Отчётов пока нет — запустите загрузку в блоке «Ручная загрузка» выше
          </p>
          <div style={{ textAlign: 'center', marginTop: '15px' }}>
            <button
              onClick={() => router.push(`/app/project/${projectId}/marketplaces`)}
              style={{
                backgroundColor: '#007bff',
                color: 'white',
                padding: '10px 20px',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Перейти к настройкам
            </button>
          </div>
        </div>
      ) : (
        <div className="card">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #dee2e6' }}>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 'bold' }}>Report ID</th>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 'bold' }}>Period From</th>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 'bold' }}>Period To</th>
                <th style={{ padding: '12px', textAlign: 'right', fontWeight: 'bold' }}>Rows Count</th>
              </tr>
            </thead>
            <tbody>
              {sortedReports.map((report, index) => (
                <tr 
                  key={report.report_id} 
                  style={{ 
                    borderBottom: '1px solid #dee2e6',
                    backgroundColor: index % 2 === 0 ? '#fff' : '#f8f9fa'
                  }}
                >
                  <td style={{ padding: '12px' }}>{report.report_id}</td>
                  <td style={{ padding: '12px' }}>{formatDate(report.period_from)}</td>
                  <td style={{ padding: '12px' }}>{formatDate(report.period_to)}</td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>{report.rows_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
