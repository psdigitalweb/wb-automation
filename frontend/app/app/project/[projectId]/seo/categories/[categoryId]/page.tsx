'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import { apiDeleteData, apiGetData, apiPutData, postCategoryBootstrapRun, type CategoryBootstrapStatusResponse } from '@/lib/apiClient'
import { getAccessToken } from '@/lib/auth'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../../_components/SeoShell'

interface CorpusBatch {
  batch_id: number
  original_filename: string | null
  status: string
  raw_rows?: number
  normalized_rows?: number
  created_at: string | null
}

interface CorpusResponse {
  category_id: number
  summary: {
    active_batches_count: number
    total_batches_count: number
    total_raw_rows: number
    total_normalized_rows: number
    unique_normalized_queries: number
    duplicate_across_batches_count: number
    readiness_status: string | null
  }
  batches: CorpusBatch[]
  bootstrap_status?: CategoryBootstrapStatusResponse | null
}

interface QueryDataStatusResponse {
  project_id: number
  category_id: number
  query_count: number
  normalized_query_count: number
  cluster_count: number
  latest_batch: {
    batch_id: number
    status: string
    original_filename: string | null
    created_at: string
    updated_at: string
  } | null
  expressive_prior: {
    ready: boolean
    status: string | null
    source: string | null
    schema_version: string | null
    axes_id: number | null
    llm_model: string | null
    prompt_version: string | null
    updated_at: string | null
    confidence: Record<string, number>
    evidence_refs: string[]
    expressive_axes: string[]
    audience_axes: string[]
    occasion_axes: string[]
    use_case_axes: string[]
    product_type_axes: string[]
    attribute_axes: string[]
    constraint_axes: string[]
    negative_constraint_axes: string[]
  }
  review_archive: {
    source_table: string
    category_join: string
    total_review_rows: number
    text_review_rows: number
    sku_with_reviews: number
    sku_with_text_reviews: number
    rating_positive_rows: number
  }
  readiness: {
    query_data_loaded: boolean
    normalized_queries_ready: boolean
    clusters_ready: boolean
    expressive_prior_ready: boolean
    ready: boolean
  }
}

interface ClusterItem {
  cluster_id: number
  cluster_key: string
  label: string | null
  top_query: string | null
  query_count: number
  top_frequency: string | null
}

interface ClusterListResponse {
  project_id: number
  category_id: number
  total: number
  limit: number
  offset: number
  items: ClusterItem[]
}

interface ClusterDetailResponse {
  project_id: number
  category_id: number
  cluster: ClusterItem
  queries: Array<{
    normalized_query_text: string
    display_query: string | null
    frequency_total: string | null
    ranking_value_used: string
    query_type: string
    membership_reason_code: string
  }>
}

interface CategorySelectedQueriesResponse {
  project_id: number
  category_id: number
  total: number
  items: Array<{
    id: number
    query_text: string
    sort_order: number
    created_at: string | null
    updated_at: string | null
  }>
}

async function parseError(res: Response) {
  const text = await res.text()
  try {
    return JSON.parse(text)?.detail || text
  } catch {
    return text || `HTTP ${res.status}`
  }
}

function tone(status?: string | null): 'good' | 'warn' | 'bad' | 'neutral' {
  if (status === 'ready_for_matching') return 'good'
  if (status === 'ready_with_fallback' || status === 'building') return 'warn'
  if (status === 'failed') return 'bad'
  return 'neutral'
}

function label(status?: string | null) {
  if (status === 'ready_for_matching') return 'Готова к подбору'
  if (status === 'ready_with_fallback') return 'Можно использовать, но качество ниже'
  if (status === 'building') return 'Обрабатывается'
  return 'Нужно действие'
}

function formatCount(value?: number | null) {
  return (value ?? 0).toLocaleString('ru-RU')
}

function readinessLabel(value: boolean) {
  return value ? 'Готово' : 'Не готово'
}

function compactList(items: string[] | undefined, limit = 24) {
  const values = (items || []).filter(Boolean)
  return {
    visible: values.slice(0, limit),
    remaining: Math.max(values.length - limit, 0),
  }
}

function AxisList({ title, items, empty = 'Нет данных' }: { title: string; items?: string[]; empty?: string }) {
  const { visible, remaining } = compactList(items)
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
      <div style={{ fontWeight: 800, marginBottom: 8 }}>{title}</div>
      {visible.length ? (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {visible.map((item) => (
            <span key={`${title}-${item}`} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 999, padding: '5px 9px', fontSize: 13 }}>
              {item}
            </span>
          ))}
          {remaining > 0 && <span style={{ color: '#64748b', padding: '5px 0' }}>и ещё {remaining}</span>}
        </div>
      ) : (
        <div style={{ color: '#64748b' }}>{empty}</div>
      )}
    </div>
  )
}

function sourceSummary(prior?: QueryDataStatusResponse['expressive_prior']) {
  const refs = prior?.evidence_refs || []
  if (refs.includes('reviews') && refs.length > 1) return 'Система собрала смыслы из запросов, товаров, отзывов и общего профиля категории'
  if (refs.includes('reviews')) return 'Источник: отзывы'
  if (prior?.source === 'llm_enhanced') return 'Источник: LLM-enhanced prior'
  return 'Источник: deterministic/category meaning'
}

export default function SeoCategoryPage({ params }: { params: { projectId: string; categoryId: string } }) {
  const { projectId, categoryId } = params
  const [corpus, setCorpus] = useState<CorpusResponse | null>(null)
  const [categoryName, setCategoryName] = useState<string | null>(null)
  const [queryDataStatus, setQueryDataStatus] = useState<QueryDataStatusResponse | null>(null)
  const [clusters, setClusters] = useState<ClusterListResponse | null>(null)
  const [selectedQueries, setSelectedQueries] = useState<CategorySelectedQueriesResponse | null>(null)
  const [selectedQueriesText, setSelectedQueriesText] = useState('')
  const [selectedQueriesSaving, setSelectedQueriesSaving] = useState(false)
  const [expandedClusterId, setExpandedClusterId] = useState<number | null>(null)
  const [clusterDetails, setClusterDetails] = useState<Record<number, ClusterDetailResponse>>({})
  const [clusterLoadingId, setClusterLoadingId] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const categoryTitle = categoryName || 'Категория'
  usePageTitle(`SEO: ${categoryTitle}`, projectId)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [corpusData, statusData, clusterData, selectedData, categoryItems] = await Promise.all([
        apiGetData<CorpusResponse>(`/api/v1/projects/${projectId}/wildberries/seo/query-import/corpus?category_id=${categoryId}`),
        apiGetData<QueryDataStatusResponse>(`/api/v1/projects/${projectId}/seo/categories/${categoryId}/query-data/status`),
        apiGetData<ClusterListResponse>(`/api/v1/projects/${projectId}/seo/categories/${categoryId}/clusters?limit=50`),
        apiGetData<CategorySelectedQueriesResponse>(`/api/v1/projects/${projectId}/seo/categories/${categoryId}/selected-queries`),
        apiGetData<Array<{ category_id: number; category_name: string }>>(`/api/v1/projects/${projectId}/seo/categories`).catch(() => []),
      ])
      setCorpus(corpusData)
      setQueryDataStatus(statusData)
      setClusters(clusterData)
      setSelectedQueries(selectedData)
      setSelectedQueriesText(selectedData.items.map((item) => item.query_text).join('\n'))
      const currentCategory = categoryItems.find((item) => String(item.category_id) === String(categoryId))
      setCategoryName(currentCategory?.category_name || null)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId, categoryId])

  useEffect(() => {
    const status = corpus?.summary?.readiness_status || corpus?.bootstrap_status?.readiness_status
    const runStatus = corpus?.bootstrap_status?.run_status
    const isBuilding = status === 'building' || runStatus === 'running' || runStatus === 'pending'
    if (!isBuilding) return
    const timer = setInterval(() => {
      load()
    }, 3000)
    return () => clearInterval(timer)
  }, [corpus?.summary?.readiness_status, corpus?.bootstrap_status?.readiness_status, corpus?.bootstrap_status?.run_status])

  const upload = async () => {
    if (!file) return setError('Выберите CSV файл.')
    setLoading(true)
    setError(null)
    setInfo(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('category_id', categoryId)
      const token = getAccessToken()
      const res = await fetch(`/api/v1/projects/${projectId}/wildberries/seo/query-import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })
      if (!res.ok) throw new Error(await parseError(res))
      setFile(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      setInfo('CSV загружен. Обработка категории запущена в фоне.')
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const rerun = async () => {
    setLoading(true)
    setError(null)
    try {
      await postCategoryBootstrapRun(projectId, { category_id: Number(categoryId), force_refresh: true, use_llm: true })
      setInfo('Повторная обработка запущена.')
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const deleteBatch = async (batchId: number) => {
    if (!window.confirm(`Удалить файл #${batchId}?`)) return
    setLoading(true)
    try {
      await apiDeleteData(`/api/v1/projects/${projectId}/wildberries/seo/query-import/batches/${batchId}`)
      setInfo('Файл удален. Категория будет пересобрана по оставшимся CSV.')
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const clear = async () => {
    const expected = `CLEAR ${categoryId}`
    if (window.prompt(`Введите "${expected}", чтобы очистить запросы категории.`) !== expected) return
    setLoading(true)
    try {
      await apiDeleteData(`/api/v1/projects/${projectId}/wildberries/seo/query-import/category?category_id=${categoryId}`)
      setInfo('Запросы категории очищены.')
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const toggleCluster = async (clusterId: number) => {
    if (expandedClusterId === clusterId) {
      setExpandedClusterId(null)
      return
    }
    setExpandedClusterId(clusterId)
    if (clusterDetails[clusterId]) return
    setClusterLoadingId(clusterId)
    setError(null)
    try {
      const detail = await apiGetData<ClusterDetailResponse>(
        `/api/v1/projects/${projectId}/seo/categories/${categoryId}/clusters/${clusterId}?limit=100`
      )
      setClusterDetails((current) => ({ ...current, [clusterId]: detail }))
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setClusterLoadingId(null)
    }
  }

  const saveSelectedQueries = async () => {
    setSelectedQueriesSaving(true)
    setError(null)
    setInfo(null)
    try {
      const queries = selectedQueriesText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      const saved = await apiPutData<CategorySelectedQueriesResponse>(
        `/api/v1/projects/${projectId}/seo/categories/${categoryId}/selected-queries`,
        { queries },
      )
      setSelectedQueries(saved)
      setSelectedQueriesText(saved.items.map((item) => item.query_text).join('\n'))
      setInfo(`Список запросов категории сохранён: ${saved.total}.`)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setSelectedQueriesSaving(false)
    }
  }

  const status = corpus?.summary?.readiness_status || corpus?.bootstrap_status?.readiness_status
  const readiness = queryDataStatus?.readiness
  const expressivePrior = queryDataStatus?.expressive_prior
  const reviewArchive = queryDataStatus?.review_archive
  const confidenceText = expressivePrior?.confidence
    ? Object.entries(expressivePrior.confidence).map(([key, value]) => `${key}: ${value}`).join(' · ')
    : ''
  return (
    <SeoShell projectId={projectId} title={categoryTitle} subtitle="Корпус запросов и готовность категории к подбору.">
      <div style={{ display: 'grid', gap: 16 }}>
        {error && <Card><div style={{ color: '#b91c1c' }}>{error}</div></Card>}
        {info && <Card><div style={{ color: '#047857' }}>{info}</div></Card>}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <StatusPill label={label(status)} tone={tone(status)} />
              <div style={{ marginTop: 12, color: '#64748b' }}>
                {corpus ? `${corpus.summary.active_batches_count} CSV · ${corpus.summary.unique_normalized_queries} уникальных запросов` : 'Нет данных корпуса'}
              </div>
            </div>
            <button type="button" onClick={rerun} disabled={loading} style={buttonStyle('light')}>Повторить обработку</button>
          </div>
          <details style={{ marginTop: 14 }}>
            <summary>Техническая диагностика</summary>
            <pre style={{ overflow: 'auto' }}>{JSON.stringify(corpus?.bootstrap_status || corpus, null, 2)}</pre>
          </details>
        </Card>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div>
              <h2 style={{ margin: 0 }}>Загруженные данные</h2>
            </div>
            <StatusPill
              label={readiness?.ready ? 'Ready' : 'Not ready'}
              tone={readiness?.ready ? 'good' : 'warn'}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginTop: 16 }}>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>Загружено запросов</div>
              <strong style={{ fontSize: 24 }}>{formatCount(queryDataStatus?.query_count)}</strong>
            </div>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>Кластеры</div>
              <strong style={{ fontSize: 24 }}>{formatCount(queryDataStatus?.cluster_count)}</strong>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10, marginTop: 14 }}>
            <StatusPill label={`Query data: ${readinessLabel(Boolean(readiness?.query_data_loaded))}`} tone={readiness?.query_data_loaded ? 'good' : 'neutral'} />
            <StatusPill label={`Normalization: ${readinessLabel(Boolean(readiness?.normalized_queries_ready))}`} tone={readiness?.normalized_queries_ready ? 'good' : 'neutral'} />
            <StatusPill label={`Clusters: ${readinessLabel(Boolean(readiness?.clusters_ready))}`} tone={readiness?.clusters_ready ? 'good' : 'neutral'} />
          </div>
        </Card>
        <Card>
          <details>
            <summary style={{ cursor: 'pointer', listStyle: 'none' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div>
                  <h2 style={{ margin: '0 0 8px' }}>Что система поняла о категории</h2>
                  <div style={{ color: '#64748b' }}>{sourceSummary(expressivePrior)}</div>
                </div>
                <StatusPill label={expressivePrior?.ready ? 'Данные готовы' : 'Данных пока нет'} tone={expressivePrior?.ready ? 'good' : 'warn'} />
              </div>
            </summary>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, marginTop: 16 }}>
              <AxisList title="Покупательские смыслы" items={expressivePrior?.expressive_axes} />
              <AxisList title="Для кого" items={expressivePrior?.audience_axes} />
              <AxisList title="Поводы" items={expressivePrior?.occasion_axes} />
              <AxisList title="Сценарии" items={expressivePrior?.use_case_axes} />
              <AxisList title="Типы/форматы товара" items={expressivePrior?.product_type_axes} />
              <AxisList title="Атрибуты" items={expressivePrior?.attribute_axes} />
              <AxisList title="Ограничения" items={expressivePrior?.constraint_axes} />
              <AxisList title="Исключения" items={expressivePrior?.negative_constraint_axes} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10, marginTop: 14, color: '#475569' }}>
              <div>Source: <strong>{expressivePrior?.source || 'unknown'}</strong></div>
              <div>Model: <strong>{expressivePrior?.llm_model || 'deterministic'}</strong></div>
              <div>Prompt: <strong>{expressivePrior?.prompt_version || 'unknown'}</strong></div>
              <div>Schema: <strong>{expressivePrior?.schema_version || 'unknown'}</strong></div>
              <div>Confidence: <strong>{confidenceText || 'нет'}</strong></div>
              <div>Evidence refs: <strong>{expressivePrior?.evidence_refs?.join(', ') || 'нет'}</strong></div>
            </div>
          </details>
        </Card>
        <Card>
          <h2 style={{ marginTop: 0 }}>Отзывы товаров категории</h2>
          <div style={{ color: '#64748b', marginBottom: 12 }}>
            Сводка показывает, сколько отзывов доступно системе для анализа смыслов и покупательских сценариев. Тексты отзывов здесь не выводятся.
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>Всего отзывов</div>
              <strong style={{ fontSize: 24 }}>{formatCount(reviewArchive?.total_review_rows)}</strong>
            </div>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>С текстом/pros/cons</div>
              <strong style={{ fontSize: 24 }}>{formatCount(reviewArchive?.text_review_rows)}</strong>
            </div>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>SKU с отзывами</div>
              <strong style={{ fontSize: 24 }}>{formatCount(reviewArchive?.sku_with_reviews)}</strong>
            </div>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>SKU с текстовыми отзывами</div>
              <strong style={{ fontSize: 24 }}>{formatCount(reviewArchive?.sku_with_text_reviews)}</strong>
            </div>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
              <div style={{ color: '#64748b', fontSize: 13 }}>Позитивных оценок</div>
              <strong style={{ fontSize: 24 }}>{formatCount(reviewArchive?.rating_positive_rows)}</strong>
            </div>
          </div>
        </Card>
        <Card>
          <details>
            <summary style={{ cursor: 'pointer', listStyle: 'none' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div>
                  <h2 style={{ margin: '0 0 8px' }}>Запросы, уже выбранные для товаров</h2>
                  <div style={{ color: '#64748b' }}>
                    Список запросов, которые оператор уже сохранял для товаров этой категории. Его можно использовать как базу для похожих товаров.
                  </div>
                </div>
                <StatusPill label={`${selectedQueries?.total || 0} запросов`} tone={selectedQueries?.total ? 'good' : 'neutral'} />
              </div>
            </summary>
            <textarea
              value={selectedQueriesText}
              onChange={(event) => setSelectedQueriesText(event.target.value)}
              placeholder={'кружка капибара\nмилая кружка\nкружка подарок'}
              rows={Math.max(7, Math.min(16, selectedQueriesText.split('\n').length + 2))}
              style={{
                marginTop: 14,
                width: '100%',
                boxSizing: 'border-box',
                border: '1px solid #cbd5e1',
                borderRadius: 8,
                padding: 12,
                font: 'inherit',
                resize: 'vertical',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
              <div style={{ color: '#64748b' }}>Введите или отредактируйте сохранённый список: один поисковый запрос на строку.</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" onClick={() => setSelectedQueriesText('')} disabled={selectedQueriesSaving || !selectedQueriesText.trim()} style={buttonStyle('light')}>
                  Очистить поле
                </button>
                <button type="button" onClick={saveSelectedQueries} disabled={selectedQueriesSaving} style={buttonStyle('primary')}>
                  {selectedQueriesSaving ? 'Сохраняем...' : 'Сохранить список'}
                </button>
              </div>
            </div>
            {selectedQueries?.items.length ? (
              <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
                <div style={{ color: '#64748b', fontWeight: 700 }}>Текущий сохранённый список</div>
                {selectedQueries.items.slice(0, 30).map((item, index) => (
                  <div key={item.id} style={{ display: 'grid', gridTemplateColumns: '44px minmax(0, 1fr)', gap: 10, alignItems: 'center', borderTop: '1px solid #e2e8f0', paddingTop: 8 }}>
                    <span style={{ color: '#64748b', fontVariantNumeric: 'tabular-nums' }}>{index + 1}</span>
                    <strong style={{ overflowWrap: 'anywhere' }}>{item.query_text}</strong>
                  </div>
                ))}
                {selectedQueries.items.length > 30 ? <div style={{ color: '#64748b' }}>И ещё {selectedQueries.items.length - 30} запросов.</div> : null}
              </div>
            ) : null}
          </details>
        </Card>
        <Card>
          <details>
            <summary style={{ cursor: 'pointer', listStyle: 'none' }}>
              <h2 style={{ marginTop: 0, marginBottom: 8 }}>Кластеры запросов</h2>
              <div style={{ color: '#64748b' }}>
                Группы похожих поисковых запросов, которые система построила после загрузки данных.
              </div>
            </summary>
            <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
              {(clusters?.items || []).map((cluster) => {
                const detail = clusterDetails[cluster.cluster_id]
                const isExpanded = expandedClusterId === cluster.cluster_id
                return (
                  <div key={cluster.cluster_id} style={{ borderTop: '1px solid #e2e8f0', paddingTop: 10 }}>
                    <button
                      type="button"
                      onClick={() => toggleCluster(cluster.cluster_id)}
                      style={{ ...buttonStyle('ghost'), width: '100%', justifyContent: 'space-between', textAlign: 'left' }}
                    >
                      <span>
                        #{cluster.cluster_id} · {cluster.label || cluster.top_query || cluster.cluster_key}
                        <span style={{ color: '#64748b', marginLeft: 8 }}>
                          {formatCount(cluster.query_count)} запросов
                          {cluster.top_frequency ? ` · top frequency ${cluster.top_frequency}` : ''}
                        </span>
                      </span>
                      <span>{isExpanded ? 'Свернуть' : 'Раскрыть'}</span>
                    </button>
                    {isExpanded && (
                      <div style={{ marginTop: 10, overflowX: 'auto' }}>
                        {clusterLoadingId === cluster.cluster_id && <div style={{ color: '#64748b' }}>Загружаем запросы...</div>}
                        {detail && (
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                            <thead>
                              <tr style={{ textAlign: 'left', color: '#64748b' }}>
                                <th style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>Запрос</th>
                                <th style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>Частотность</th>
                                <th style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>Вес в подборе</th>
                                <th style={{ padding: '8px 6px', borderBottom: '1px solid #e2e8f0' }}>Тип</th>
                              </tr>
                            </thead>
                            <tbody>
                              {detail.queries.map((query) => (
                                <tr key={`${cluster.cluster_id}-${query.normalized_query_text}`}>
                                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{query.display_query || query.normalized_query_text}</td>
                                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{query.frequency_total || '0'}</td>
                                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{query.ranking_value_used}</td>
                                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #f1f5f9' }}>{query.query_type}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
              {!clusters?.items?.length && <div style={{ color: '#64748b' }}>Кластеры пока не построены.</div>}
            </div>
          </details>
        </Card>
        <Card>
          <h2 style={{ marginTop: 0 }}>Загрузка CSV</h2>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <input ref={fileInputRef} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <button type="button" onClick={upload} disabled={loading || !file} style={buttonStyle('primary')}>Загрузить CSV</button>
            <button type="button" onClick={clear} disabled={loading} style={buttonStyle('danger')}>Очистить запросы категории</button>
          </div>
        </Card>
        <Card>
          <h2 style={{ marginTop: 0 }}>Файлы категории</h2>
          <div style={{ display: 'grid', gap: 10 }}>
            {(corpus?.batches || []).map((batch) => (
              <div key={batch.batch_id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, borderTop: '1px solid #e2e8f0', paddingTop: 10 }}>
                <div>
                  <strong>{batch.original_filename || `batch ${batch.batch_id}`}</strong>
                  <div style={{ color: '#64748b' }}>#{batch.batch_id} · {batch.status}{batch.normalized_rows != null ? ` · ${batch.normalized_rows} строк` : ''}</div>
                </div>
                <button type="button" onClick={() => deleteBatch(batch.batch_id)} style={buttonStyle('light')}>Удалить</button>
              </div>
            ))}
            {!corpus?.batches?.length && <div style={{ color: '#64748b' }}>CSV пока не загружены.</div>}
          </div>
        </Card>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link href={`/app/project/${projectId}/seo/products?category_id=${categoryId}`} style={buttonStyle('primary')}>Перейти к товарам категории</Link>
          <Link href={`/app/project/${projectId}/seo/categories/${categoryId}/eval`} style={buttonStyle('light')}>Открыть eval категории</Link>
        </div>
      </div>
    </SeoShell>
  )
}
