'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function SystemMarketplacesRedirect() {
  const router = useRouter()
  
  useEffect(() => {
    router.replace('/app/admin/settings/marketplaces')
  }, [router])
  
  return (
    <div className="container">
      <p>Перенаправление...</p>
    </div>
  )
}
