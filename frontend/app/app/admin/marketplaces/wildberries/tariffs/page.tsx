'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function WBTariffsRedirect() {
  const router = useRouter()
  
  useEffect(() => {
    router.replace('/app/admin/settings/wb-tariffs')
  }, [router])
  
  return (
    <div className="container">
      <p>Перенаправление...</p>
    </div>
  )
}
