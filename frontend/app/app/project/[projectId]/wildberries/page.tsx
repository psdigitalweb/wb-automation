'use client'

import { useParams } from 'next/navigation'
import Link from 'next/link'

export default function WildberriesPage() {
  const params = useParams()
  const projectId = params.projectId as string

  return (
    <div className="container">
      <h1>Wildberries</h1>
      <Link href={`/app/project/${projectId}/dashboard`}>
        <button type="button">← Назад к дашборду</button>
      </Link>

      <div className="card" style={{ marginTop: 20 }}>
        <h2 style={{ marginTop: 0 }}>Инструменты</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Link
            href={`/app/project/${projectId}/wildberries/price-discrepancies`}
            style={{
              display: 'inline-block',
              padding: '12px 20px',
              backgroundColor: '#0070f3',
              color: 'white',
              textDecoration: 'none',
              borderRadius: 6,
              fontWeight: 500,
              transition: 'background-color 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#0051cc'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#0070f3'
            }}
          >
            Расхождения цен (РРЦ vs Витрина)
          </Link>
        </div>
      </div>
    </div>
  )
}
