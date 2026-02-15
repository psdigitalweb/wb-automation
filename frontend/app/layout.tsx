import './globals.css'

import AppShell from '../components/AppShell'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // #region agent log
  try {
    // #endregion
    return (
      <html lang="ru">
        <body>
          <AppShell>{children}</AppShell>
        </body>
      </html>
    )
  } catch (e) {
    // #region agent log
    const payload = {
      hypothesisId: 'H1',
      location: 'layout.tsx:RootLayout',
      message: 'Root layout render error',
      data: {
        errorMessage: e instanceof Error ? e.message : String(e),
        stack: e instanceof Error ? e.stack?.slice(0, 1000) : undefined,
      },
      timestamp: Date.now(),
    }
    console.error('[DEBUG]', JSON.stringify(payload))
    // #endregion
    throw e
  }
}


