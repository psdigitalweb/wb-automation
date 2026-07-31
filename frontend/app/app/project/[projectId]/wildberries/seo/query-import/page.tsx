'use client'

import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import { getApiBase } from '../../../../../../../lib/api'
import {
  apiDeleteData,
  apiGetData,
  ApiError,
  getWBProductSubjects,
  type WBProductSubjectItem,
} from '../../../../../../../lib/apiClient'
import { getAccessToken } from '../../../../../../../lib/auth'

interface SeoQueryImportBatchMeta {
  batch_id: number
  project_id: number
  category_id: number
  status: string
  source_type: string
  source_path: string | null
  original_filename: string | null
  created_at: string
  updated_at: string
  query_column_resolved: string | null
  frequency_column_resolved: string | null
  normalization_version: string | null
}

interface SeoQueryImportNormalizedQueryItem {
  id: number
  normalized_query: string
  display_query: string
  raw_query_example: string
  raw_row_count: number
  frequency_total: string
  normalization_version: string
}

interface SeoQueryImportNormalizedQueryList {
  total: number
  limit: number
  offset: number
  q: string | null
  items: SeoQueryImportNormalizedQueryItem[]
}

interface SeoQueryCorpusSummary {
  project_id: number
  category_id: number
  active_batches_count: number
  total_batches_count: number
  total_raw_rows: number
  total_normalized_rows: number
  unique_normalized_queries: number
  duplicate_across_batches_count: number
  latest_batch_id: number | null
  readiness_status: string | null
  bootstrap_run_id: number | null
  bootstrap_run_status: string | null
}

interface SeoQueryCorpusResponse {
  summary: SeoQueryCorpusSummary
  batches: SeoQueryImportBatchMeta[]
  normalized_queries: SeoQueryImportNormalizedQueryList
}

interface SeoQueryDeleteResponse {
  project_id: number
  category_id: number
  deleted_batch_id: number | null
  action: string
  deleted_counts: Record<string, number>
  preserved_judgments_count: number
  deleted_judgments_count: number
  remaining_active_batches_count: number
  remaining_unique_queries_count: number
  bootstrap_run_id: number | null
  readiness_status: string
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

async function parseErrorResponse(res: Response): Promise<string> {
  const rawText = await res.text()
  if (!rawText) return `HTTP ${res.status}`
  try {
    const parsed = JSON.parse(rawText)
    return parsed?.detail || parsed?.message || rawText
  } catch {
    return rawText
  }
}

function directApiBase(): string {
  const configured = getApiBase()
  if (configured) return configured
  if (typeof window === 'undefined') return ''
  const host = window.location.hostname || 'localhost'
  if (host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0') {
    return 'http://127.0.0.1:8000'
  }
  return ''
}

function statusStyle(status: string | null | undefined): CSSProperties {
  const value = String(status || 'not_started')
  const color =
    value === 'ready_for_matching'
      ? '#0f766e'
      : value === 'ready_with_fallback'
        ? '#92400e'
        : value === 'building'
          ? '#1d4ed8'
          : value === 'failed'
            ? '#b91c1c'
            : '#475569'
  return { color, fontWeight: 700 }
}

export default function SeoQueryImportDebugPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [categoryId, setCategoryId] = useState(searchParams.get('category_id') || '')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [corpus, setCorpus] = useState<SeoQueryCorpusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [subjects, setSubjects] = useState<WBProductSubjectItem[]>([])
  const [subjectsLoading, setSubjectsLoading] = useState(false)
  const [subjectsError, setSubjectsError] = useState<string | null>(null)
  const [querySearch, setQuerySearch] = useState(searchParams.get('q') || '')
  const lastAutoLoadedCategoryRef = useRef<string | null>(null)

  useEffect(() => {
    const next = searchParams.get('category_id') || ''
    setCategoryId((prev) => (prev === next ? prev : next))
    setQuerySearch((prev) => (prev === (searchParams.get('q') || '') ? prev : searchParams.get('q') || ''))
  }, [searchParams])

  useEffect(() => {
    const nextCategoryId = categoryId.trim()
    const paramsObj = new URLSearchParams(searchParams.toString())
    if (nextCategoryId) {
      paramsObj.set('category_id', nextCategoryId)
    } else {
      paramsObj.delete('category_id')
    }
    const trimmedSearch = querySearch.trim()
    if (trimmedSearch) {
      paramsObj.set('q', trimmedSearch)
    } else {
      paramsObj.delete('q')
    }
    const nextQuery = paramsObj.toString()
    const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname
    const currentUrl = searchParams.toString() ? `${pathname}?${searchParams.toString()}` : pathname
    if (nextUrl !== currentUrl) {
      router.replace(nextUrl, { scroll: false })
    }
  }, [categoryId, pathname, querySearch, router, searchParams])

  const loadCorpus = async (successMessage?: string, offset = 0) => {
    const trimmedCategoryId = categoryId.trim()
    if (!trimmedCategoryId) {
      setError('Category ID is required.')
      return
    }
    setLoading(true)
    setError(null)
    if (successMessage) setInfo(null)
    try {
      const qs = new URLSearchParams()
      qs.set('category_id', trimmedCategoryId)
      qs.set('limit', '100')
      qs.set('offset', String(offset))
      const trimmedSearch = querySearch.trim()
      if (trimmedSearch) qs.set('q', trimmedSearch)
      const data = await apiGetData<SeoQueryCorpusResponse>(
        `/api/v1/projects/${projectId}/wildberries/seo/query-import/corpus?${qs.toString()}`
      )
      lastAutoLoadedCategoryRef.current = trimmedCategoryId
      setCorpus(data)
      if (successMessage) setInfo(successMessage)
    } catch (e: any) {
      const err = e as ApiError
      setError(err.detail || 'Failed to load query corpus.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const initialCategory = searchParams.get('category_id')
    if (!initialCategory || !/^\d+$/.test(initialCategory)) return
    if (lastAutoLoadedCategoryRef.current === initialCategory) return
    void loadCorpus(`Loaded query corpus for category ${initialCategory}.`)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, searchParams])

  useEffect(() => {
    const readiness = corpus?.summary.readiness_status
    const runStatus = corpus?.summary.bootstrap_run_status
    const shouldPoll =
      readiness === 'building' ||
      runStatus === 'queued' ||
      runStatus === 'running'
    if (!shouldPoll || loading) return

    const timer = window.setTimeout(() => {
      void loadCorpus(undefined, corpus?.normalized_queries.offset || 0)
    }, 5000)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    corpus?.summary.readiness_status,
    corpus?.summary.bootstrap_run_status,
    corpus?.normalized_queries.offset,
    loading,
  ])

  const handleImport = async () => {
    const trimmedCategoryId = categoryId.trim()
    if (!trimmedCategoryId) {
      setError('Category ID is required.')
      return
    }
    if (!selectedFile) {
      setError('CSV file is required.')
      return
    }

    setLoading(true)
    setError(null)
    setInfo(null)
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('category_id', trimmedCategoryId)
      formData.append('limit', '100')
      formData.append('offset', '0')

      const token = getAccessToken()
      const res = await fetch(`${directApiBase()}/api/v1/projects/${projectId}/wildberries/seo/query-import`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })

      if (!res.ok) throw new Error(await parseErrorResponse(res))
      const data = await res.json()
      setSelectedFile(null)
      await loadCorpus(
        data.bootstrap_run_id
          ? `Imported CSV into batch #${data.batch.batch_id}. Bootstrap queued as run #${data.bootstrap_run_id}.`
          : `Imported CSV into batch #${data.batch.batch_id}.`
      )
    } catch (e: any) {
      setError(e?.message || 'Failed to import CSV.')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteBatch = async (batch: SeoQueryImportBatchMeta) => {
    const confirmed = window.confirm(
      `Delete batch #${batch.batch_id}${batch.original_filename ? ` (${batch.original_filename})` : ''}? Query-derived SEO state for category ${batch.category_id} will be rebuilt.`
    )
    if (!confirmed) return
    setLoading(true)
    setError(null)
    setInfo(null)
    try {
      const result = await apiDeleteData<SeoQueryDeleteResponse>(
        `/api/v1/projects/${projectId}/wildberries/seo/query-import/batches/${batch.batch_id}`
      )
      await loadCorpus(
        result.bootstrap_run_id
          ? `Deleted batch #${batch.batch_id}. Bootstrap queued as run #${result.bootstrap_run_id}.`
          : `Deleted batch #${batch.batch_id}.`
      )
    } catch (e: any) {
      const err = e as ApiError
      setError(err.detail || 'Failed to delete batch.')
    } finally {
      setLoading(false)
    }
  }

  const handleClearCategory = async () => {
    const trimmedCategoryId = categoryId.trim()
    if (!trimmedCategoryId) {
      setError('Category ID is required.')
      return
    }
    const expected = `CLEAR ${trimmedCategoryId}`
    const value = window.prompt(`Type "${expected}" to clear query corpus for category ${trimmedCategoryId}.`)
    if (value !== expected) return
    setLoading(true)
    setError(null)
    setInfo(null)
    try {
      await apiDeleteData<SeoQueryDeleteResponse>(
        `/api/v1/projects/${projectId}/wildberries/seo/query-import/category?category_id=${trimmedCategoryId}`
      )
      await loadCorpus(`Cleared query corpus for category ${trimmedCategoryId}.`)
    } catch (e: any) {
      const err = e as ApiError
      setError(err.detail || 'Failed to clear query corpus.')
    } finally {
      setLoading(false)
    }
  }

  const handlePageChange = async (nextOffset: number) => {
    await loadCorpus(undefined, nextOffset)
  }

  const handleLoadSubjects = async () => {
    setSubjectsLoading(true)
    setSubjectsError(null)
    try {
      const items = await getWBProductSubjects(projectId)
      setSubjects(items)
      if (items.length === 0) setSubjectsError('No WB categories found for this project yet.')
    } catch (e: any) {
      const err = e as ApiError
      setSubjects([])
      setSubjectsError(err.detail || 'Failed to load project categories.')
    } finally {
      setSubjectsLoading(false)
    }
  }

  const normalized = corpus?.normalized_queries
  const canGoPrev = !!normalized && normalized.offset > 0
  const canGoNext = !!normalized && normalized.offset + normalized.limit < normalized.total

  return (
    <div className="container">
      <div style={{ marginBottom: 20 }}>
        <Link href={`/app/project/${projectId}/wildberries`}>
          <button type="button">Back to Wildberries</button>
        </Link>
      </div>

      <h1>WB SEO Query Corpus</h1>
      <p style={{ color: '#666', marginBottom: 20 }}>
        Internal debug page for multi-batch WB frequency CSV import, corpus QA, and destructive cleanup.
      </p>

      {error && (
        <div style={{ padding: 12, backgroundColor: '#f8d7da', color: '#721c24', borderRadius: 6, marginBottom: 16, border: '1px solid #f1aeb5' }}>
          {error}
        </div>
      )}

      {info && (
        <div style={{ padding: 12, backgroundColor: '#d1e7dd', color: '#0f5132', borderRadius: 6, marginBottom: 16, border: '1px solid #a3cfbb' }}>
          {info}
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h2 style={{ marginTop: 0 }}>Controls</h2>
        <div style={{ display: 'grid', gap: 12, maxWidth: 780 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>Project ID</label>
            <input type="text" value={projectId} readOnly style={{ width: '100%' }} />
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>Category ID</label>
            <input
              type="number"
              min={1}
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              placeholder="e.g. 777"
              style={{ width: '100%' }}
            />
          </div>

          <div style={{ padding: 12, border: '1px solid #d8dee4', borderRadius: 6, backgroundColor: '#f8f9fb' }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
              <strong>Project categories helper</strong>
              <button type="button" onClick={handleLoadSubjects} disabled={subjectsLoading}>
                {subjectsLoading ? 'Loading categories...' : 'Load project categories'}
              </button>
            </div>
            {subjectsError && <div style={{ color: '#a94442', marginBottom: subjects.length > 0 ? 10 : 0 }}>{subjectsError}</div>}
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>Select WB category</label>
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              disabled={subjectsLoading || subjects.length === 0}
              style={{ width: '100%' }}
            >
              <option value="">{subjects.length === 0 ? 'Load categories first' : 'Select category'}</option>
              {subjects.map((subject) => (
                <option key={subject.subject_id} value={String(subject.subject_id)}>
                  {subject.subject_name} ({subject.subject_id}, {subject.skus_count} SKU)
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>WB frequency CSV</label>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              style={{ width: '100%' }}
            />
            <div style={{ marginTop: 8, color: '#666', fontSize: 13 }}>
              Multiple CSV files can be imported into the same category corpus. Frequencies are summed by normalized query.
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>Corpus query search</label>
            <input
              type="search"
              value={querySearch}
              onChange={(e) => setQuerySearch(e.target.value)}
              placeholder="normalized query"
              style={{ width: '100%' }}
            />
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button type="button" onClick={() => loadCorpus('Loaded query corpus.')} disabled={loading}>
              {loading ? 'Loading...' : 'Load corpus'}
            </button>
            <button type="button" onClick={handleImport} disabled={loading}>
              {loading ? 'Importing...' : 'Import CSV'}
            </button>
            <button type="button" onClick={handleClearCategory} disabled={loading || !corpus || corpus.summary.total_batches_count === 0} style={{ borderColor: '#b91c1c', color: '#b91c1c' }}>
              Clear query corpus
            </button>
          </div>
        </div>
      </div>

      {corpus && (
        <>
          <div className="card" style={{ marginTop: 20 }}>
            <h2 style={{ marginTop: 0 }}>Corpus Summary</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
              <div><strong>Category ID:</strong> {corpus.summary.category_id}</div>
              <div><strong>Active batches:</strong> {corpus.summary.active_batches_count}</div>
              <div><strong>Total batches:</strong> {corpus.summary.total_batches_count}</div>
              <div><strong>Raw rows:</strong> {corpus.summary.total_raw_rows}</div>
              <div><strong>Normalized rows:</strong> {corpus.summary.total_normalized_rows}</div>
              <div><strong>Unique queries:</strong> {corpus.summary.unique_normalized_queries}</div>
              <div><strong>Duplicates across batches:</strong> {corpus.summary.duplicate_across_batches_count}</div>
              <div><strong>Latest batch:</strong> {corpus.summary.latest_batch_id || '-'}</div>
              <div><strong>Readiness:</strong> <span style={statusStyle(corpus.summary.readiness_status)}>{corpus.summary.readiness_status || 'not_started'}</span></div>
              <div><strong>Bootstrap run:</strong> {corpus.summary.bootstrap_run_id || '-'}</div>
              <div><strong>Bootstrap status:</strong> {corpus.summary.bootstrap_run_status || '-'}</div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 20 }}>
            <h2 style={{ marginTop: 0 }}>Batches</h2>
            {corpus.batches.length === 0 ? (
              <p style={{ marginBottom: 0 }}>No imported query batches for this category.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Batch</th>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Filename</th>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Status</th>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Created</th>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Query column</th>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Frequency column</th>
                      <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {corpus.batches.map((batch) => (
                      <tr key={batch.batch_id}>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>#{batch.batch_id}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{batch.original_filename || '-'}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{batch.status}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{formatDateTime(batch.created_at)}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{batch.query_column_resolved || '-'}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{batch.frequency_column_resolved || '-'}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top', textAlign: 'right' }}>
                          <button type="button" onClick={() => handleDeleteBatch(batch)} disabled={loading} style={{ borderColor: '#b91c1c', color: '#b91c1c' }}>
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <h2 style={{ marginTop: 0, marginBottom: 0 }}>Aggregated Normalized Queries</h2>
              <div style={{ color: '#666' }}>
                {normalized && normalized.total > 0
                  ? `Showing ${normalized.offset + 1} - ${Math.min(normalized.offset + normalized.items.length, normalized.total)} of ${normalized.total}`
                  : '0 queries'}
              </div>
            </div>

            {!normalized || normalized.items.length === 0 ? (
              <p style={{ marginTop: 16, marginBottom: 0 }}>No normalized queries in this corpus page.</p>
            ) : (
              <div style={{ overflowX: 'auto', marginTop: 16 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Normalized query</th>
                      <th style={{ textAlign: 'left', padding: '8px 6px' }}>Display query</th>
                      <th style={{ textAlign: 'right', padding: '8px 6px' }}>Raw rows</th>
                      <th style={{ textAlign: 'right', padding: '8px 6px' }}>Frequency total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {normalized.items.map((item) => (
                      <tr key={item.id}>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{item.normalized_query}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{item.display_query}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top', textAlign: 'right' }}>{item.raw_row_count}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top', textAlign: 'right' }}>{item.frequency_total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
              <button
                type="button"
                disabled={!canGoPrev || loading || !normalized}
                onClick={() => normalized && handlePageChange(Math.max(0, normalized.offset - normalized.limit))}
              >
                Prev
              </button>
              <button
                type="button"
                disabled={!canGoNext || loading || !normalized}
                onClick={() => normalized && handlePageChange(normalized.offset + normalized.limit)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
