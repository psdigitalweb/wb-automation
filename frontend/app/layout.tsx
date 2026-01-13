import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'WB Automation Dashboard',
  description: 'Wildberries Automation Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  )
}

