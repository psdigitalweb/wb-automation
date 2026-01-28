'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPost, apiPatch, apiDelete } from '../../../../../../lib/apiClient'

interface InternalCategory {
  id: number
  key: string
  name: string
  parent_id: number | null
  meta_json: any
  created_at: string
  updated_at: string
}

interface CategoriesResponse {
  total: number
  items: InternalCategory[]
}

export default function CategoriesPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [categories, setCategories] = useState<InternalCategory[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [parentFilter, setParentFilter] = useState<'all' | 'root' | number>('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [createKey, setCreateKey] = useState('')
  const [createName, setCreateName] = useState('')
  const [createParentId, setCreateParentId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    loadCategories()
  }, [projectId, searchQuery, parentFilter])

  const loadCategories = async () => {
    try {
      setLoading(true)
      setError(null)
      let url = `/api/v1/projects/${projectId}/internal-data/categories?limit=500&offset=0`
      if (searchQuery) {
        url += `&q=${encodeURIComponent(searchQuery)}`
      }
      if (parentFilter === 'root') {
        url += `&parent_id=null`
      } else if (typeof parentFilter === 'number') {
        url += `&parent_id=${parentFilter}`
      }
      const result = await apiGet<CategoriesResponse>(url)
      setCategories(result.data.items)
      setTotal(result.data.total)
    } catch (err: any) {
      console.error('Failed to load categories:', err)
      setError(err?.detail || 'Ошибка загрузки категорий')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    try {
      await apiPost(`/api/v1/projects/${projectId}/internal-data/categories`, {
        key: createKey,
        name: createName,
        parent_id: createParentId,
      })
      setShowCreateModal(false)
      setCreateKey('')
      setCreateName('')
      setCreateParentId(null)
      setToast('Категория создана')
      setTimeout(() => setToast(null), 3000)
      loadCategories()
    } catch (err: any) {
      console.error('Failed to create category:', err)
      alert(err?.detail || 'Ошибка создания категории')
    }
  }

  const handleUpdate = async (id: number) => {
    try {
      await apiPatch(`/api/v1/projects/${projectId}/internal-data/categories/${id}`, {
        name: editName,
      })
      setEditingId(null)
      setEditName('')
      setToast('Категория обновлена')
      setTimeout(() => setToast(null), 3000)
      loadCategories()
    } catch (err: any) {
      console.error('Failed to update category:', err)
      alert(err?.detail || 'Ошибка обновления категории')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Удалить категорию? Товары потеряют связь с этой категорией.')) {
      return
    }
    try {
      await apiDelete(`/api/v1/projects/${projectId}/internal-data/categories/${id}`)
      setToast('Категория удалена')
      setTimeout(() => setToast(null), 3000)
      loadCategories()
    } catch (err: any) {
      console.error('Failed to delete category:', err)
      if (err?.status === 404) {
        alert('Категория не найдена')
      } else {
        alert(err?.detail || 'Ошибка удаления категории')
      }
    }
  }

  const getCategoryName = (id: number | null) => {
    if (!id) return null
    const cat = categories.find((c) => c.id === id)
    return cat ? cat.name : null
  }

  const rootCategories = categories.filter((c) => c.parent_id === null)

  return (
    <div className="container">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Категории (Internal Data)</h1>
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={() => router.push(`/app/project/${projectId}/internal-data`)}
            style={{
              padding: '8px 16px',
              backgroundColor: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Назад к товарам
          </button>
          <button
            onClick={() => router.push(`/app/project/${projectId}/internal-data/categories/import`)}
            style={{
              padding: '8px 16px',
              backgroundColor: '#17a2b8',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Импорт категорий (XML)
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            style={{
              padding: '8px 16px',
              backgroundColor: '#0d6efd',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            Создать категорию
          </button>
        </div>
      </div>

      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 20,
            right: 20,
            padding: '12px 20px',
            backgroundColor: '#28a745',
            color: 'white',
            borderRadius: 4,
            zIndex: 1000,
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          }}
        >
          {toast}
        </div>
      )}

      <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Поиск по названию или ключу..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #ccc',
            borderRadius: 4,
            fontSize: 14,
            minWidth: 250,
          }}
        />
        <select
          value={parentFilter === 'all' ? 'all' : parentFilter === 'root' ? 'root' : String(parentFilter)}
          onChange={(e) => {
            const val = e.target.value
            if (val === 'all') setParentFilter('all')
            else if (val === 'root') setParentFilter('root')
            else setParentFilter(Number(val))
          }}
          style={{
            padding: '8px 12px',
            border: '1px solid #ccc',
            borderRadius: 4,
            fontSize: 14,
          }}
        >
          <option value="all">Все категории</option>
          <option value="root">Только корневые</option>
          {rootCategories.map((cat) => (
            <option key={cat.id} value={cat.id}>
              Дети: {cat.name}
            </option>
          ))}
        </select>
        <span style={{ color: '#666', fontSize: 14 }}>Всего: {total}</span>
      </div>

      {error && (
        <div style={{ padding: 12, backgroundColor: '#f8d7da', color: '#721c24', borderRadius: 4, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div>Loading...</div>
      ) : categories.length === 0 ? (
        <div style={{ padding: 20, textAlign: 'center', color: '#666' }}>Нет категорий</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ backgroundColor: '#f8f9fa', borderBottom: '2px solid #dee2e6' }}>
                <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>ID</th>
                <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Ключ</th>
                <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Название</th>
                <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Родитель</th>
                <th style={{ padding: 12, textAlign: 'left', border: '1px solid #dee2e6' }}>Действия</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((category) => (
                <tr key={category.id} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={{ padding: 12, border: '1px solid #dee2e6' }}>{category.id}</td>
                  <td style={{ padding: 12, border: '1px solid #dee2e6', fontFamily: 'monospace' }}>
                    {category.key}
                  </td>
                  <td style={{ padding: 12, border: '1px solid #dee2e6' }}>
                    {editingId === category.id ? (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          style={{
                            padding: '4px 8px',
                            border: '1px solid #ccc',
                            borderRadius: 4,
                            fontSize: 14,
                            flex: 1,
                          }}
                          autoFocus
                        />
                        <button
                          onClick={() => handleUpdate(category.id)}
                          style={{
                            padding: '4px 12px',
                            backgroundColor: '#28a745',
                            color: 'white',
                            border: 'none',
                            borderRadius: 4,
                            cursor: 'pointer',
                            fontSize: 12,
                          }}
                        >
                          Сохранить
                        </button>
                        <button
                          onClick={() => {
                            setEditingId(null)
                            setEditName('')
                          }}
                          style={{
                            padding: '4px 12px',
                            backgroundColor: '#6c757d',
                            color: 'white',
                            border: 'none',
                            borderRadius: 4,
                            cursor: 'pointer',
                            fontSize: 12,
                          }}
                        >
                          Отмена
                        </button>
                      </div>
                    ) : (
                      <span
                        onClick={() => {
                          setEditingId(category.id)
                          setEditName(category.name)
                        }}
                        style={{ cursor: 'pointer', textDecoration: 'underline' }}
                      >
                        {category.name}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: 12, border: '1px solid #dee2e6' }}>
                    {getCategoryName(category.parent_id) || '—'}
                  </td>
                  <td style={{ padding: 12, border: '1px solid #dee2e6' }}>
                    <button
                      onClick={() => handleDelete(category.id)}
                      style={{
                        padding: '4px 12px',
                        backgroundColor: '#dc3545',
                        color: 'white',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer',
                        fontSize: 12,
                      }}
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreateModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2000,
          }}
          onClick={() => setShowCreateModal(false)}
        >
          <div
            style={{
              backgroundColor: 'white',
              padding: 24,
              borderRadius: 8,
              maxWidth: 500,
              width: '90%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0 }}>Создать категорию</h2>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Ключ (уникальный)</label>
              <input
                type="text"
                value={createKey}
                onChange={(e) => setCreateKey(e.target.value)}
                placeholder="category-key"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ccc',
                  borderRadius: 4,
                  fontSize: 14,
                }}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Название</label>
              <input
                type="text"
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="Название категории"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ccc',
                  borderRadius: 4,
                  fontSize: 14,
                }}
              />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>Родительская категория (опционально)</label>
              <select
                value={createParentId === null ? '' : String(createParentId)}
                onChange={(e) => setCreateParentId(e.target.value ? Number(e.target.value) : null)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #ccc',
                  borderRadius: 4,
                  fontSize: 14,
                }}
              >
                <option value="">— Нет родителя</option>
                {rootCategories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button
                onClick={() => {
                  setShowCreateModal(false)
                  setCreateKey('')
                  setCreateName('')
                  setCreateParentId(null)
                }}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: 4,
                  cursor: 'pointer',
                }}
              >
                Отмена
              </button>
              <button
                onClick={handleCreate}
                disabled={!createKey || !createName}
                style={{
                  padding: '8px 16px',
                  backgroundColor: !createKey || !createName ? '#ccc' : '#0d6efd',
                  color: 'white',
                  border: 'none',
                  borderRadius: 4,
                  cursor: !createKey || !createName ? 'not-allowed' : 'pointer',
                }}
              >
                Создать
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
