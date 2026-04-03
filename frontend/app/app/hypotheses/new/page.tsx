'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { createHypothesis } from '@/lib/apiClient'

export default function NewHypothesisPage() {
  const router = useRouter()
  const [key, setKey] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [domain, setDomain] = useState('')
  const [hypothesisType, setHypothesisType] = useState('')
  const [hypothesisText, setHypothesisText] = useState('')
  const [primaryMetricKey, setPrimaryMetricKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!key.trim() || !title.trim()) {
      setError('Укажите key и title.')
      return
    }

    setError(null)
    setSubmitting(true)

    createHypothesis({
      key: key.trim(),
      title: title.trim(),
      description: description.trim() || undefined,
      domain: domain.trim() || undefined,
      hypothesis_type: hypothesisType.trim() || undefined,
      hypothesis_text: hypothesisText.trim() || undefined,
      primary_metric_key: primaryMetricKey.trim() || undefined,
    })
      .then(() => router.replace('/app/hypotheses'))
      .catch((e) => {
        setError(e?.detail ?? e?.message ?? 'Ошибка создания')
        setSubmitting(false)
      })
  }

  return (
    <div className="container">
      <h1>Создать гипотезу</h1>
      <Link href="/app/hypotheses" style={{ color: '#0070f3', textDecoration: 'none' }}>
        ← К списку гипотез
      </Link>

      <div className="card" style={{ marginTop: 20, maxWidth: 560 }}>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>key *</label>
            <input
              type="text"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>domain</label>
            <input
              type="text"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>hypothesis_type</label>
            <input
              type="text"
              value={hypothesisType}
              onChange={(e) => setHypothesisType(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>hypothesis_text</label>
            <textarea
              value={hypothesisText}
              onChange={(e) => setHypothesisText(e.target.value)}
              rows={3}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>primary_metric_key</label>
            <input
              type="text"
              value={primaryMetricKey}
              onChange={(e) => setPrimaryMetricKey(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
            />
          </div>

          {error && <p style={{ color: 'red', marginBottom: 12 }}>{error}</p>}

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="submit"
              disabled={submitting}
              style={{
                padding: '10px 18px',
                backgroundColor: '#0070f3',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                fontWeight: 500,
                cursor: submitting ? 'wait' : 'pointer',
              }}
            >
              {submitting ? 'Создание...' : 'Создать'}
            </button>
            <Link href="/app/hypotheses" style={{ padding: '10px 18px', color: '#666', textDecoration: 'none' }}>
              Отмена
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
