export default function ClientLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#f5f5f5',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      <header style={{
        padding: '16px 24px',
        backgroundColor: '#fff',
        borderBottom: '1px solid #e5e5e5',
      }}>
        <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>Отчёты</h1>
      </header>
      <main style={{
        maxWidth: 1200,
        margin: '0 auto',
        padding: 24,
      }}>
        {children}
      </main>
    </div>
  )
}
