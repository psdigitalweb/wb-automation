'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { isSuperuser } from '../../../lib/admin'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()

  useEffect(() => {
    if (!isSuperuser()) {
      router.push('/app/projects')
    }
  }, [router])

  if (!isSuperuser()) {
    return (
      <div className="container">
        <h1>Access Denied</h1>
        <p>Not enough permissions. Superuser access required.</p>
      </div>
    )
  }

  return <>{children}</>
}
