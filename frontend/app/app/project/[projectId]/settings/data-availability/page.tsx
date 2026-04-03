'use client'

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import Link from 'next/link'
import { apiGet } from '../../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../../hooks/usePageTitle'

type CoverageSegment = {
  start: string // YYYY-MM-DD
  end: string // YYYY-MM-DD
  count: number
}

type DatasetAvailability = {
  code: string
  title: string
  grain: 'day' | 'week'
  status: 'OK' | 'WARN' | 'EMPTY' | 'NOT_CONFIGURED' | 'ERROR'
  window_from: string
  window_to: string
  expected_count: number
  present_count: number
  missing_count: number
  min_present: string | null
  max_present: string | null
  present_segments: CoverageSegment[]
  missing_segments: CoverageSegment[]
  note: string | null
}

type DataAvailabilityResponse = {
  project_id: number
  window_days: number
  window_from: string
  window_to: string
  items: DatasetAvailability[]
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const parts = String(iso).split('-')
  if (parts.length !== 3) return String(iso)
  const [y, m, d] = parts
  if (!y || !m || !d) return String(iso)
  return `${d}.${m}.${y}`
}

function segmentLabel(seg: CoverageSegment): string {
  const a = fmtDate(seg.start)
  const b = fmtDate(seg.end)
  const range = seg.start === seg.end ? a : `${a}–${b}`
  return `${range} (${seg.count})`
}

export default function ProjectDataAvailabilityPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  usePageTitle('Наличие данных', projectId)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<DataAvailabilityResponse | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await apiGet<DataAvailabilityResponse>(`/api/v1/projects/${projectId}/data-availability?days=90`)
        setData(res.data)
      } catch (e: any) {
        setError(e?.detail || 'Failed to load data availability')
        setData(null)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectId])

  const items = useMemo(() => (data?.items || []).slice().sort((a, b) => a.title.localeCompare(b.title)), [data])

  const badgeStyle = (status: DatasetAvailability['status']) => {
    const base: CSSProperties = {
      display: 'inline-flex',
      alignItems: 'center',
      padding: '2px 10px',
      borderRadius: 999,
      fontSize: 12,
      fontWeight: 700,
      border: '1px solid transparent',
      whiteSpace: 'nowrap',
    }
    if (status === 'OK') return { ...base, background: '#dcfce7', color: '#166534', borderColor: '#a7f3d0' }
    if (status === 'WARN') return { ...base, background: '#fef9c3', color: '#854d0e', borderColor: '#fde68a' }
    if (status === 'EMPTY') return { ...base, background: '#fee2e2', color: '#991b1b', borderColor: '#fecaca' }
    if (status === 'NOT_CONFIGURED') return { ...base, background: '#f3f4f6', color: '#4b5563', borderColor: '#e5e7eb' }
    return { ...base, background: '#fef2f2', color: '#7f1d1d', borderColor: '#fecaca' }
  }

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1 style={{ margin: 0 }}>Наличие данных</h1>
        <Link href={`/app/project/${projectId}/settings`}>← Настройки проекта</Link>
      </div>

      <div style={{ marginTop: 10, color: '#6b7280' }}>
        Окно: последние <strong>90</strong> дней{data ? ` (${fmtDate(data.window_from)}–${fmtDate(data.window_to)})` : ''}
      </div>

      {loading ? <div style={{ marginTop: 16 }}>Загрузка…</div> : null}
      {error ? (
        <div style={{ marginTop: 16, color: '#b91c1c' }}>
          {error}
        </div>
      ) : null}

      {!loading && !error && (
        <div className="card" style={{ padding: 16, marginTop: 16 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 8px' }}>Датасет</th>
                <th style={{ padding: '10px 8px' }}>Статус</th>
                <th style={{ padding: '10px 8px' }}>Периоды “есть”</th>
                <th style={{ padding: '10px 8px' }}>Гэпы</th>
                <th style={{ padding: '10px 8px' }}>Примечание</th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.code} style={{ borderBottom: '1px solid #f3f4f6', verticalAlign: 'top' }}>
                  <td style={{ padding: '10px 8px' }}>
                    <div style={{ fontWeight: 700 }}>{it.title}</div>
                    <div style={{ fontSize: 12, color: '#6b7280' }}>
                      {it.grain === 'week' ? 'недели' : 'дни'} · есть: {it.present_count}/{it.expected_count}
                      {it.max_present ? ` · последнее: ${fmtDate(it.max_present)}` : ''}
                    </div>
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={badgeStyle(it.status)}>{it.status}</span>
                  </td>
                  <td style={{ padding: '10px 8px', fontSize: 13 }}>
                    {it.present_segments.length === 0 ? (
                      <span style={{ color: '#6b7280' }}>—</span>
                    ) : it.present_segments.length <= 3 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {it.present_segments.map((s, idx) => (
                          <div key={idx}>{segmentLabel(s)}</div>
                        ))}
                      </div>
                    ) : (
                      <details>
                        <summary style={{ cursor: 'pointer' }}>
                          {it.present_segments.slice(0, 2).map(segmentLabel).join(', ')}…
                        </summary>
                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {it.present_segments.map((s, idx) => (
                            <div key={idx}>{segmentLabel(s)}</div>
                          ))}
                        </div>
                      </details>
                    )}
                  </td>
                  <td style={{ padding: '10px 8px', fontSize: 13 }}>
                    {it.missing_segments.length === 0 ? (
                      <span style={{ color: '#6b7280' }}>—</span>
                    ) : it.missing_segments.length <= 2 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {it.missing_segments.map((s, idx) => (
                          <div key={idx}>{segmentLabel(s)}</div>
                        ))}
                      </div>
                    ) : (
                      <details>
                        <summary style={{ cursor: 'pointer' }}>
                          {it.missing_segments.slice(0, 2).map(segmentLabel).join(', ')}…
                        </summary>
                        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {it.missing_segments.map((s, idx) => (
                            <div key={idx}>{segmentLabel(s)}</div>
                          ))}
                        </div>
                      </details>
                    )}
                  </td>
                  <td style={{ padding: '10px 8px', fontSize: 12, color: '#6b7280' }}>
                    {it.note || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
