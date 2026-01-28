'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPatch } from '../../../../../lib/apiClient'
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
  const dropdownRef = useRef<HTMLDivElement>(null)
  const pageSize = 100

  useEffect(() => {
    loadProducts()
    loadCategories()
  }, [projectId, page, withStockOnly])

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
          <span>Только товары в наличии (stock > 0)</span>
        </label>
        <span style={{ color: '#666', fontSize: 14 }}>
          Всего: {total} товаров
        </span>
      </div>

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
