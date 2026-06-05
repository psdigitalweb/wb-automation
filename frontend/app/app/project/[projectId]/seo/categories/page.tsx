'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoCategories,
  type SeoCategoryListItem,
} from '@/lib/apiClient'
import { Card, Panel, SeoShell, StatusPill, buttonClass, normalizeError, seoStyles } from '../_components/SeoShell'

function tone(status?: string | null): 'good' | 'warn' | 'bad' | 'neutral' {
  if (status === 'ready_for_matching') return 'good'
  if (status === 'ready_with_fallback' || status === 'building') return 'warn'
  if (status === 'failed') return 'bad'
  return 'neutral'
}

function label(status?: string | null) {
  if (status === 'ready_for_matching') return 'готова'
  if (status === 'ready_with_fallback') return 'fallback'
  if (status === 'building') return 'обработка'
  if (status === 'failed') return 'ошибка'
  return 'нет CSV'
}

function formatCount(value?: number | null) {
  return (value ?? 0).toLocaleString('ru-RU')
}

export default function SeoCategoriesPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params
  const [items, setItems] = useState<SeoCategoryListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  usePageTitle('SEO: категории', projectId)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getSeoCategories(projectId)
      .then((categories) => {
        if (cancelled) return
        setItems(categories)
      })
      .catch((e) => setError(normalizeError(e)))
      .finally(() => setLoading(false))
    return () => {
      cancelled = true
    }
  }, [projectId])

  const readyCount = items.filter((item) => item.readiness_status === 'ready_for_matching').length
  const buildingCount = items.filter((item) => item.readiness_status === 'building').length
  const totalProducts = items.reduce((sum, item) => sum + Number(item.skus_count || 0), 0)

  return (
    <SeoShell projectId={projectId} title="Категории" subtitle="Готовность категорий к подбору запросов и ручной проверке.">
      <div className={seoStyles.metricGrid}>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>Категорий</div><div className={seoStyles.metricValue}>{items.length}</div></div>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>Готовы к подбору</div><div className={seoStyles.metricValue}>{readyCount}</div></div>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>В обработке</div><div className={seoStyles.metricValue}>{buildingCount}</div></div>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>SKU в категориях</div><div className={seoStyles.metricValue}>{formatCount(totalProducts)}</div></div>
      </div>

      {error ? <Card><div style={{ color: 'var(--seo-danger)' }}>{error}</div></Card> : null}
      {loading ? (
        <Card>Загружаем категории...</Card>
      ) : (
        <Panel title="Категории" subtitle="Состояние query data, кластеров, prior и очереди проверки.">
          <div className={seoStyles.tableWrap}>
            <table className={seoStyles.table}>
              <thead>
                <tr>
                  <th>Категория</th>
                  <th>Статус</th>
                  <th>Товаров</th>
                  <th>Смыслов</th>
                  <th>Query data</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const readiness = item.readiness_status
                  return (
                    <tr key={item.category_id} className={seoStyles.clickable}>
                      <td>
                        <strong>{item.category_name}</strong>
                        <div className={seoStyles.subtext}>WB subject_id {item.category_id}</div>
                      </td>
                      <td><StatusPill label={label(readiness)} tone={tone(readiness)} /></td>
                      <td className={seoStyles.num}>{formatCount(item.skus_count)}</td>
                      <td className={seoStyles.num}>{formatCount(item.query_meanings_count)}</td>
                      <td>
                        <span className={seoStyles.subtext}>
                          {readiness === 'ready_for_matching'
                            ? 'готова к matcher'
                            : readiness === 'building'
                              ? 'система готовит категорию'
                              : item.has_query_corpus
                                ? 'есть corpus, нужна обработка'
                                : 'загрузите CSV и запустите обработку'}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link className={buttonClass('primary')} href={`/app/project/${projectId}/seo/categories/${item.category_id}`}>
                          Открыть
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {items.length === 0 ? <div className={seoStyles.muted}>В проекте пока нет категорий с товарами.</div> : null}
        </Panel>
      )}
    </SeoShell>
  )
}
