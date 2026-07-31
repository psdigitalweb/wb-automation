import './globals.css'

import { Suspense } from 'react'
import AppShell from '../components/AppShell'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <Suspense fallback={<>{children}</>}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  )
}
