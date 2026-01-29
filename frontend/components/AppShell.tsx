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
  const inApp = pathname.startsWith('/app')

  useEffect(() => {
    setMounted(true)
  }, [])

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
    if (inApp && isAuthed === false) router.push('/')
  }, [router, mounted, inApp, isAuthed])

  // Avoid hydration mismatch: on the server (and initial client render), just
  // render children. After mount we can safely read window/localStorage.
  if (!mounted) return <>{children}</>

  if (!inApp)
    return (
      <>
        {children}
      </>
    )

  if (isAuthed === false) return null

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


