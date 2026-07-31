'use client'

import { useState } from 'react'
import Link from 'next/link'

export default function PnlReportPage() {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  return (
    <div>
      <Link href="/client" style={{ color: '#0070f3', fontSize: 14, marginBottom: 16, display: 'inline-block' }}>
        ← К списку отчётов
      </Link>
      <h2 style={{ marginBottom: 20, fontSize: '1.5rem' }}>PnL</h2>
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <label>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#666' }}>С</span>
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 5 }}
          />
        </label>
        <label>
          <span style={{ display: 'block', marginBottom: 4, fontSize: 14, color: '#666' }}>По</span>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 5 }}
          />
        </label>
        <button
          type="button"
          style={{ padding: '8px 20px', backgroundColor: '#0070f3', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}
        >
          Применить
        </button>
      </div>
    </div>
  )
}
