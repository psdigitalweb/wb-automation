'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, ApiError } from '@/lib/apiClient'

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

export default function WBFinancesReportsPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [reports, setReports] = useState<WBFinanceReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadReports()
  }, [projectId])

  const loadReports = async () => {
    try {
      setLoading(true)
      setError(null)
      const { data } = await apiGet<WBFinanceReport[]>(
        `/v1/projects/${projectId}/marketplaces/wildberries/finances/reports`
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

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('ru-RU')
  }

  const formatDateTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU')
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

      {loading ? (
        <p>Загрузка...</p>
      ) : reports.length === 0 ? (
        <div className="card">
          <p style={{ padding: '20px', textAlign: 'center', color: '#6c757d' }}>
            Отчётов пока нет — загрузите их в настройках проекта
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
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 'bold' }}>Currency</th>
                <th style={{ padding: '12px', textAlign: 'right', fontWeight: 'bold' }}>Total Amount</th>
                <th style={{ padding: '12px', textAlign: 'right', fontWeight: 'bold' }}>Rows Count</th>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 'bold' }}>Last Seen At</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report, index) => (
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
                  <td style={{ padding: '12px' }}>{report.currency || '-'}</td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>
                    {report.total_amount !== null ? report.total_amount.toLocaleString('ru-RU') : '-'}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>{report.rows_count}</td>
                  <td style={{ padding: '12px' }}>{formatDateTime(report.last_seen_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
