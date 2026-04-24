'use client'

import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import { apiDeleteData, apiGetData, postCategoryBootstrapRun, type CategoryBootstrapStatusResponse } from '@/lib/apiClient'
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

export default function SeoCategoryPage({ params }: { params: { projectId: string; categoryId: string } }) {
  const { projectId, categoryId } = params
  const [corpus, setCorpus] = useState<CorpusResponse | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  usePageTitle(`SEO: категория ${categoryId}`, projectId)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiGetData<CorpusResponse>(`/api/v1/projects/${projectId}/wildberries/seo/query-import/corpus?category_id=${categoryId}`)
      setCorpus(data)
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

  const status = corpus?.summary?.readiness_status || corpus?.bootstrap_status?.readiness_status
  return (
    <SeoShell projectId={projectId} title={`Категория ${categoryId}`} subtitle="Корпус запросов и готовность категории к подбору.">
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
