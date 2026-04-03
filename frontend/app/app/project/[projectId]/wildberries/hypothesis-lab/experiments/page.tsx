'use client'

import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  getHypothesisExperiments,
  type HypothesisExperimentListItem,
} from '@/lib/apiClient'
import PortalBackButton from '@/components/PortalBackButton'

const basePath = (projectId: string) => `/app/project/${projectId}/wildberries/hypothesis-lab/experiments`

export default function HypothesisLabExperimentsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  const [items, setItems] = useState<HypothesisExperimentListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [queryFilter, setQueryFilter] = useState('')

  useEffect(() => {
    let cancelled = false
    const queryParams: { status?: string; query?: string } = {}
    if (statusFilter) queryParams.status = statusFilter
    if (queryFilter.trim()) queryParams.query = queryFilter.trim()
    getHypothesisExperiments(projectId, queryParams)
      .then((data) => { if (!cancelled) setItems(data) })
      .catch((e) => { if (!cancelled) setError(e?.message || 'Ошибка загрузки') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId, statusFilter, queryFilter])

  return (
    <div className="container">
      <h1>Hypothesis Lab — Эксперименты</h1>
      <PortalBackButton href={`/app/project/${projectId}/wildberries`} label="Назад к Wildberries" />

      <div className="card" style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
          <Link
            href={`${basePath(projectId)}/new`}
            style={{
              display: 'inline-block',
              padding: '10px 18px',
              backgroundColor: '#0070f3',
              color: 'white',
              borderRadius: 6,
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            Создать эксперимент
          </Link>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          >
            <option value="">Все статусы</option>
            <option value="draft">draft</option>
            <option value="running">running</option>
            <option value="completed">completed</option>
            <option value="invalid">invalid</option>
          </select>
          <input
            type="text"
            placeholder="Поиск по гипотезе / SKU / названию"
            value={queryFilter}
            onChange={(e) => setQueryFilter(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd', minWidth: 220 }}
          />
        </div>

        {loading && <p>Загрузка…</p>}
        {error && <p style={{ color: 'red' }}>{error}</p>}
        {!loading && !error && (
          items.length === 0 ? (
            <p>Нет экспериментов.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                  <th style={{ padding: 8 }}>ID</th>
                  <th style={{ padding: 8 }}>Гипотеза</th>
                  <th style={{ padding: 8 }}>TEST SKU</th>
                  <th style={{ padding: 8 }}>Change type</th>
                  <th style={{ padding: 8 }}>Metric</th>
                  <th style={{ padding: 8 }}>Control</th>
                  <th style={{ padding: 8 }}>Статус</th>
                  <th style={{ padding: 8 }}>Период</th>
                  <th style={{ padding: 8 }}></th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: 8 }}>{e.id}</td>
                    <td style={{ padding: 8 }}>{e.hypothesis_title ?? e.hypothesis_id}</td>
                    <td style={{ padding: 8 }}>
                      <span>{e.nm_id}</span>
                      {e.product_title && <div style={{ fontSize: 12, color: '#666' }}>{e.product_title.slice(0, 40)}…</div>}
                    </td>
                    <td style={{ padding: 8 }}>{e.change_type}</td>
                    <td style={{ padding: 8 }}>{e.metric}</td>
                    <td style={{ padding: 8 }}>{e.control_mode} {e.controls_count != null ? `(${e.controls_count})` : ''}</td>
                    <td style={{ padding: 8 }}>{e.status}</td>
                    <td style={{ padding: 8 }}>{e.period_start && e.period_end ? `${e.period_start} — ${e.period_end}` : '—'}</td>
                    <td style={{ padding: 8 }}>
                      <Link href={`${basePath(projectId)}/${e.id}`}>Открыть</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}
