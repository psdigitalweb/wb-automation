'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import { getSeoCategories, getSeoProducts, type SeoCategoryListItem, type SeoProductListItem } from '@/lib/apiClient'
import { Card, Panel, SeoShell, StatusPill, buttonClass, normalizeError, seoStyles } from '../_components/SeoShell'

const pageSize = 200

function compactStatus(value: string | null | undefined, ready: boolean) {
  if (ready) return 'готов'
  if (!value) return 'нужен анализ'
  const normalized = value.toLowerCase()
  if (normalized.includes('проанализ')) return 'нужен анализ'
  if (normalized.includes('готов')) return 'готов'
  return value
}

export default function SeoProductsPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params
  const searchParams = useSearchParams()
  const [categoryId, setCategoryId] = useState(searchParams.get('category_id') || '')
  const [q, setQ] = useState('')
  const [stockStatus, setStockStatus] = useState('all')
  const [categories, setCategories] = useState<SeoCategoryListItem[]>([])
  const [items, setItems] = useState<SeoProductListItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  usePageTitle('SEO: товары', projectId)

  const load = async (nextOffset = offset) => {
    setLoading(true)
    setError(null)
    try {
      const data = await getSeoProducts(projectId, {
        category_id: categoryId ? Number(categoryId) : undefined,
        q: q || undefined,
        stock_status: stockStatus,
        limit: pageSize,
        offset: nextOffset,
      })
      setItems(data.items)
      setTotal(data.total)
      setOffset(nextOffset)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    getSeoCategories(projectId)
      .then(setCategories)
      .catch(() => setCategories([]))
  }, [projectId])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      load(0)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [projectId, categoryId, q, stockStatus])

  const visionReady = items.filter((item) => item.has_vision_atoms).length
  const meaningReady = items.filter((item) => item.has_sku_atoms).length
  const pageStart = total && items.length ? offset + 1 : 0
  const pageEnd = offset + items.length

  return (
    <SeoShell projectId={projectId} title="Товары" subtitle="Единая очередь товаров для vision, подбора и утверждения запросов.">
      <div className={seoStyles.metricGrid}>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>Найдено SKU</div><div className={seoStyles.metricValue}>{total.toLocaleString('ru-RU')}</div></div>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>На странице</div><div className={seoStyles.metricValue}>{items.length.toLocaleString('ru-RU')}</div></div>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>Meaning готов</div><div className={seoStyles.metricValue}>{meaningReady}</div></div>
        <div className={seoStyles.metricCard}><div className={seoStyles.metricLabel}>Vision готов</div><div className={seoStyles.metricValue}>{visionReady}</div></div>
      </div>

      <form
        className={seoStyles.filterBar}
        onSubmit={(event) => {
          event.preventDefault()
          load(0)
        }}
      >
        <label className={`${seoStyles.filterControl} ${seoStyles.searchControl}`}>
          <span className={seoStyles.searchIcon}>⌕</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Артикул / nmID / название..."
            aria-label="Поиск по артикулу, nmID или названию"
          />
        </label>
        <label className={seoStyles.filterControl}>
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} aria-label="Категория">
            <option value="">Категории: Все</option>
            {categories.map((category) => (
              <option key={category.category_id} value={category.category_id}>
                {category.category_name}
              </option>
            ))}
          </select>
        </label>
        <label className={seoStyles.filterControl}>
          <select value={stockStatus} onChange={(e) => setStockStatus(e.target.value)} aria-label="Наличие на складе предприятия">
            <option value="all">Склад предприятия: все</option>
            <option value="in_stock">Склад предприятия: в наличии</option>
            <option value="out_of_stock">Склад предприятия: нет</option>
          </select>
        </label>
      </form>

      {error ? <Card><div style={{ color: 'var(--seo-danger)' }}>{error}</div></Card> : null}

      <Panel
        title="Товары"
        subtitle={total ? `Показаны ${pageStart}-${pageEnd} из ${total.toLocaleString('ru-RU')}. Клик по строке открывает рабочий экран SKU.` : 'Клик по строке открывает рабочий экран SKU.'}
        actions={
          <div className={seoStyles.pager}>
            <button type="button" className={buttonClass('light')} disabled={loading || offset === 0} onClick={() => load(Math.max(0, offset - pageSize))}>
              Назад
            </button>
            <button type="button" className={buttonClass('light')} disabled={loading || pageEnd >= total} onClick={() => load(offset + pageSize)}>
              Вперед
            </button>
          </div>
        }
      >
        <div className={seoStyles.tableWrap}>
          <table className={`${seoStyles.table} ${seoStyles.productsTable}`}>
            <thead>
              <tr>
                <th style={{ minWidth: 420 }}>Товар</th>
                <th>Отзывы</th>
                <th>Склад</th>
                <th>Vision</th>
                <th>Подбор</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const catSuffix = item.category_id ? `?category_id=${item.category_id}` : ''
                const reviews = item.review_count ?? item.feedbacks
                const stockKnown = item.stock_quantity != null || item.in_stock != null
                return (
                  <tr key={item.nm_id} className={seoStyles.clickable}>
                    <td>
                      <Link href={`/app/project/${projectId}/seo/products/${item.nm_id}${catSuffix}`} className={seoStyles.productCore} style={{ textDecoration: 'none' }}>
                        {item.photo_url ? <img src={item.photo_url} alt="" className={seoStyles.thumb} /> : <span className={seoStyles.thumb}>фото</span>}
                        <span>
                          <span className={seoStyles.sku}>{item.vendor_code || item.article || 'SKU'}</span>
                          <span className={seoStyles.subtext}>nm_id: {item.nm_id}</span>
                        </span>
                        <span>
                          <span className={seoStyles.productTitle}>{item.title || `SKU ${item.nm_id}`}</span>
                          <span className={seoStyles.subtext}>{item.category_name || item.subject_name || item.category_id || 'без категории'}</span>
                        </span>
                      </Link>
                    </td>
                    <td className={seoStyles.num}>{reviews ?? '-'}</td>
                    <td>{stockKnown ? (item.in_stock ? '✓' : '✗') : '-'}</td>
                    <td>{item.has_vision_atoms ? '✓' : '—'}</td>
                    <td>{item.has_sku_atoms ? 'готов' : '—'}</td>
                    <td>
                      <StatusPill label={compactStatus(item.analysis_status, Boolean(item.has_sku_atoms))} tone={item.has_sku_atoms ? 'good' : 'warn'} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {!items.length && !loading ? <div className={seoStyles.muted}>Товары не найдены.</div> : null}
      </Panel>
    </SeoShell>
  )
}
