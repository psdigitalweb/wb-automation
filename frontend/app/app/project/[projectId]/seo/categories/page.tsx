'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getCategoryBootstrapStatus,
  getWBProductSubjects,
  type CategoryBootstrapStatusResponse,
  type WBProductSubjectItem,
} from '@/lib/apiClient'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../_components/SeoShell'

function tone(status?: string | null): 'good' | 'warn' | 'bad' | 'neutral' {
  if (status === 'ready_for_matching') return 'good'
  if (status === 'ready_with_fallback' || status === 'building') return 'warn'
  if (status === 'failed') return 'bad'
  return 'neutral'
}

function label(status?: string | null) {
  if (status === 'ready_for_matching') return 'Готова к подбору'
  if (status === 'ready_with_fallback') return 'Можно подбирать'
  if (status === 'building') return 'Обрабатывается'
  if (status === 'failed') return 'Нужно повторить обработку'
  return 'Загрузите запросы'
}

function hint(status?: string | null, item?: CategoryBootstrapStatusResponse) {
  if (status === 'ready_for_matching') return `${item?.query_meanings_count ?? 0} смыслов запросов`
  if (status === 'ready_with_fallback') return 'Смыслы построены без полного LLM-улучшения'
  if (status === 'building') return 'Система готовит категорию в фоне'
  if (status === 'failed') return 'Откройте категорию и повторите обработку'
  return 'CSV с запросами еще не загружен'
}

export default function SeoCategoriesPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params
  const [items, setItems] = useState<WBProductSubjectItem[]>([])
  const [statuses, setStatuses] = useState<Record<number, CategoryBootstrapStatusResponse>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  usePageTitle('SEO: категории', projectId)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getWBProductSubjects(projectId)
      .then(async (subjects) => {
        if (cancelled) return
        setItems(subjects)
        const settled = await Promise.allSettled(
          subjects.map((item) => getCategoryBootstrapStatus(projectId, { category_id: Number(item.subject_id) }))
        )
        if (cancelled) return
        const next: Record<number, CategoryBootstrapStatusResponse> = {}
        settled.forEach((result) => {
          if (result.status === 'fulfilled') {
            next[result.value.category_id] = result.value
          }
        })
        setStatuses(next)
      })
      .catch((e) => setError(normalizeError(e)))
      .finally(() => setLoading(false))
    return () => {
      cancelled = true
    }
  }, [projectId])

  return (
    <SeoShell projectId={projectId} title="Категории и запросы" subtitle="Управление корпусом поисковых запросов по категориям.">
      {error && <Card><div style={{ color: '#b91c1c' }}>{error}</div></Card>}
      {loading ? (
        <Card>Загружаем категории...</Card>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {items.map((item) => (
            <Card key={item.subject_id}>
              {(() => {
                const status = statuses[Number(item.subject_id)]
                const readiness = status?.readiness_status
                return (
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center' }}>
                <div>
                  <h2 style={{ margin: '0 0 6px' }}>{item.subject_name}</h2>
                  <div style={{ color: '#64748b' }}>
                    ID {item.subject_id} · {item.skus_count} товаров · {hint(readiness, status)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <StatusPill label={label(readiness)} tone={tone(readiness)} />
                  <Link href={`/app/project/${projectId}/seo/categories/${item.subject_id}/eval`} style={buttonStyle('light')}>Eval</Link>
                  <Link href={`/app/project/${projectId}/seo/categories/${item.subject_id}`} style={buttonStyle('primary')}>Открыть</Link>
                </div>
              </div>
                )
              })()}
            </Card>
          ))}
          {items.length === 0 && <Card>В проекте пока нет категорий с товарами.</Card>}
        </div>
      )}
    </SeoShell>
  )
}
