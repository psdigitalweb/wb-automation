'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  getHypothesesMvp,
  getWBProductLookup,
  createHypothesisExperiment,
  type HypothesisMvpItem,
  type WBProductLookupItem,
} from '@/lib/apiClient'
import PortalBackButton from '@/components/PortalBackButton'

const basePath = (projectId: string) => `/app/project/${projectId}/wildberries/hypothesis-lab/experiments`

const CHANGE_TYPES = ['cover', 'images_set', 'title', 'description', 'seo', 'other'] as const
const METRICS = ['views', 'carts', 'orders', 'order_sum', 'cart_rate', 'order_cr', 'order_from_cart'] as const

export default function NewHypothesisLabExperimentPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [hypotheses, setHypotheses] = useState<HypothesisMvpItem[]>([])
  const [hypothesisSearch, setHypothesisSearch] = useState('')
  const [productSearch, setProductSearch] = useState('')
  const [productItems, setProductItems] = useState<WBProductLookupItem[]>([])
  const [hypothesisId, setHypothesisId] = useState<number | null>(null)
  const [nmId, setNmId] = useState<number | null>(null)
  const [changeType, setChangeType] = useState<string>('title')
  const [changeNote, setChangeNote] = useState('')
  const [metric, setMetric] = useState<string>('orders')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHypothesesMvp({ query: hypothesisSearch || undefined, limit: 20 }).then(setHypotheses).catch(() => setHypotheses([]))
  }, [hypothesisSearch])

  useEffect(() => {
    if (!productSearch.trim()) {
      setProductItems([])
      return
    }
    getWBProductLookup(projectId, { q: productSearch, limit: 15 }).then((r) => setProductItems(r.items || [])).catch(() => setProductItems([]))
  }, [projectId, productSearch])

  const handleCreate = () => {
    if (hypothesisId == null || nmId == null || !changeNote.trim()) {
      setError('Укажите гипотезу, TEST SKU и примечание к изменению.')
      return
    }
    setError(null)
    setSubmitting(true)
    createHypothesisExperiment(projectId, {
      hypothesis_id: hypothesisId,
      nm_id: nmId,
      change_type: changeType,
      change_note: changeNote.trim(),
      metric,
    })
      .then((created) => router.push(`${basePath(projectId)}/${created.id}`))
      .catch((e) => {
        setError(e?.detail ?? e?.message ?? 'Ошибка создания')
        setSubmitting(false)
      })
  }

  return (
    <div className="container">
      <h1>Новый эксперимент</h1>
      <PortalBackButton href={basePath(projectId)} label="Назад к списку" />

      <div className="card" style={{ marginTop: 20, maxWidth: 560 }}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Гипотеза (глобальная)</label>
          <input
            type="text"
            placeholder="Поиск по названию"
            value={hypothesisSearch}
            onChange={(e) => setHypothesisSearch(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          />
          <select
            value={hypothesisId ?? ''}
            onChange={(e) => setHypothesisId(e.target.value ? Number(e.target.value) : null)}
            style={{ width: '100%', marginTop: 6, padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          >
            <option value="">Выберите гипотезу</option>
            {hypotheses.map((h) => (
              <option key={h.id} value={h.id}>{h.title || h.key || h.id}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>TEST SKU</label>
          <input
            type="text"
            placeholder="Поиск по nm_id или артикулу"
            value={productSearch}
            onChange={(e) => setProductSearch(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          />
          <select
            value={nmId ?? ''}
            onChange={(e) => setNmId(e.target.value ? Number(e.target.value) : null)}
            style={{ width: '100%', marginTop: 6, padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          >
            <option value="">Выберите товар</option>
            {productItems.map((p) => (
              <option key={p.nm_id} value={p.nm_id}>{p.nm_id} — {p.title?.slice(0, 50) ?? p.vendor_code ?? ''}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Тип изменения</label>
          <select
            value={changeType}
            onChange={(e) => setChangeType(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          >
            {CHANGE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Примечание к изменению *</label>
          <textarea
            value={changeNote}
            onChange={(e) => setChangeNote(e.target.value)}
            rows={3}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Метрика</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
          >
            {METRICS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {error && <p style={{ color: 'red', marginBottom: 12 }}>{error}</p>}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            onClick={handleCreate}
            disabled={submitting}
            style={{ padding: '10px 18px', backgroundColor: '#0070f3', color: 'white', border: 'none', borderRadius: 6, fontWeight: 500, cursor: submitting ? 'wait' : 'pointer' }}
          >
            {submitting ? 'Создание…' : 'Создать (draft)'}
          </button>
          <Link href={basePath(projectId)} style={{ padding: '10px 18px', color: '#666', textDecoration: 'none' }}>Отмена</Link>
        </div>
        <p style={{ fontSize: 12, color: '#666', marginTop: 12 }}>Control mode и количество контролов будут рассчитаны автоматически после создания.</p>
      </div>
    </div>
  )
}
