import Link from 'next/link'

export default function Client404Page() {
  return (
    <div style={{ padding: '48px 0', textAlign: 'center' }}>
      <h2 style={{ marginBottom: 12, fontSize: '1.5rem', fontWeight: 600 }}>Страница не найдена</h2>
      <p style={{ color: '#666', marginBottom: 24 }}>Запрашиваемая страница не существует.</p>
      <Link
        href="/client"
        style={{
          padding: '10px 20px',
          backgroundColor: '#0070f3',
          color: '#fff',
          borderRadius: 5,
          textDecoration: 'none',
          display: 'inline-block',
        }}
      >
        К списку отчётов
      </Link>
    </div>
  )
}
