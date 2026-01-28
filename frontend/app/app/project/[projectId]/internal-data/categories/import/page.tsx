'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet } from '../../../../../../../lib/apiClient'
import { getApiBase } from '../../../../../../../lib/api'
import { getAccessToken } from '../../../../../../../lib/auth'

interface CategoryImportResult {
  categories_total: number
  categories_created: number
  categories_updated: number
  products_total_rows: number
  products_updated: number
  missing_sku: string[]
  missing_category: string[]
  errors_first_n: Array<{ type: string; message: string; [key: string]: any }>
}

interface IntrospectResponse {
  detected_format: string
  category_candidates: Array<{ path: string; count: number; sample_attrs: string[] }>
  product_candidates: Array<{ path: string; count: number; sample_attrs: string[] }>
  category_samples: Array<{ tag: string; attributes: Record<string, string>; text: string }>
  product_samples: Array<{ tag: string; attributes: Record<string, string>; text: string; children: string[] }>
  default_mapping: any
}

export default function CategoryImportPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [file, setFile] = useState<File | null>(null)
  const [format, setFormat] = useState<'auto' | 'yml' | '1c'>('auto')
  const [mode, setMode] = useState<'categories_only' | 'categories_and_products'>('categories_and_products')
  const [createMissingCategories, setCreateMissingCategories] = useState(true)
  const [mappingJson, setMappingJson] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [loading, setLoading] = useState(false)
  const [introspectData, setIntrospectData] = useState<IntrospectResponse | null>(null)
  const [result, setResult] = useState<CategoryImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleGetTemplate = async () => {
    try {
      const formatForTemplate = format === 'auto' ? 'yml' : format
      const res = await apiGet(`/api/v1/projects/${projectId}/internal-data/categories/import-xml/mapping-template?format=${formatForTemplate}`)
      setMappingJson(JSON.stringify(res.data, null, 2))
      setShowAdvanced(true)
    } catch (err: any) {
      setError(err?.detail || 'Ошибка загрузки шаблона')
    }
  }

  const handleIntrospect = async () => {
    if (!file) {
      setError('Выберите XML файл')
      return
    }

    try {
      setLoading(true)
      setError(null)
      const formData = new FormData()
      formData.append('file', file)

      const apiBase = getApiBase()
      const token = getAccessToken()
      
      const res = await fetch(`${apiBase}/api/v1/projects/${projectId}/internal-data/categories/import-xml/introspect`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Ошибка интроспекции')
      }

      const data = await res.json()
      setIntrospectData(data)
      setFormat(data.detected_format as 'yml' | '1c')
      if (data.default_mapping) {
        setMappingJson(JSON.stringify(data.default_mapping, null, 2))
        setShowAdvanced(true)
      }
    } catch (err: any) {
      setError(err?.message || 'Ошибка интроспекции')
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    if (!file) {
      setError('Выберите XML файл')
      return
    }

    if (format === '1c' && !mappingJson.trim()) {
      setError('Для формата 1C требуется mapping_json. Используйте интроспекцию или шаблон.')
      return
    }

    try {
      setLoading(true)
      setError(null)
      const formData = new FormData()
      formData.append('file', file)
      if (mappingJson.trim()) {
        formData.append('mapping_json', mappingJson)
      }

      const apiBase = getApiBase()
      const token = getAccessToken()
      
      const url = new URL(`${apiBase}/api/v1/projects/${projectId}/internal-data/categories/import-xml`)
      url.searchParams.set('format', format)
      url.searchParams.set('mode', mode)
      url.searchParams.set('create_missing_categories', String(createMissingCategories))
      url.searchParams.set('on_unknown_sku', 'skip')

      const res = await fetch(url.toString(), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Ошибка импорта')
      }

      const data = await res.json()
      setResult(data)
    } catch (err: any) {
      setError(err?.message || 'Ошибка импорта')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Импорт категорий (XML)</h1>
        <button
          onClick={() => router.push(`/app/project/${projectId}/internal-data/categories`)}
          style={{
            padding: '8px 16px',
            backgroundColor: '#6c757d',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          Назад к категориям
        </button>
      </div>

      {error && (
        <div style={{ padding: 12, backgroundColor: '#f8d7da', color: '#721c24', borderRadius: 4, marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 800 }}>
        <div>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>XML файл</label>
          <input
            type="file"
            accept=".xml"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            style={{
              padding: '8px 12px',
              border: '1px solid #ccc',
              borderRadius: 4,
              fontSize: 14,
              width: '100%',
            }}
          />
        </div>

        <div>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>Формат</label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as 'auto' | 'yml' | '1c')}
            style={{
              padding: '8px 12px',
              border: '1px solid #ccc',
              borderRadius: 4,
              fontSize: 14,
              width: '100%',
            }}
          >
            <option value="auto">Автоопределение</option>
            <option value="yml">YML (Yandex Market)</option>
            <option value="1c">1C XML</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={handleGetTemplate}
            disabled={loading}
            style={{
              padding: '8px 16px',
              backgroundColor: '#0d6efd',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            Получить шаблон
          </button>
          <button
            onClick={handleIntrospect}
            disabled={loading || !file}
            style={{
              padding: '8px 16px',
              backgroundColor: '#17a2b8',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              cursor: loading || !file ? 'not-allowed' : 'pointer',
            }}
          >
            Интроспекция XML
          </button>
        </div>

        {introspectData && (
          <div style={{ padding: 16, backgroundColor: '#f8f9fa', borderRadius: 4 }}>
            <h3 style={{ marginTop: 0 }}>Результаты интроспекции</h3>
            <p><strong>Определённый формат:</strong> {introspectData.detected_format}</p>
            {introspectData.category_candidates.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <strong>Найденные категории:</strong>
                <ul>
                  {introspectData.category_candidates.map((cand, idx) => (
                    <li key={idx}>
                      {cand.path} ({cand.count} элементов)
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {introspectData.product_candidates.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <strong>Найденные товары:</strong>
                <ul>
                  {introspectData.product_candidates.map((cand, idx) => (
                    <li key={idx}>
                      {cand.path} ({cand.count} элементов)
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showAdvanced}
              onChange={(e) => setShowAdvanced(e.target.checked)}
            />
            <span>Показать/редактировать mapping_json</span>
          </label>
        </div>

        {showAdvanced && (
          <div>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>mapping_json</label>
            <textarea
              value={mappingJson}
              onChange={(e) => setMappingJson(e.target.value)}
              rows={15}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #ccc',
                borderRadius: 4,
                fontSize: 14,
                fontFamily: 'monospace',
              }}
              placeholder='{"format": "yml", "categories": {...}, "products": {...}}'
            />
          </div>
        )}

        <div>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>Режим импорта</label>
          <div style={{ display: 'flex', gap: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="radio"
                checked={mode === 'categories_only'}
                onChange={() => setMode('categories_only')}
              />
              <span>Только категории</span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="radio"
                checked={mode === 'categories_and_products'}
                onChange={() => setMode('categories_and_products')}
              />
              <span>Категории и товары</span>
            </label>
          </div>
        </div>

        <div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={createMissingCategories}
              onChange={(e) => setCreateMissingCategories(e.target.checked)}
            />
            <span>Создавать отсутствующие категории</span>
          </label>
        </div>

        <button
          onClick={handleImport}
          disabled={loading || !file}
          style={{
            padding: '12px 24px',
            backgroundColor: loading || !file ? '#ccc' : '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            cursor: loading || !file ? 'not-allowed' : 'pointer',
            fontSize: 16,
            fontWeight: 500,
          }}
        >
          {loading ? 'Импорт...' : 'Импорт'}
        </button>

        {result && (
          <div style={{ padding: 16, backgroundColor: '#d4edda', borderRadius: 4 }}>
            <h3 style={{ marginTop: 0 }}>Результаты импорта</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <strong>Категории:</strong>
                <ul style={{ margin: '8px 0', paddingLeft: 20 }}>
                  <li>Всего найдено: {result.categories_total}</li>
                  <li>Создано: {result.categories_created}</li>
                  <li>Обновлено: {result.categories_updated}</li>
                </ul>
              </div>
              <div>
                <strong>Товары:</strong>
                <ul style={{ margin: '8px 0', paddingLeft: 20 }}>
                  <li>Всего найдено: {result.products_total_rows}</li>
                  <li>Обновлено: {result.products_updated}</li>
                  {result.missing_sku.length > 0 && (
                    <li style={{ color: '#dc3545' }}>Не найдено SKU: {result.missing_sku.length}</li>
                  )}
                  {result.missing_category.length > 0 && (
                    <li style={{ color: '#dc3545' }}>Не найдено категорий: {result.missing_category.length}</li>
                  )}
                </ul>
              </div>
            </div>

            {result.errors_first_n.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <strong>Ошибки (первые {result.errors_first_n.length}):</strong>
                <ul style={{ margin: '8px 0', paddingLeft: 20, maxHeight: 200, overflowY: 'auto' }}>
                  {result.errors_first_n.map((err, idx) => (
                    <li key={idx} style={{ color: '#dc3545' }}>
                      {err.type}: {err.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
