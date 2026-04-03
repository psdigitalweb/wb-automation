'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function HypothesisLabPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string

  useEffect(() => {
    router.replace(`/app/project/${projectId}/wildberries/hypothesis-lab/experiments`)
  }, [router, projectId])

  return (
    <div className="container">
      <p>Перенаправление в раздел «Эксперименты»…</p>
    </div>
  )
}
