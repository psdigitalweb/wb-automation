'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { isAuthenticated } from '../lib/auth'
import Breadcrumbs from './Breadcrumbs'
import Topbar from './Topbar'
import './Topbar.css'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname() || '/'
  const [mounted, setMounted] = useState(false)
  const [isAuthed, setIsAuthed] = useState<boolean | null>(null)
  const [isReportsHost, setIsReportsHost] = useState(false)
  const inApp = pathname.startsWith('/app')

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (!mounted) return
    setIsReportsHost(typeof window !== 'undefined' && window.location.hostname === 'reports.zakka.ru')
  }, [mounted])

  useEffect(() => {
    if (!mounted) return
    if (inApp) {
      setIsAuthed(isAuthenticated())
    } else {
      setIsAuthed(null)
    }
  }, [mounted, inApp])

  useEffect(() => {
    if (!mounted) return
    if (inApp && isAuthed === false && !isReportsHost) router.push('/')
  }, [router, mounted, inApp, isAuthed, isReportsHost])

  // Avoid hydration mismatch: on the server (and initial client render), just
  // render children. After mount we can safely read window/localStorage.
  if (!mounted) return <>{children}</>

  if (!inApp)
    return (
      <>
        {children}
      </>
    )

  if (isAuthed === false && !isReportsHost) return null

  if (isReportsHost) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: '#f5f5f5', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
        <header style={{ padding: '16px 24px', backgroundColor: '#fff', borderBottom: '1px solid #e5e5e5' }}>
          <a href="/client" style={{ fontSize: '1.25rem', fontWeight: 600, color: 'inherit', textDecoration: 'none' }}>Отчёты</a>
        </header>
        <main style={{ maxWidth: 1400, margin: '0 auto', padding: 24 }}>
          {children}
        </main>
      </div>
    )
  }

  return (
    <div className="app-layout">
      <Topbar />
      <div className="app-content">
        <Breadcrumbs />
        {isAuthed === true ? children : null}
      </div>
    </div>
  )
}


