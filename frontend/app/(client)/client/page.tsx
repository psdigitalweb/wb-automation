import Link from 'next/link'

const reports = [
  { title: 'PnL', desc: 'Прибыли и убытки', href: '/client/reports/pnl' },
  { title: 'Продажи', desc: 'Данные о продажах', href: '/client/reports/sales' },
  { title: 'Остатки', desc: 'Текущие остатки товаров', href: '/client/reports/stock' },
  { title: 'Логистика', desc: 'Данные по логистике', href: '/client/reports/logistics' },
]

export default function ClientReportsPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24, fontSize: '1.5rem' }}>Отчёты</h2>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        gap: 20,
      }}>
        {reports.map((r) => (
          <div
            key={r.href}
            style={{
              backgroundColor: '#fff',
              borderRadius: 8,
              padding: 20,
              boxShadow: '0 2px 4px rgba(0,0,0,0.08)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>{r.title}</h3>
            <p style={{ margin: 0, color: '#666', fontSize: 14 }}>{r.desc}</p>
            <Link
              href={r.href}
              style={{
                alignSelf: 'flex-start',
                padding: '8px 16px',
                backgroundColor: '#0070f3',
                color: '#fff',
                borderRadius: 5,
                fontSize: 14,
                textDecoration: 'none',
              }}
            >
              Открыть
            </Link>
          </div>
        ))}
      </div>
    </div>
  )
}
