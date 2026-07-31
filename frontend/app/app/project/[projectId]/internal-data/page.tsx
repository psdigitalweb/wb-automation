'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPatch, apiPost } from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'

interface InternalCategory {
  id: number
  key: string
  name: string
  parent_id: number | null
}

interface InternalDataProduct {
  id: number
  internal_sku: string
  name: string | null
  lifecycle_status: string | null
  internal_category_id: number | null
  attributes: {
    stock?: number
    barcode?: string
    [key: string]: any
  } | null
  price_rrp: number | null
  price_currency: string | null
  cost: number | null
  cost_currency: string | null
}

interface InternalDataProductsResponse {
  total: number
  items: InternalDataProduct[]
}

type MappingStatus = 'confirmed' | 'proposed' | 'rejected' | 'conflict' | 'unmatched'

interface ProductMappingItem {
  marketplace_product_id: number
  marketplace_code: string
  marketplace_item_id: string
  marketplace_sku: string | null
  title: string | null
  mapping_id: number | null
  internal_sku: string | null
  mapping_source: string | null
  confidence: number | null
  candidate_internal_skus: string[] | null
  effective_status: MappingStatus
}

interface ProductMappingDiagnostics {
  project_id: number
  internal_catalog_products: number
  total_marketplace_products: number
  confirmed: number
  proposed: number
  rejected: number
  conflict: number
  unmatched: number
  items: ProductMappingItem[]
}

export default function InternalDataPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  usePageTitle('Каталог товаров', projectId)
  const [products, setProducts] = useState<InternalDataProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [withStockOnly, setWithStockOnly] = useState(false)
  const [categories, setCategories] = useState<InternalCategory[]>([])
  const [categoriesLoading, setCategoriesLoading] = useState(false)
  const [editingCategory, setEditingCategory] = useState<string | null>(null)
  const [categorySearch, setCategorySearch] = useState('')
  const [categoryDropdownOpen, setCategoryDropdownOpen] = useState<string | null>(null)
  const [mappingDiagnostics, setMappingDiagnostics] = useState<ProductMappingDiagnostics | null>(null)
  const [mappingStatus, setMappingStatus] = useState<MappingStatus | ''>('')
  const [mappingLoading, setMappingLoading] = useState(false)
  const [mappingError, setMappingError] = useState<string | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const pageSize = 100

  useEffect(() => {
    loadProducts()
    loadCategories()
  }, [projectId, page, withStockOnly])

  useEffect(() => {
    loadMappings()
  }, [projectId, mappingStatus])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setCategoryDropdownOpen(null)
        setCategorySearch('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const loadProducts = async () => {
    try {
      setLoading(true)
      setError(null)
      const offset = (page - 1) * pageSize
      const result = await apiGet<InternalDataProductsResponse>(
        `/api/v1/projects/${projectId}/internal-data/products?limit=${pageSize}&offset=${offset}&with_stock_only=${withStockOnly}&include_category=true`
      )
      setProducts(result.data.items)
      setTotal(result.data.total)
    } catch (err: any) {
      console.error('Failed to load internal data products:', err)
      setError(err?.detail || 'Failed to load products')
    } finally {
      setLoading(false)
    }
  }

  const loadCategories = async () => {
    try {
      setCategoriesLoading(true)
      const result = await apiGet<{ total: number; items: InternalCategory[] }>(
        `/api/v1/projects/${projectId}/internal-data/categories?limit=500&offset=0`
      )
      setCategories(result.data.items)
    } catch (err: any) {
      console.error('Failed to load categories:', err)
    } finally {
      setCategoriesLoading(false)
    }
  }

  const loadMappings = async () => {
    try {
      setMappingLoading(true)
      setMappingError(null)
      const statusQuery = mappingStatus ? `&status=${mappingStatus}` : ''
      const result = await apiGet<ProductMappingDiagnostics>(
        `/api/v1/projects/${projectId}/internal-data/product-mappings?limit=100&offset=0${statusQuery}`
      )
      setMappingDiagnostics(result.data)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить связи товаров'
      setMappingError(message)
    } finally {
      setMappingLoading(false)
    }
  }

  const reconcileMappings = async () => {
    try {
      setMappingLoading(true)
      setMappingError(null)
      await apiPost(`/api/v1/projects/${projectId}/internal-data/product-mappings/reconcile`, {})
      await loadMappings()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Не удалось пересобрать связи'
      setMappingError(message)
    } finally {
      setMappingLoading(false)
    }
  }

  const setMappingDecision = async (mappingId: number, status: 'confirmed' | 'rejected') => {
    try {
      setMappingError(null)
      await apiPatch(`/api/v1/projects/${projectId}/internal-data/product-mappings/${mappingId}`, { status })
      await loadMappings()
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Не удалось изменить статус связи'
      setMappingError(message)
    }
  }

  const mappingStatusLabel = (status: MappingStatus) => ({
    confirmed: 'Подтверждено',
    proposed: 'Требует подтверждения',
    rejected: 'Отклонено',
    conflict: 'Конфликт',
    unmatched: 'Не связано',
  })[status]

  const updateProductCategory = async (sku: string, categoryId: number | null) => {
    try {
      await apiPatch(`/api/v1/projects/${projectId}/internal-data/products/${sku}/category`, {
        category_id: categoryId,
      })
      setProducts((prev) =>
        prev.map((p) => (p.internal_sku === sku ? { ...p, internal_category_id: categoryId } : p))
      )
      setCategoryDropdownOpen(null)
      setCategorySearch('')
    } catch (err: any) {
      console.error('Failed to update category:', err)
      alert(err?.detail || 'Ошибка при обновлении категории')
    }
  }

  const getCategoryName = (categoryId: number | null) => {
    if (!categoryId) return null
    const cat = categories.find((c) => c.id === categoryId)
    return cat ? cat.name : null
  }

  const filteredCategories = categories.filter(
    (cat) => !categorySearch || cat.name.toLowerCase().includes(categorySearch.toLowerCase()) || cat.key.toLowerCase().includes(categorySearch.toLowerCase())
  )

  const formatNumber = (value: number | null | undefined) => {
    if (value === null || value === undefined) return 'N/A'
    return value.toLocaleString('ru-RU')
  }

  return (
    <div className="container">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Внутренние данные</h1>
        <button
          onClick={() => router.push(`/app/project/${projectId}/dashboard`)}
          style={{
            padding: '8px 16px',
            backgroundColor: '#6c757d',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          Назад к дашборду
        </button>
      </div>

      <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={withStockOnly}
            onChange={(e) => {
              setWithStockOnly(e.target.checked)
              setPage(1)
            }}
          />
          <span>Только товары в наличии (stock {'>'} 0)</span>
        </label>
        <span style={{ color: '#666', fontSize: 14 }}>
          Всего: {total} товаров
        </span>
      </div>

      <section style={{ marginBottom: 24, padding: 16, background: '#fff', border: '1px solid #dee2e6', borderRadius: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 12 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>Связи с маркетплейсами</h2>
            <div style={{ marginTop: 4, color: '#666', fontSize: 13 }}>
              Наш SKU связывает карточки Wildberries и Ozon с себестоимостью и РРЦ.
            </div>
          </div>
          <button type="button" onClick={reconcileMappings} disabled={mappingLoading} style={{ padding: '8px 14px' }}>
            {mappingLoading ? 'Обновление…' : 'Пересобрать связи'}
          </button>
        </div>

        {mappingError ? <div style={{ color: '#842029', marginBottom: 12 }}>{mappingError}</div> : null}

        {mappingDiagnostics ? (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              {([
                ['Внутренний каталог', mappingDiagnostics.internal_catalog_products],
                ['Карточки МП', mappingDiagnostics.total_marketplace_products],
                ['Подтверждено', mappingDiagnostics.confirmed],
                ['На проверке', mappingDiagnostics.proposed],
                ['Конфликты', mappingDiagnostics.conflict],
                ['Не связаны', mappingDiagnostics.unmatched],
              ] as Array<[string, number]>).map(([label, value]) => (
                <div key={label} style={{ minWidth: 130, padding: '8px 12px', background: '#f8f9fa', borderRadius: 6 }}>
                  <div style={{ color: '#666', fontSize: 12 }}>{label}</div>
                  <div style={{ fontSize: 20, fontWeight: 600 }}>{formatNumber(value)}</div>
                </div>
              ))}
            </div>

            <div style={{ marginBottom: 10 }}>
              <select value={mappingStatus} onChange={(event) => setMappingStatus(event.target.value as MappingStatus | '')}>
                <option value="">Все статусы</option>
                <option value="proposed">Требуют подтверждения</option>
                <option value="conflict">Конфликты</option>
                <option value="unmatched">Не связаны</option>
                <option value="confirmed">Подтверждены</option>
                <option value="rejected">Отклонены</option>
              </select>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f8f9fa' }}>
                    <th style={{ padding: 8, textAlign: 'left' }}>Маркетплейс</th>
                    <th style={{ padding: 8, textAlign: 'left' }}>ID карточки</th>
                    <th style={{ padding: 8, textAlign: 'left' }}>Артикул продавца</th>
                    <th style={{ padding: 8, textAlign: 'left' }}>Наш SKU</th>
                    <th style={{ padding: 8, textAlign: 'left' }}>Статус</th>
                    <th style={{ padding: 8, textAlign: 'left' }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {mappingDiagnostics.items.map((item) => (
                    <tr key={item.marketplace_product_id} style={{ borderTop: '1px solid #eee' }}>
                      <td style={{ padding: 8 }}>{item.marketplace_code}</td>
                      <td style={{ padding: 8, fontFamily: 'monospace' }}>{item.marketplace_item_id}</td>
                      <td style={{ padding: 8, fontFamily: 'monospace' }}>{item.marketplace_sku || '—'}</td>
                      <td style={{ padding: 8, fontFamily: 'monospace' }}>
                        {item.internal_sku || item.candidate_internal_skus?.join(', ') || '—'}
                      </td>
                      <td style={{ padding: 8 }}>{mappingStatusLabel(item.effective_status)}</td>
                      <td style={{ padding: 8 }}>
                        {item.effective_status === 'proposed' && item.mapping_id ? (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button type="button" onClick={() => setMappingDecision(item.mapping_id as number, 'confirmed')}>
                              Подтвердить
                            </button>
                            <button type="button" onClick={() => setMappingDecision(item.mapping_id as number, 'rejected')}>
                              Отклонить
                            </button>
                          </div>
                        ) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : mappingLoading ? <div>Загрузка связей…</div> : null}
      </section>

      {error && (
        <div style={{ padding: 12, backgroundColor: '#f8d7da', color: '#721c24', borderRadius: 4, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div>Loading...</div>
      ) : products.length === 0 ? (
        <div style={{ padding: 20, textAlign: 'center', color: '#666' }}>
          Нет данных для отображения
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>SKU</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Название</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Категория</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Наличие</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>РРЦ</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Себестоимость</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Статус</th>
                  <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Штрихкод</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => {
                  const isEditing = categoryDropdownOpen === product.internal_sku
                  const categoryName = getCategoryName(product.internal_category_id)
                  return (
                    <tr key={product.id} style={{ borderBottom: '1px solid #dee2e6' }}>
                      <td style={{ padding: 12, border: '1px solid #dee2e6', fontFamily: 'monospace' }}>
                        {product.internal_sku}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6' }}>
                        {product.name || 'N/A'}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6', position: 'relative' }}>
                        {isEditing ? (
                          <div ref={dropdownRef} style={{ position: 'relative', zIndex: 1000 }}>
                            <input
                              type="text"
                              value={categorySearch}
                              onChange={(e) => setCategorySearch(e.target.value)}
                              placeholder="Поиск категории..."
                              style={{
                                width: '100%',
                                padding: '4px 8px',
                                border: '1px solid #ccc',
                                borderRadius: 4,
                                fontSize: 14,
                              }}
                              autoFocus
                            />
                            <div
                              style={{
                                position: 'absolute',
                                top: '100%',
                                left: 0,
                                right: 0,
                                backgroundColor: 'white',
                                border: '1px solid #ccc',
                                borderRadius: 4,
                                maxHeight: 200,
                                overflowY: 'auto',
                                marginTop: 4,
                                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                              }}
                            >
                              <div
                                onClick={() => updateProductCategory(product.internal_sku, null)}
                                style={{
                                  padding: '8px 12px',
                                  cursor: 'pointer',
                                  borderBottom: '1px solid #eee',
                                  backgroundColor: product.internal_category_id === null ? '#e7f3ff' : undefined,
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f0f0f0')}
                                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = product.internal_category_id === null ? '#e7f3ff' : 'white')}
                              >
                                <strong>— Снять категорию</strong>
                              </div>
                              {filteredCategories.map((cat) => (
                                <div
                                  key={cat.id}
                                  onClick={() => updateProductCategory(product.internal_sku, cat.id)}
                                  style={{
                                    padding: '8px 12px',
                                    cursor: 'pointer',
                                    borderBottom: '1px solid #eee',
                                    backgroundColor: product.internal_category_id === cat.id ? '#e7f3ff' : undefined,
                                  }}
                                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f0f0f0')}
                                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = product.internal_category_id === cat.id ? '#e7f3ff' : 'white')}
                                >
                                  <div style={{ fontWeight: 500 }}>{cat.name}</div>
                                  <div style={{ fontSize: 12, color: '#666' }}>{cat.key}</div>
                                </div>
                              ))}
                              {filteredCategories.length === 0 && (
                                <div style={{ padding: '8px 12px', color: '#666', fontStyle: 'italic' }}>
                                  Категории не найдены
                                </div>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div
                            onClick={() => {
                              setCategoryDropdownOpen(product.internal_sku)
                              setCategorySearch('')
                            }}
                            style={{
                              cursor: 'pointer',
                              padding: '4px 8px',
                              borderRadius: 4,
                              border: '1px solid transparent',
                              display: 'inline-block',
                              minWidth: 100,
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.borderColor = '#ccc'
                              e.currentTarget.style.backgroundColor = '#f8f9fa'
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.borderColor = 'transparent'
                              e.currentTarget.style.backgroundColor = 'transparent'
                            }}
                          >
                            {categoryName || '—'}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6', textAlign: 'right' }}>
                        {formatNumber(product.attributes?.stock)}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6', textAlign: 'right' }}>
                        {product.price_rrp ? `${formatNumber(product.price_rrp)} ${product.price_currency || ''}`.trim() : 'N/A'}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6', textAlign: 'right' }}>
                        {product.cost ? `${formatNumber(product.cost)} ${product.cost_currency || ''}`.trim() : 'N/A'}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6' }}>
                        {product.lifecycle_status || 'N/A'}
                      </td>
                      <td style={{ padding: 12, border: '1px solid #dee2e6', fontFamily: 'monospace' }}>
                        {product.attributes?.barcode || 'N/A'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              style={{
                padding: '8px 16px',
                backgroundColor: page === 1 ? '#ccc' : '#0d6efd',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: page === 1 ? 'not-allowed' : 'pointer',
              }}
            >
              Предыдущая
            </button>
            <span>
              Страница {page} из {Math.ceil(total / pageSize)} (Всего: {total})
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={page * pageSize >= total}
              style={{
                padding: '8px 16px',
                backgroundColor: page * pageSize >= total ? '#ccc' : '#0d6efd',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                cursor: page * pageSize >= total ? 'not-allowed' : 'pointer',
              }}
            >
              Следующая
            </button>
          </div>
        </>
      )}
    </div>
  )
}
