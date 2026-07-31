'use client'

import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import PortalBackButton from '@/components/PortalBackButton'
import WBProductLookupInput from '@/components/WBProductLookupInput'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSkuMeaningAnnotation,
  getSkuMeaningCandidateQueries,
  getSkuMeaningEvidence,
  getSkuMeaningProductLookup,
  getCategoryBootstrapStatus,
  getQueryMeaningLibrary,
  postCategoryBootstrapRun,
  postMeaningAwareMatcherPreview,
  postQueryMeaningLibraryBuild,
  postSkuMeaningDraft,
  postSkuMeaningEvalExport,
  putSkuMeaningAnnotation,
  putSkuMeaningQueryJudgments,
  type ApiError,
  type CategoryBootstrapStatusResponse,
  type MeaningAwareMatcherBucket,
  type MeaningAwareMatcherItem,
  type MeaningAwareMatcherResponse,
  type SkuMeaningAnnotationResponse,
  type SkuMeaningCandidateQuery,
  type SkuMeaningEvidencePack,
  type SkuMeaningPayload,
  type SkuMeaningStatus,
  type SkuQueryJudgmentLabel,
  type WBProductLookupItem,
} from '@/lib/apiClient'


const STATUS_OPTIONS: SkuMeaningStatus[] = ['draft', 'verified', 'needs_more_data', 'rejected']
const LABEL_OPTIONS: SkuQueryJudgmentLabel[] = [
  'highly_relevant',
  'maybe_relevant',
  'too_broad',
  'irrelevant',
  'conflict',
  'dangerous_claim',
  'manual_rejected',
]
const MATCHER_BUCKETS: MeaningAwareMatcherBucket[] = ['primary', 'secondary', 'broad', 'rejected']
const MATCHER_BUCKET_LABELS: Record<MeaningAwareMatcherBucket, string> = {
  primary: 'Primary',
  secondary: 'Secondary',
  broad: 'Broad',
  rejected: 'Rejected',
}

type JudgmentsState = Record<string, { label: SkuQueryJudgmentLabel | ''; rationale: string }>

function emptyMeaning(): SkuMeaningPayload {
  return {
    schema_version: 'sku_meaning_v0',
    functional: {},
    expressive: {},
    audience: [],
    negative_constraints: [],
    confidence: {},
    evidence_refs: [],
    review_status: 'draft',
  }
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function normalizeError(error: unknown): string {
  const apiError = error as Partial<ApiError>
  return apiError?.detail || (error instanceof Error ? error.message : 'Unknown error')
}

function Pill({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        minHeight: 24,
        border: '1px solid #d7dde5',
        borderRadius: 6,
        padding: '2px 8px',
        fontSize: 12,
        color: '#334155',
        background: '#f8fafc',
      }}
    >
      {children}
    </span>
  )
}

export default function SkuMeaningAnnotationPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  usePageTitle('SKU Meaning Annotation', projectId)

  const [lookupValue, setLookupValue] = useState('')
  const [selectedProduct, setSelectedProduct] = useState<WBProductLookupItem | null>(null)
  const [categoryInput, setCategoryInput] = useState('')
  const [evidence, setEvidence] = useState<SkuMeaningEvidencePack | null>(null)
  const [annotation, setAnnotation] = useState<SkuMeaningAnnotationResponse | null>(null)
  const [meaningText, setMeaningText] = useState(pretty(emptyMeaning()))
  const [status, setStatus] = useState<SkuMeaningStatus>('draft')
  const [reviewer, setReviewer] = useState('')
  const [draftMeta, setDraftMeta] = useState<{ model?: string | null; prompt_version?: string; artifact_path?: string | null }>({})
  const [queryMeaningCount, setQueryMeaningCount] = useState<number | null>(null)
  const [categoryReadiness, setCategoryReadiness] = useState<CategoryBootstrapStatusResponse | null>(null)
  const [matcherResult, setMatcherResult] = useState<MeaningAwareMatcherResponse | null>(null)
  const [queries, setQueries] = useState<SkuMeaningCandidateQuery[]>([])
  const [querySearch, setQuerySearch] = useState('')
  const [judgments, setJudgments] = useState<JudgmentsState>({})
  const [includeDrafts, setIncludeDrafts] = useState(false)
  const [exportContent, setExportContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [draftLoading, setDraftLoading] = useState(false)
  const [libraryLoading, setLibraryLoading] = useState(false)
  const [bootstrapLoading, setBootstrapLoading] = useState(false)
  const [matcherLoading, setMatcherLoading] = useState(false)
  const [rejectingMatcherKey, setRejectingMatcherKey] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const nmId = selectedProduct?.nm_id ?? null
  const resolvedCategoryId = useMemo(() => {
    const fromEvidence = evidence?.category_id
    if (fromEvidence != null) return fromEvidence
    const parsed = Number(categoryInput)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
  }, [categoryInput, evidence?.category_id])
  const matcherBlockedByBootstrap = categoryReadiness?.readiness_status === 'building'

  async function loadSkuByNmId(nextNmId: number, overrideCategoryId?: number) {
    setError('')
    setMessage('')
    setLoading(true)
    setEvidence(null)
    setSelectedProduct(null)
    setAnnotation(null)
    setQueryMeaningCount(null)
    setCategoryReadiness(null)
    setMatcherResult(null)
    setQueries([])
    setJudgments({})
    try {
      const pack = await getSkuMeaningEvidence(projectId, nextNmId, { category_id: overrideCategoryId })
      setEvidence(pack)
      setCategoryInput(String(pack.category_id))
      const loadedProduct: WBProductLookupItem = {
        nm_id: pack.nm_id,
        vendor_code: pack.product.vendor_code || null,
        title: pack.product.title || null,
        wb_category: pack.product.subject_name || null,
      }
      setSelectedProduct(loadedProduct)
      setLookupValue(loadedProduct.vendor_code ? `${loadedProduct.vendor_code} · ${loadedProduct.nm_id}` : String(loadedProduct.nm_id))

      const annotationEnvelope = await getSkuMeaningAnnotation(projectId, nextNmId, { category_id: pack.category_id })
      const saved = annotationEnvelope.annotation
      setAnnotation(saved)
      if (saved) {
        setMeaningText(pretty(saved.meaning))
        setStatus(saved.status)
        setReviewer(saved.reviewer || '')
        setDraftMeta({
          model: saved.draft_model,
          prompt_version: saved.draft_prompt_version || undefined,
          artifact_path: saved.draft_artifact_path,
        })
      } else {
        setMeaningText(pretty(emptyMeaning()))
        setStatus('draft')
        setDraftMeta({})
      }

      setQueries([])
      setMatcherResult(null)
      setJudgments({})
      try {
        const library = await getQueryMeaningLibrary(projectId, { category_id: pack.category_id, limit: 1 })
        setQueryMeaningCount(library.total)
      } catch {
        setQueryMeaningCount(null)
      }
      try {
        const readiness = await getCategoryBootstrapStatus(projectId, { category_id: pack.category_id })
        setCategoryReadiness(readiness)
        setQueryMeaningCount(readiness.query_meanings_count || null)
      } catch {
        setCategoryReadiness(null)
      }
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function loadSku(product: WBProductLookupItem, overrideCategoryId?: number) {
    await loadSkuByNmId(product.nm_id, overrideCategoryId)
  }

  async function loadSkuFromInput() {
    const trimmed = lookupValue.trim()
    if (!trimmed) return
    const parsedNmId = Number(trimmed.match(/\d{6,}/)?.[0] || NaN)
    if (!Number.isFinite(parsedNmId)) {
      setError(`Enter nm_id, got "${trimmed}".`)
      return
    }
    await loadSkuByNmId(parsedNmId, Number(categoryInput) || undefined)
  }

  async function reloadQueries() {
    if (!nmId || !resolvedCategoryId) return
    setError('')
    try {
      const payload = await getSkuMeaningCandidateQueries(projectId, nmId, {
        category_id: resolvedCategoryId,
        limit: 100,
        search: querySearch,
      })
      setQueries(payload.items)
      setJudgments((prev) => {
        const next = { ...prev }
        for (const item of payload.items) {
          if (!next[item.normalized_query_text]) {
            next[item.normalized_query_text] = {
              label: item.existing_label || '',
              rationale: item.existing_rationale || '',
            }
          }
        }
        return next
      })
    } catch (err) {
      setError(normalizeError(err))
    }
  }

  useEffect(() => {
    if (!selectedProduct || !resolvedCategoryId) return
    const timer = window.setTimeout(() => {
      reloadQueries()
    }, 250)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [querySearch])

  useEffect(() => {
    if (!resolvedCategoryId || categoryReadiness?.readiness_status !== 'building') return
    const timer = window.setInterval(() => {
      handleRefreshBootstrapStatus()
    }, 3000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedCategoryId, categoryReadiness?.readiness_status])

  async function handleGenerateDraft(forceRefresh = false) {
    if (!nmId) return
    setDraftLoading(true)
    setError('')
    setMessage('')
    try {
      const draft = await postSkuMeaningDraft(projectId, nmId, {
        category_id: resolvedCategoryId,
        force_refresh: forceRefresh,
      })
      setMeaningText(pretty(draft.meaning))
      setStatus(draft.meaning.review_status)
      setDraftMeta({
        model: draft.model,
        prompt_version: draft.prompt_version,
        artifact_path: draft.artifact_path,
      })
      if (evidence && draft.evidence_hash !== evidence.evidence_hash) {
        setMessage('Draft generated for a different evidence hash; reload evidence before saving.')
      } else {
        setMessage(draft.cached ? 'Draft loaded from cache.' : 'Draft generated.')
      }
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setDraftLoading(false)
    }
  }

  async function handleSaveAnnotation() {
    if (!nmId || !evidence) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const meaning = JSON.parse(meaningText) as SkuMeaningPayload
      const syncedMeaning = { ...meaning, review_status: status }
      const saved = await putSkuMeaningAnnotation(projectId, nmId, {
        category_id: evidence.category_id,
        meaning: syncedMeaning,
        status,
        evidence_hash: evidence.evidence_hash,
        reviewer: reviewer || null,
        source_metadata: {
          tool: 'sku_meaning_preview_annotation',
          product_title: evidence.product?.title || null,
        },
        draft_model: draftMeta.model || null,
        draft_prompt_version: draftMeta.prompt_version || null,
        draft_artifact_path: draftMeta.artifact_path || null,
      })
      setAnnotation(saved)
      setMeaningText(pretty(saved.meaning))
      setMessage('Annotation saved.')
      await reloadQueries()
    } catch (err) {
      setError(err instanceof SyntaxError ? 'Meaning JSON is invalid.' : normalizeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleBuildQueryMeanings(forceRefresh = false) {
    if (!resolvedCategoryId) return
    setLibraryLoading(true)
    setError('')
    setMessage('')
    try {
      const result = await postQueryMeaningLibraryBuild(projectId, {
        category_id: resolvedCategoryId,
        limit: 500,
        force_refresh: forceRefresh,
        use_llm: false,
      })
      const library = await getQueryMeaningLibrary(projectId, { category_id: resolvedCategoryId, limit: 1 })
      setQueryMeaningCount(library.total)
      setMessage(
        `Query meanings: ${result.created} created, ${result.updated} updated, ${result.skipped} skipped, ${result.errors} errors.`
      )
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLibraryLoading(false)
    }
  }

  async function handleRefreshBootstrapStatus() {
    if (!resolvedCategoryId) return
    setBootstrapLoading(true)
    setError('')
    try {
      const readiness = await getCategoryBootstrapStatus(projectId, { category_id: resolvedCategoryId })
      setCategoryReadiness(readiness)
      setQueryMeaningCount(readiness.query_meanings_count || null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setBootstrapLoading(false)
    }
  }

  async function handleRunBootstrap(forceRefresh = false) {
    if (!resolvedCategoryId) return
    setBootstrapLoading(true)
    setError('')
    setMessage('')
    try {
      const started = await postCategoryBootstrapRun(projectId, {
        category_id: resolvedCategoryId,
        force_refresh: forceRefresh,
        use_llm: true,
      })
      setMessage(`Category bootstrap queued as run #${started.run_id}.`)
      const readiness = await getCategoryBootstrapStatus(projectId, { category_id: resolvedCategoryId })
      setCategoryReadiness(readiness)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setBootstrapLoading(false)
    }
  }

  async function handleRunMatcher() {
    if (!nmId || !resolvedCategoryId) return
    setMatcherLoading(true)
    setError('')
    setMessage('')
    try {
      const result = await postMeaningAwareMatcherPreview(projectId, {
        category_id: resolvedCategoryId,
        nm_id: nmId,
        limit: 400,
        include_rejected: true,
      })
      setMatcherResult(result)
      setMessage(`Matcher scored ${result.diagnostics.scored_total} query meanings.`)
    } catch (err) {
      setError(normalizeError(err))
      await handleRefreshBootstrapStatus()
    } finally {
      setMatcherLoading(false)
    }
  }

  async function handleManualRejectMatcherItem(item: MeaningAwareMatcherItem) {
    if (!nmId || !evidence || !annotation) return
    const key = item.cluster_key || item.query
    setRejectingMatcherKey(key)
    setError('')
    setMessage('')
    try {
      await putSkuMeaningQueryJudgments(projectId, nmId, {
        category_id: evidence.category_id,
        annotation_id: annotation.id,
        items: [
          {
            query_text: item.query,
            normalized_query_text: item.query,
            query_id: null,
            cluster_id: item.cluster_id,
            cluster_key: item.cluster_key,
            label: 'manual_rejected',
            rationale: 'Manual rejected from matcher preview.',
            reviewer: reviewer || null,
            matcher_version: matcherResult?.diagnostics.matcher_version || null,
            source: 'matcher_preview',
          },
        ],
      })
      setMessage(`Manual rejected: ${item.query}`)
      await handleRunMatcher()
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setRejectingMatcherKey(null)
    }
  }

  async function handleSaveJudgments() {
    if (!nmId || !evidence) return
    const items = queries
      .map((query) => {
        const state = judgments[query.normalized_query_text]
        if (!state?.label) return null
        return {
          query_text: query.query_text,
          normalized_query_text: query.normalized_query_text,
          query_id: query.query_id,
          cluster_id: query.cluster_id,
          cluster_key: query.cluster_key,
          label: state.label as SkuQueryJudgmentLabel,
          rationale: state.rationale || null,
          reviewer: reviewer || null,
          source: 'manual',
        }
      })
      .filter(Boolean) as Array<{
        query_text: string
        normalized_query_text: string
        query_id: number | null
        cluster_id: number | null
        cluster_key: string | null
        label: SkuQueryJudgmentLabel
        rationale: string | null
        reviewer: string | null
        source: string
      }>

    setSaving(true)
    setError('')
    setMessage('')
    try {
      await putSkuMeaningQueryJudgments(projectId, nmId, {
        category_id: evidence.category_id,
        annotation_id: annotation?.id || null,
        items,
      })
      setMessage(`Saved ${items.length} query judgments.`)
      await reloadQueries()
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    setError('')
    setMessage('')
    try {
      const payload = await postSkuMeaningEvalExport(projectId, {
        category_id: resolvedCategoryId || null,
        nm_ids: nmId ? [nmId] : null,
        include_drafts: includeDrafts,
        format: 'jsonl',
      })
      setExportContent(payload.content)
      setMessage(`Exported ${payload.exported_count} rows.`)
    } catch (err) {
      setError(normalizeError(err))
    }
  }

  const selectedJudgmentCount = Object.values(judgments).filter((item) => item.label).length

  return (
    <main style={{ minHeight: '100vh', background: '#f6f7f9', color: '#111827' }}>
      <div style={{ width: '100%', maxWidth: 1440, margin: '0 auto', padding: '24px 20px 56px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <PortalBackButton fallbackHref={`/app/project/${projectId}/seo/query-pipeline/debug`} />
            <div>
              <h1 style={{ margin: 0, fontSize: 24, lineHeight: '30px', fontWeight: 700 }}>SKU Meaning Annotation</h1>
              <div style={{ marginTop: 4, color: '#64748b', fontSize: 13 }}>Project {projectId}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {evidence && <Pill>category {evidence.category_id}</Pill>}
            {annotation && <Pill>annotation #{annotation.id}</Pill>}
            {evidence && <Pill>evidence {evidence.evidence_hash.slice(0, 10)}</Pill>}
          </div>
        </div>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
          <WBProductLookupInput
            projectId={projectId}
            value={lookupValue}
            onChange={setLookupValue}
            onSelect={(item) => loadSku(item)}
            lookupFn={getSkuMeaningProductLookup}
            placeholder="nm_id or vendor code"
          />
          <input
            value={categoryInput}
            onChange={(event) => setCategoryInput(event.target.value)}
            placeholder="category_id"
            style={{ height: 40, border: '1px solid #d1d5db', borderRadius: 6, padding: '0 10px', fontSize: 14 }}
          />
          <button
            type="button"
            disabled={loading || !lookupValue.trim()}
            onClick={loadSkuFromInput}
            style={{ height: 40, border: 0, borderRadius: 6, background: '#1f2937', color: '#fff', fontWeight: 600, cursor: !loading && lookupValue.trim() ? 'pointer' : 'not-allowed' }}
          >
            {loading ? 'Loading...' : 'Load'}
          </button>
        </section>

        {error && <div style={{ marginBottom: 12, padding: 12, border: '1px solid #fecaca', borderRadius: 6, background: '#fff1f2', color: '#991b1b', fontSize: 13 }}>{error}</div>}
        {message && <div style={{ marginBottom: 12, padding: 12, border: '1px solid #bbf7d0', borderRadius: 6, background: '#f0fdf4', color: '#166534', fontSize: 13 }}>{message}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16, alignItems: 'start' }}>
          <section style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>Evidence Pack</h2>
              <button
                type="button"
                disabled={!nmId || draftLoading}
                onClick={() => handleGenerateDraft(false)}
                style={{ height: 36, border: 0, borderRadius: 6, background: '#2563eb', color: '#fff', fontWeight: 600, padding: '0 12px', cursor: nmId ? 'pointer' : 'not-allowed' }}
              >
                {draftLoading ? 'Generating...' : 'Generate draft'}
              </button>
            </div>

            {!evidence && <div style={{ color: '#64748b', fontSize: 14 }}>{loading ? 'Loading evidence...' : 'Select SKU to load evidence.'}</div>}
            {evidence && (
              <div style={{ display: 'grid', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>Title</div>
                  <div style={{ fontSize: 15, fontWeight: 650 }}>{String(evidence.product.title || '-')}</div>
                  <div style={{ marginTop: 4, color: '#64748b', fontSize: 13 }}>
                    {evidence.product.vendor_code || '-'} · nm {evidence.nm_id} · {evidence.product.subject_name || evidence.category_id}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <Pill>{evidence.reviews.length} reviews</Pill>
                  <Pill>{Object.keys(evidence.category_prior || {}).length ? 'category prior' : 'no category prior'}</Pill>
                  <Pill>{Object.keys(evidence.product_projection || {}).length ? 'projection' : 'no projection'}</Pill>
                </div>

                <pre style={{ maxHeight: 500, overflow: 'auto', margin: 0, padding: 12, background: '#0f172a', color: '#e5e7eb', borderRadius: 6, fontSize: 12, lineHeight: '18px' }}>
                  {pretty({
                    product: evidence.product,
                    reviews: evidence.reviews.slice(0, 5),
                    category_prior: evidence.category_prior,
                    product_projection: evidence.product_projection,
                    warnings: evidence.warnings,
                  })}
                </pre>
              </div>
            )}
          </section>

          <section style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>SKU Meaning</h2>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  disabled={!nmId || draftLoading}
                  onClick={() => handleGenerateDraft(true)}
                  style={{ height: 36, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff', color: '#334155', fontWeight: 600, padding: '0 12px', cursor: nmId ? 'pointer' : 'not-allowed' }}
                >
                  Refresh draft
                </button>
                <button
                  type="button"
                  disabled={!evidence || saving}
                  onClick={handleSaveAnnotation}
                  style={{ height: 36, border: 0, borderRadius: 6, background: '#047857', color: '#fff', fontWeight: 600, padding: '0 12px', cursor: evidence ? 'pointer' : 'not-allowed' }}
                >
                  {saving ? 'Saving...' : 'Save meaning'}
                </button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 10, marginBottom: 10 }}>
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value as SkuMeaningStatus)}
                style={{ height: 36, border: '1px solid #d1d5db', borderRadius: 6, padding: '0 8px' }}
              >
                {STATUS_OPTIONS.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <input
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                placeholder="reviewer"
                style={{ height: 36, border: '1px solid #d1d5db', borderRadius: 6, padding: '0 10px' }}
              />
            </div>

            <textarea
              value={meaningText}
              onChange={(event) => setMeaningText(event.target.value)}
              spellCheck={false}
              style={{
                width: '100%',
                minHeight: 520,
                resize: 'vertical',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                padding: 12,
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                fontSize: 12,
                lineHeight: '18px',
                boxSizing: 'border-box',
              }}
            />
          </section>
        </div>

        <section style={{ marginTop: 16, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 18 }}>Matcher Preview</h2>
              <div style={{ marginTop: 4, color: '#64748b', fontSize: 13 }}>
                {queryMeaningCount == null ? 'query meanings unknown' : `${queryMeaningCount} query meanings`} · {categoryReadiness?.readiness_status || 'readiness unknown'} · meaning-aware ranking
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <button
                type="button"
                disabled={!resolvedCategoryId || bootstrapLoading}
                onClick={() => handleRunBootstrap(false)}
                style={{ height: 36, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff', color: '#334155', fontWeight: 600, padding: '0 12px', cursor: resolvedCategoryId ? 'pointer' : 'not-allowed' }}
              >
                {bootstrapLoading ? 'Working...' : 'Run bootstrap'}
              </button>
              <button
                type="button"
                disabled={!resolvedCategoryId || bootstrapLoading}
                onClick={handleRefreshBootstrapStatus}
                style={{ height: 36, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff', color: '#334155', fontWeight: 600, padding: '0 12px', cursor: resolvedCategoryId ? 'pointer' : 'not-allowed' }}
              >
                Refresh status
              </button>
              <button
                type="button"
                disabled={!annotation || !resolvedCategoryId || matcherLoading || matcherBlockedByBootstrap}
                onClick={handleRunMatcher}
                style={{ height: 36, border: 0, borderRadius: 6, background: '#0f766e', color: '#fff', fontWeight: 600, padding: '0 12px', cursor: annotation && resolvedCategoryId && !matcherBlockedByBootstrap ? 'pointer' : 'not-allowed' }}
              >
                {matcherLoading ? 'Running...' : 'Run matcher'}
              </button>
            </div>
          </div>

          {categoryReadiness && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <Pill>readiness {categoryReadiness.readiness_status}</Pill>
              <Pill>run {categoryReadiness.latest_run_id || '-'}</Pill>
              <Pill>step {categoryReadiness.current_step || '-'}</Pill>
              <Pill>{categoryReadiness.clusters_count} clusters</Pill>
              <Pill>{categoryReadiness.query_meanings_count} meanings</Pill>
              <Pill>{categoryReadiness.embeddings_count} embeddings</Pill>
              {categoryReadiness.last_error && <Pill>{categoryReadiness.last_error.slice(0, 90)}</Pill>}
            </div>
          )}

          {!matcherResult ? (
            <div style={{ padding: '18px 6px', color: '#64748b', fontSize: 13 }}>
              Matcher output will appear here after category bootstrap is ready and a saved SKU Meaning exists.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 14 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Pill>annotation #{matcherResult.sku_annotation_id}</Pill>
                <Pill>{matcherResult.diagnostics.matcher_version}</Pill>
                <Pill>{matcherResult.diagnostics.embedding_model || 'embedding model unknown'}</Pill>
              </div>

              {MATCHER_BUCKETS.map((bucket) => {
                const items = matcherResult.buckets[bucket] || []
                return (
                  <div key={bucket} style={{ borderTop: '1px solid #e5e7eb', paddingTop: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <h3 style={{ margin: 0, fontSize: 15 }}>{MATCHER_BUCKET_LABELS[bucket]}</h3>
                      <Pill>{items.length}</Pill>
                    </div>
                    {items.length === 0 ? (
                      <div style={{ color: '#94a3b8', fontSize: 13, padding: '6px 0' }}>empty</div>
                    ) : (
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', fontSize: 13 }}>
                          <thead>
                            <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #e5e7eb' }}>
                              <th style={{ padding: '8px 6px', width: '22%' }}>Query</th>
                              <th style={{ padding: '8px 6px', width: 90 }}>Score</th>
                              <th style={{ padding: '8px 6px', width: 90 }}>Similarity</th>
                              <th style={{ padding: '8px 6px', width: 110 }}>Rank</th>
                              <th style={{ padding: '8px 6px', width: '18%' }}>Matched</th>
                              <th style={{ padding: '8px 6px', width: 100 }}>Manual</th>
                              <th style={{ padding: '8px 6px' }}>Reasons</th>
                            </tr>
                          </thead>
                          <tbody>
                            {items.map((item) => (
                              <tr key={`${bucket}-${item.query_meaning_id}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top', wordBreak: 'break-word' }}>
                                  <div style={{ fontWeight: 650 }}>{item.query}</div>
                                  <div style={{ marginTop: 2, color: '#64748b', fontSize: 12 }}>{item.genericness} · {item.cluster_key || '-'}</div>
                                </td>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{item.score.toFixed(3)}</td>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{item.semantic_similarity.toFixed(3)}</td>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{item.ranking_value_used == null ? '-' : item.ranking_value_used.toFixed(0)}</td>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top', wordBreak: 'break-word' }}>
                                  {item.matched_meanings.length ? item.matched_meanings.join(', ') : '-'}
                                </td>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>
                                  <button
                                    type="button"
                                    disabled={!annotation || rejectingMatcherKey === (item.cluster_key || item.query)}
                                    onClick={() => handleManualRejectMatcherItem(item)}
                                    style={{ height: 30, border: '1px solid #fecaca', borderRadius: 6, background: '#fff1f2', color: '#991b1b', fontWeight: 650, padding: '0 8px', cursor: annotation ? 'pointer' : 'not-allowed' }}
                                  >
                                    {rejectingMatcherKey === (item.cluster_key || item.query) ? 'Saving' : 'Reject'}
                                  </button>
                                </td>
                                <td style={{ padding: '8px 6px', verticalAlign: 'top', wordBreak: 'break-word' }}>
                                  {[...item.reasons, ...item.conflicts].filter(Boolean).slice(0, 5).join(' · ') || '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>

        <section style={{ marginTop: 16, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 18 }}>Eval Query Sample</h2>
              <div style={{ marginTop: 4, color: '#64748b', fontSize: 13 }}>{selectedJudgmentCount} selected · {queries.length} raw candidates · not matcher output</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={querySearch}
                onChange={(event) => setQuerySearch(event.target.value)}
                placeholder="search queries"
                style={{ height: 36, width: 220, border: '1px solid #d1d5db', borderRadius: 6, padding: '0 10px' }}
              />
              <button
                type="button"
                disabled={!nmId || !resolvedCategoryId}
                onClick={reloadQueries}
                style={{ height: 36, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff', color: '#334155', fontWeight: 600, padding: '0 12px', cursor: nmId && resolvedCategoryId ? 'pointer' : 'not-allowed' }}
              >
                Load raw sample
              </button>
              <button
                type="button"
                disabled={!annotation || saving || queries.length === 0}
                onClick={handleSaveJudgments}
                style={{ height: 36, border: 0, borderRadius: 6, background: '#1f2937', color: '#fff', fontWeight: 600, padding: '0 12px', cursor: annotation && queries.length > 0 ? 'pointer' : 'not-allowed' }}
              >
                Save judgments
              </button>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            {queries.length === 0 ? (
              <div style={{ padding: '18px 6px', color: '#64748b', fontSize: 13 }}>
                Raw frequency candidates are hidden by default.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: '#475569', textAlign: 'left', borderBottom: '1px solid #e5e7eb' }}>
                    <th style={{ padding: '8px 6px', width: '32%' }}>Query</th>
                    <th style={{ padding: '8px 6px', width: '16%' }}>Cluster</th>
                    <th style={{ padding: '8px 6px', width: 110 }}>Rank</th>
                    <th style={{ padding: '8px 6px', width: 190 }}>Label</th>
                    <th style={{ padding: '8px 6px' }}>Rationale</th>
                  </tr>
                </thead>
                <tbody>
                  {queries.map((query) => {
                    const state = judgments[query.normalized_query_text] || { label: '', rationale: '' }
                    return (
                      <tr key={query.normalized_query_text} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top', wordBreak: 'break-word' }}>
                          <div style={{ fontWeight: 650 }}>{query.query_text}</div>
                          <div style={{ marginTop: 2, color: '#64748b', fontSize: 12 }}>{query.bucket || '-'} · {query.intent_type || '-'}</div>
                        </td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top', wordBreak: 'break-word' }}>{query.cluster_label_candidate || query.cluster_key || '-'}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>{query.ranking_value_used || '-'}</td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>
                          <select
                            value={state.label}
                            onChange={(event) => {
                              const value = event.target.value as SkuQueryJudgmentLabel | ''
                              setJudgments((prev) => ({
                                ...prev,
                                [query.normalized_query_text]: { ...state, label: value },
                              }))
                            }}
                            style={{ height: 34, width: '100%', border: '1px solid #d1d5db', borderRadius: 6, padding: '0 8px' }}
                          >
                            <option value="">-</option>
                            {LABEL_OPTIONS.map((item) => (
                              <option key={item} value={item}>{item}</option>
                            ))}
                          </select>
                        </td>
                        <td style={{ padding: '8px 6px', verticalAlign: 'top' }}>
                          <input
                            value={state.rationale}
                            onChange={(event) => {
                              const value = event.target.value
                              setJudgments((prev) => ({
                                ...prev,
                                [query.normalized_query_text]: { ...state, rationale: value },
                              }))
                            }}
                            style={{ height: 34, width: '100%', border: '1px solid #d1d5db', borderRadius: 6, padding: '0 8px', boxSizing: 'border-box' }}
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section style={{ marginTop: 16, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Eval Export</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#475569', fontSize: 13 }}>
                <input type="checkbox" checked={includeDrafts} onChange={(event) => setIncludeDrafts(event.target.checked)} />
                include drafts
              </label>
              <button
                type="button"
                disabled={!resolvedCategoryId}
                onClick={handleExport}
                style={{ height: 36, border: 0, borderRadius: 6, background: '#7c3aed', color: '#fff', fontWeight: 600, padding: '0 12px', cursor: resolvedCategoryId ? 'pointer' : 'not-allowed' }}
              >
                Export JSONL
              </button>
            </div>
          </div>
          <textarea
            value={exportContent}
            onChange={(event) => setExportContent(event.target.value)}
            spellCheck={false}
            style={{
              width: '100%',
              minHeight: 180,
              resize: 'vertical',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              padding: 12,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              fontSize: 12,
              lineHeight: '18px',
              boxSizing: 'border-box',
            }}
          />
        </section>
      </div>
    </main>
  )
}
