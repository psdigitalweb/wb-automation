'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { apiPost, ApiError } from '../lib/apiClient'

interface WBFinancesSectionProps {
  projectId: string
  title?: string
}

export default function WBFinancesSection({ projectId, title }: WBFinancesSectionProps) {
  const router = useRouter()
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Set default dates: first day of current month to today
  useEffect(() => {
    const today = new Date()
    const firstDayOfMonth = new Date(today.getFullYear(), today.getMonth(), 1)
    setDateFrom(firstDayOfMonth.toISOString().split('T')[0])
    setDateTo(today.toISOString().split('T')[0])
  }, [projectId])

  const handleIngest = async () => {
    if (!dateFrom || !dateTo) {
      setError('Пожалуйста, укажите обе даты')
      return
    }

    try {
      setLoading(true)
      setError(null)
      setSuccess(null)

      const { data } = await apiPost<any>(
        `/v1/projects/${projectId}/marketplaces/wildberries/finances/ingest`,
        {
          date_from: dateFrom,
          date_to: dateTo,
        }
      )

      setSuccess(
        `Загрузка запущена (task_id: ${data.task_id || 'N/A'}). Проверьте список отчётов через несколько секунд.`
      )
      setTimeout(() => setSuccess(null), 10000)
    } catch (e: any) {
      const err = e as ApiError
      setError(err.detail || 'Не удалось запустить загрузку финансовых отчётов')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card" style={{ marginTop: '24px' }}>
      <h2>{title ?? 'Wildberries — Finances'}</h2>

      {error && (
        <div
          style={{
            padding: '10px',
            marginBottom: '15px',
            backgroundColor: '#f8d7da',
            color: '#721c24',
            borderRadius: '4px',
          }}
        >
          <strong>Ошибка:</strong> {error}
        </div>
      )}

      {success && (
        <div
          style={{
            padding: '10px',
            marginBottom: '15px',
            backgroundColor: '#d4edda',
            color: '#155724',
            borderRadius: '4px',
          }}
        >
          <strong>Успех:</strong> {success}
        </div>
      )}

      <div style={{ display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div style={{ flex: '1', minWidth: '150px' }}>
          <label
            htmlFor="wb-finances-date-from"
            style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}
          >
            Date From
          </label>
          <input
            id="wb-finances-date-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            disabled={loading}
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
          />
        </div>

        <div style={{ flex: '1', minWidth: '150px' }}>
          <label
            htmlFor="wb-finances-date-to"
            style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}
          >
            Date To
          </label>
          <input
            id="wb-finances-date-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            disabled={loading}
            style={{ width: '100%', padding: '8px', fontSize: '14px' }}
          />
        </div>

        <button
          onClick={handleIngest}
          disabled={loading || !dateFrom || !dateTo}
          style={{
            backgroundColor: '#007bff',
            color: 'white',
            padding: '10px 20px',
            border: 'none',
            borderRadius: '4px',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading || !dateFrom || !dateTo ? 0.6 : 1,
          }}
        >
          {loading ? 'Загрузка...' : 'Загрузить финансовые отчеты WB'}
        </button>

        <button
          onClick={() => router.push(`/app/project/${projectId}/wildberries/finances/reports`)}
          style={{
            backgroundColor: '#28a745',
            color: 'white',
            padding: '10px 20px',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          Открыть список отчётов
        </button>
      </div>
    </div>
  )
}

