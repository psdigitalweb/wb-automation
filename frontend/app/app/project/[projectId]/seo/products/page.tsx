'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import { getSeoProducts, type SeoProductListItem } from '@/lib/apiClient'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../_components/SeoShell'

export default function SeoProductsPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params
  const searchParams = useSearchParams()
  const [categoryId, setCategoryId] = useState(searchParams.get('category_id') || '')
  const [q, setQ] = useState('')
  const [items, setItems] = useState<SeoProductListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  usePageTitle('SEO: товары', projectId)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getSeoProducts(projectId, { category_id: categoryId ? Number(categoryId) : undefined, q: q || undefined, limit: 100 })
      setItems(data.items)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId])

  return (
    <SeoShell projectId={projectId} title="Товары" subtitle="Поиск товара и запуск анализа для подбора SEO-запросов.">
      <div style={{ display: 'grid', gap: 16 }}>
        <Card>
          <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr auto', gap: 10, alignItems: 'end' }}>
            <label>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>Категория</div>
              <input value={categoryId} onChange={(e) => setCategoryId(e.target.value)} placeholder="category_id" style={{ width: '100%', padding: 10 }} />
            </label>
            <label>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>Товар</div>
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="nm_id, артикул или часть названия" style={{ width: '100%', padding: 10 }} />
            </label>
            <button type="button" onClick={load} disabled={loading} style={buttonStyle('primary')}>{loading ? 'Ищем...' : 'Найти'}</button>
          </div>
        </Card>
        {error && <Card><div style={{ color: '#b91c1c' }}>{error}</div></Card>}
        <div style={{ display: 'grid', gap: 12 }}>
          {items.map((item) => {
            const catSuffix = item.category_id ? `?category_id=${item.category_id}` : ''
            const base = `/app/project/${projectId}/seo/products/${item.nm_id}`
            return (
              <Card key={item.nm_id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                  <div>
                    <h2 style={{ margin: '0 0 6px' }}>{item.title || item.nm_id}</h2>
                    <div style={{ color: '#64748b' }}>nm_id {item.nm_id} · {item.category_name || item.category_id || 'категория не указана'}</div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                      <StatusPill label={item.analysis_status} tone={item.has_sku_atoms ? 'good' : 'warn'} />
                      {item.has_vision_atoms && <StatusPill label="Фото учтены" tone="good" />}
                      {item.category_status && <StatusPill label={item.category_status} tone={item.category_status === 'Готова к подбору' ? 'good' : 'warn'} />}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    <Link href={`${base}${catSuffix}`} style={buttonStyle('primary')}>Открыть</Link>
                    {item.category_id && (
                      <>
                        <Link href={`${base}/queries${catSuffix}`} style={buttonStyle('light')}>Запросы</Link>
                        <Link href={`${base}/compare${catSuffix}`} style={buttonStyle('light')}>Compare</Link>
                        <Link href={`${base}/generation${catSuffix}`} style={buttonStyle('ghost')}>Генерация</Link>
                      </>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
          {!items.length && !loading && <Card>Товары не найдены.</Card>}
        </div>
      </div>
    </SeoShell>
  )
}
