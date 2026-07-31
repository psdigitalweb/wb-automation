'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { getHypothesesMvp, type HypothesisMvpItem } from '@/lib/apiClient'

export default function HypothesesPage() {
  const [items, setItems] = useState<HypothesisMvpItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    getHypothesesMvp({
      query: query.trim() || undefined,
      limit: 100,
      status: statusFilter || undefined,
    })
      .then((data) => {
        if (!cancelled) setItems(data)
      })
      .catch((e) => {
        if (!cancelled) setError(e?.detail ?? e?.message ?? 'Ошибка загрузки')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [query, statusFilter])

  return (
    <div className="container">
      <h1>Гипотезы</h1>
      <p style={{ color: '#666', marginBottom: 16 }}>
        Глобальная библиотека гипотез для будущих экспериментов.
      </p>
      <Link href="/app/projects" style={{ color: '#0070f3', textDecoration: 'none' }}>
        ← К списку проектов
      </Link>

      <div className="card" style={{ marginTop: 20 }}>
        <div
          style={{
            display: 'flex',
            gap: 12,
            alignItems: 'center',
            marginBottom: 16,
            flexWrap: 'wrap',
          }}
        >
          <input
            type="text"
            placeholder="Поиск по названию или ключу"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd', minWidth: 260 }}
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          >
            <option value="">Все статусы</option>
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
          </select>
          <Link
            href="/app/hypotheses/new"
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
            Создать
          </Link>
        </div>

        {loading && <p>Загрузка...</p>}
        {error && <p style={{ color: 'red' }}>{error}</p>}
        {!loading && !error && (
          items.length === 0 ? (
            <p>Гипотез не найдено.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                  <th style={{ padding: 8 }}>key</th>
                  <th style={{ padding: 8 }}>title</th>
                  <th style={{ padding: 8 }}>status</th>
                  <th style={{ padding: 8 }}>domain</th>
                  <th style={{ padding: 8 }}>type</th>
                  <th style={{ padding: 8 }}>updated_at</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: 8 }}>{item.key || '—'}</td>
                    <td style={{ padding: 8 }}>{item.title || '—'}</td>
                    <td style={{ padding: 8 }}>{item.status}</td>
                    <td style={{ padding: 8 }}>{item.domain || '—'}</td>
                    <td style={{ padding: 8 }}>{item.hypothesis_type || '—'}</td>
                    <td style={{ padding: 8 }}>
                      {item.updated_at ? new Date(item.updated_at).toLocaleString() : '—'}
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
