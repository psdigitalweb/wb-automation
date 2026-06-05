'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoCompareMatcher,
  getSeoCategorySelectedQueries,
  getSeoEvalRuns,
  getSeoProductReadiness,
  getSeoProductSummary,
  getSeoProductionQuerySelectionLatest,
  getSeoProductionQuerySelectionPreview,
  getSeoQuerySelection,
  getSeoGenerationLatest,
  putSeoCategorySelectedQueries,
  postSeoGenerationPromptPreview,
  postSeoGenerationRun,
  postSeoApplyCategorySelectedQueries,
  postSeoProductAnalysisRun,
  postSeoProductionQuerySelectionRun,
  postSeoProductionQuerySelectionSave,
  type SeoGenerationLatestResponse,
  type SeoGenerationPromptPreviewResponse,
  type SeoGenerationRunResponse,
  type SeoCategorySelectedQueryListResponse,
  type SeoMatcherCompareResponse,
  type SeoProductionOperatorCandidate,
  type SeoProductionQuerySelectionPreviewResponse,
  type SeoProductionQuerySelectionRunResponse,
  type SeoProductionSelectedQuery,
  type SeoProductReadinessResponse,
  type SeoProductSummaryResponse,
  type SeoQuerySetResponse,
} from '@/lib/apiClient'
import { Card, Panel, SeoShell, StatusPill, buttonClass, normalizeError, seoStyles } from '../../_components/SeoShell'
import { QualityBadge } from '../../_components/QualityBadge'
import { ApprovalStateBadge, CategoryTierBadge } from '../../_components/CategoryTierBadge'

function imageUrlsFromProduct(product: Record<string, any> | null | undefined): string[] {
  const rawPics = product?.pics
  const urls: string[] = []
  const add = (value: unknown) => {
    const url = typeof value === 'string' ? value.trim() : ''
    if (url.startsWith('http') && !urls.includes(url)) urls.push(url)
  }
  if (typeof rawPics === 'string') {
    const trimmed = rawPics.trim()
    if (trimmed.startsWith('http')) {
      add(trimmed)
    } else if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (Array.isArray(parsed)) parsed.forEach((item) => {
          if (typeof item === 'string') add(item)
          else if (item && typeof item === 'object') {
            const pic = item as Record<string, unknown>
            add(pic.big || pic.url || pic.c516x688 || pic.hq || pic.square || pic.c128)
          }
        })
      } catch {
        // Product photo parsing is best-effort; empty state below explains missing photos.
      }
    }
  } else if (Array.isArray(rawPics)) {
    rawPics.forEach((item) => {
      if (typeof item === 'string') add(item)
      else if (item && typeof item === 'object') {
        const pic = item as Record<string, unknown>
        add(pic.big || pic.url || pic.c516x688 || pic.hq || pic.square || pic.c128)
      }
    })
  }
  return urls
}

function textValue(value: unknown, fallback = '-') {
  const text = String(value || '').trim()
  return text || fallback
}

function formatCount(value: number | null | undefined) {
  return (value ?? 0).toLocaleString('ru-RU')
}

function queryText(item: Record<string, any>) {
  return textValue(item.display_query || item.query || item.normalized_query_text, 'запрос')
}

function queryFrequency(item: Record<string, any>) {
  const value = item.ranking_value_used ?? item.ranking_value ?? item.frequency
  return typeof value === 'number' ? formatCount(value) : '-'
}

function queryLine(item: Record<string, any>) {
  return textValue(item.meaning_line || item.user_bucket_label || item.bucket, '-')
}

function normalizeQueryKey(query: string) {
  return query.trim().toLocaleLowerCase('ru-RU').replace(/\s+/g, ' ')
}

function categoryQueriesText(items: SeoCategorySelectedQueryListResponse['items'] | undefined) {
  return (items || []).filter((item) => item.source === 'category_list').map((item) => item.query_text).join('\n')
}

function categoryQuerySourceLabel(item: SeoCategorySelectedQueryListResponse['items'][number]) {
  if (item.source === 'saved_sku') {
    return item.sku_count > 1 ? `сохранено у ${item.sku_count} товаров` : 'сохранено у товара'
  }
  return 'список категории'
}

type ProductionQueryRow = {
  key: string
  query: string
  frequency: number | null
  meaningLine: string | null
  risk: string | null
  confidence: number | null
  explanation: string
  source: 'selected' | 'operator'
}

function selectedQueryToRow(item: SeoProductionSelectedQuery): ProductionQueryRow {
  return {
    key: normalizeQueryKey(item.query),
    query: item.query,
    frequency: item.frequency,
    meaningLine: item.meaning_line,
    risk: item.risk,
    confidence: item.confidence,
    explanation: item.explanation,
    source: 'selected',
  }
}

function operatorCandidateToRow(item: SeoProductionOperatorCandidate, fallbackLine: string): ProductionQueryRow {
  return {
    key: normalizeQueryKey(item.query),
    query: item.query,
    frequency: item.frequency,
    meaningLine: item.meaning_line || fallbackLine,
    risk: item.risk,
    confidence: item.confidence,
    explanation: item.explanation,
    source: 'operator',
  }
}

function productionRowsFromResult(result: SeoProductionQuerySelectionRunResponse | null): ProductionQueryRow[] {
  if (!result) return []
  const rows: ProductionQueryRow[] = []
  const seen = new Set<string>()
  for (const item of result.selected_queries) {
    const row = selectedQueryToRow(item)
    if (!seen.has(row.key)) {
      seen.add(row.key)
      rows.push(row)
    }
  }
  for (const [line, items] of Object.entries(result.operator_candidates || {})) {
    for (const item of items) {
      const row = operatorCandidateToRow(item, line)
      if (!seen.has(row.key)) {
        seen.add(row.key)
        rows.push(row)
      }
    }
  }
  return rows
}

function generationStatusTone(status: SeoGenerationRunResponse['status']): 'good' | 'warn' | 'bad' | 'neutral' {
  if (status === 'completed') return 'good'
  if (status === 'needs_review') return 'warn'
  return 'bad'
}

function SinglePassValidationBadges({ validation }: { validation?: Record<string, any> | null }) {
  if (!validation) return null
  const formatErrors = Array.isArray(validation.format_errors) ? validation.format_errors : []
  const coverage = validation.keyword_coverage || {}
  const missing = Array.isArray(coverage.missing) ? coverage.missing : []
  const covered = Array.isArray(coverage.covered) ? coverage.covered : []
  const blacklistHits = Array.isArray(validation.blacklist_hits) ? validation.blacklist_hits : []
  const mainQueryOk = validation.main_query_in_title === true
  return (
    <div style={{ display: 'grid', gap: 8, border: '1px solid #e2e8f0', borderRadius: 8, padding: 12 }}>
      <div className={seoStyles.skuBadgeRow}>
        <StatusPill label={validation.passed ? 'single-pass passed' : 'single-pass review'} tone={validation.passed ? 'good' : 'warn'} />
        <StatusPill label={formatErrors.length ? `format: ${formatErrors.length}` : 'format OK'} tone={formatErrors.length ? 'bad' : 'good'} />
        <StatusPill label={missing.length ? `missing keys: ${missing.length}` : `keys OK: ${covered.length}`} tone={missing.length ? 'warn' : 'good'} />
        <StatusPill label={blacklistHits.length ? `blacklist: ${blacklistHits.length}` : 'blacklist OK'} tone={blacklistHits.length ? 'bad' : 'good'} />
        <StatusPill label={mainQueryOk ? 'main query in title' : 'main query missing'} tone={mainQueryOk ? 'good' : 'bad'} />
      </div>
      {formatErrors.length ? <ValidationLine title="Формат" items={formatErrors} /> : null}
      {missing.length ? <ValidationLine title="Не покрыты ключи" items={missing} /> : null}
      {blacklistHits.length ? <ValidationLine title="Blacklist" items={blacklistHits} /> : null}
    </div>
  )
}

function ValidationLine({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={{ color: '#475569', fontSize: 13 }}>
      <strong>{title}:</strong> {items.join(', ')}
    </div>
  )
}

export default function SeoProductPage({ params }: { params: { projectId: string; nmId: string } }) {
  const { projectId, nmId } = params
  const searchParams = useSearchParams()
  const categoryId = searchParams.get('category_id')
  const [summary, setSummary] = useState<SeoProductSummaryResponse | null>(null)
  const [readiness, setReadiness] = useState<SeoProductReadinessResponse | null>(null)
  const [eligibilityTier, setEligibilityTier] = useState<string | null>(null)
  const [cmp, setCmp] = useState<SeoMatcherCompareResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [visionLoading, setVisionLoading] = useState(false)
  const [querySelectionLoading, setQuerySelectionLoading] = useState(false)
  const [querySaveLoading, setQuerySaveLoading] = useState(false)
  const [selectedImageUrls, setSelectedImageUrls] = useState<string[]>([])
  const [imageSelectionMessage, setImageSelectionMessage] = useState<string | null>(null)
  const [queryPromptPreview, setQueryPromptPreview] = useState<SeoProductionQuerySelectionPreviewResponse | null>(null)
  const [querySelectionResult, setQuerySelectionResult] = useState<SeoProductionQuerySelectionRunResponse | null>(null)
  const [categorySelectedQueries, setCategorySelectedQueries] = useState<SeoCategorySelectedQueryListResponse | null>(null)
  const [categoryListLoaded, setCategoryListLoaded] = useState(false)
  const [categoryListEditorOpen, setCategoryListEditorOpen] = useState(false)
  const [categoryListDraft, setCategoryListDraft] = useState('')
  const [categorySelectedQueryKeys, setCategorySelectedQueryKeys] = useState<Set<string>>(new Set())
  const [categoryListApplying, setCategoryListApplying] = useState(false)
  const [categoryListSaving, setCategoryListSaving] = useState(false)
  const [savedQuerySet, setSavedQuerySet] = useState<SeoQuerySetResponse | null>(null)
  const [selectedQueryKeys, setSelectedQueryKeys] = useState<Set<string>>(new Set())
  const [generationPromptPreview, setGenerationPromptPreview] = useState<SeoGenerationPromptPreviewResponse | null>(null)
  const [generationPromptLoading, setGenerationPromptLoading] = useState(false)
  const [generationPromptMessage, setGenerationPromptMessage] = useState<string | null>(null)
  const [generation, setGeneration] = useState<SeoGenerationRunResponse | null>(null)
  const [latestGeneration, setLatestGeneration] = useState<SeoGenerationLatestResponse | null>(null)
  const [generationLoading, setGenerationLoading] = useState(false)
  const [generationMessage, setGenerationMessage] = useState<string | null>(null)
  const [querySelectionMessage, setQuerySelectionMessage] = useState<string | null>(null)
  const [querySaveMessage, setQuerySaveMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  usePageTitle(`SEO: ${nmId}`, projectId)

  const load = async () => {
    setLoading(true)
    setError(null)
    setReadiness(null)
    setCategoryListLoaded(false)
    try {
      const resolvedCatRaw = categoryId ? Number(categoryId) : undefined
      const summaryData = await getSeoProductSummary(projectId, Number(nmId), { category_id: resolvedCatRaw })
      setSummary(summaryData)
      const imageUrls = imageUrlsFromProduct(summaryData.product)
      setSelectedImageUrls((current) => {
        const stillAvailable = current.filter((url) => imageUrls.includes(url))
        if (stillAvailable.length) return stillAvailable.slice(0, 4)
        return imageUrls.slice(0, 2)
      })
      const resolvedCat = summaryData.category_id || resolvedCatRaw
      const readinessData = await getSeoProductReadiness(projectId, Number(nmId), { category_id: resolvedCat || resolvedCatRaw })
      setReadiness(readinessData)
      if (resolvedCat) {
        const [evalRuns, compareRes, promptPreview, latestProductionRun, savedQuerySet, latestText, categoryList] = await Promise.all([
          getSeoEvalRuns(projectId, { category_id: resolvedCat, limit: 1 }).catch(() => null),
          getSeoCompareMatcher(projectId, { category_id: resolvedCat, nm_id: Number(nmId) }).catch(() => null),
          getSeoProductionQuerySelectionPreview(projectId, Number(nmId), { category_id: Number(resolvedCat) }).catch(() => null),
          getSeoProductionQuerySelectionLatest(projectId, Number(nmId), { category_id: Number(resolvedCat) }).catch(() => null),
          getSeoQuerySelection(projectId, Number(nmId), { category_id: Number(resolvedCat) }).catch(() => null),
          getSeoGenerationLatest(projectId, Number(nmId), { category_id: Number(resolvedCat) }).catch(() => null),
          getSeoCategorySelectedQueries(projectId, Number(resolvedCat)).catch(() => null),
        ])
        setEligibilityTier(evalRuns?.eligibility_tier || 'preview_only')
        setCmp(compareRes)
        setQueryPromptPreview(promptPreview)
        setLatestGeneration(latestText)
        setCategorySelectedQueries(categoryList)
        setCategoryListLoaded(true)
        if (!categoryListEditorOpen) setCategoryListDraft(categoryQueriesText(categoryList?.items))
        setCategorySelectedQueryKeys(new Set())
        setSavedQuerySet(savedQuerySet)
        if (latestProductionRun) {
          setQuerySelectionResult(latestProductionRun)
          setSelectedQueryKeys(() => {
            const savedSelected = (savedQuerySet?.items || [])
              .filter((item) => item.selection_state !== 'excluded')
              .map((item) => normalizeQueryKey(item.display_query || item.normalized_query_text))
            if (savedQuerySet && savedQuerySet.items.length) return new Set(savedSelected)
            return new Set(latestProductionRun.selected_queries.map((item) => normalizeQueryKey(item.query)))
          })
        }
      } else {
        setCategorySelectedQueries(null)
        setCategoryListLoaded(true)
      }
    } catch (e) {
      setCategoryListLoaded(true)
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId, nmId, categoryId])

  useEffect(() => {
    if (typeof window === 'undefined' || window.location.hash !== '#seo-query-selection') return
    const timer = window.setTimeout(() => {
      document.getElementById('seo-query-selection')?.scrollIntoView({ block: 'start' })
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loading, summary])

  const analyze = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await postSeoProductAnalysisRun(projectId, Number(nmId), {
        category_id: summary?.category_id || (categoryId ? Number(categoryId) : undefined),
        force_refresh: false,
        include_vision: true,
        selected_image_urls: selectedImageUrls,
      })
      await load()
      if (result.warnings.length) setError(`Анализ завершен с предупреждениями: ${result.warnings.join(', ')}`)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const runAiVision = async () => {
    if (!selectedImageUrls.length) {
      setImageSelectionMessage('Фото товара не найдены или не выбраны. AI vision запускать нечего.')
      return
    }
    setVisionLoading(true)
    setError(null)
    setImageSelectionMessage(null)
    try {
      const result = await postSeoProductAnalysisRun(projectId, Number(nmId), {
        category_id: summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined),
        force_refresh: true,
        include_vision: true,
        selected_image_urls: selectedImageUrls,
      })
      await load()
      if (result.warnings.length) setError(`AI vision завершен с предупреждениями: ${result.warnings.join(', ')}`)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setVisionLoading(false)
    }
  }

  const runProductionSelection = async () => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat) {
      setError('Нельзя запустить подбор: категория товара не определена.')
      return
    }
    setQuerySelectionLoading(true)
    setQuerySelectionMessage(null)
    setError(null)
    try {
      const result = await postSeoProductionQuerySelectionRun(projectId, Number(nmId), { category_id: Number(resolvedCat) })
      setQuerySelectionResult(result)
      setSelectedQueryKeys(new Set(result.selected_queries.map((item) => normalizeQueryKey(item.query))))
      setQuerySelectionMessage(`Production run #${result.run_id}: выбрано ${result.selected_queries.length} запросов.`)
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setQuerySelectionLoading(false)
    }
  }

  const saveProductionSelection = async () => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat || !querySelectionResult) {
      setError('Нельзя сохранить выбор: сначала запустите подбор запросов.')
      return
    }
    setQuerySaveLoading(true)
    setQuerySaveMessage(null)
    setError(null)
    try {
      const saved = await postSeoProductionQuerySelectionSave(projectId, Number(nmId), {
        category_id: Number(resolvedCat),
        run_id: querySelectionResult.run_id,
        items: productionRows.map((row) => ({
          query: row.query,
          selected: selectedQueryKeys.has(row.key),
          frequency: row.frequency,
          meaning_line: row.meaningLine,
          risk: row.risk,
          confidence: row.confidence,
          explanation: row.explanation,
          source: row.source,
        })),
      })
      setQuerySaveMessage(`Выбор сохранён: ${saved.items.filter((item) => item.selection_state !== 'excluded').length} запросов.`)
      setSavedQuerySet(saved)
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setQuerySaveLoading(false)
    }
  }

  const applyCategorySelectedList = async () => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat) {
      setError('Нельзя применить список: категория товара не определена.')
      return
    }
    setCategoryListApplying(true)
    setQuerySaveMessage(null)
    setError(null)
    try {
      const queryTexts = categoryListItems
        .filter((item) => categorySelectedQueryKeys.has(normalizeQueryKey(item.query_text)))
        .map((item) => item.query_text)
      if (!queryTexts.length) {
        setError('Выберите хотя бы один запрос из списка категории.')
        return
      }
      const saved = await postSeoApplyCategorySelectedQueries(projectId, Number(nmId), {
        category_id: Number(resolvedCat),
        query_texts: queryTexts,
      })
      setQuerySelectionResult(null)
      setSavedQuerySet(saved)
      setSelectedQueryKeys(new Set(saved.items.filter((item) => item.selection_state !== 'excluded').map((item) => normalizeQueryKey(item.display_query))))
      setQuerySaveMessage(`Список категории применён: ${saved.items.length} запросов.`)
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setCategoryListApplying(false)
    }
  }

  const saveCategorySelectedList = async () => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat) {
      setError('Нельзя сохранить список категории: категория товара не определена.')
      return
    }
    setCategoryListSaving(true)
    setQuerySaveMessage(null)
    setError(null)
    try {
      const saved = await putSeoCategorySelectedQueries(projectId, Number(resolvedCat), {
        queries: categoryListDraft.split('\n'),
      })
      setCategorySelectedQueries(saved)
      setCategoryListDraft(categoryQueriesText(saved.items))
      setCategorySelectedQueryKeys(new Set())
      setQuerySaveMessage(`Список категории сохранён: ${saved.total} запросов.`)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setCategoryListSaving(false)
    }
  }

  const addCurrentSelectionToCategoryList = async () => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat) {
      setError('Нельзя обновить список категории: категория товара не определена.')
      return
    }
    const currentSelectedQueries = querySelectionResult
      ? productionRows.filter((row) => selectedQueryKeys.has(row.key)).map((row) => row.query)
      : (savedQuerySet?.items || [])
          .filter((item) => item.selection_state !== 'excluded')
          .map((item) => item.display_query || item.normalized_query_text)
    if (!currentSelectedQueries.length) {
      setError('Нечего добавить: сначала выберите или сохраните запросы для товара.')
      return
    }
    setCategoryListSaving(true)
    setQuerySaveMessage(null)
    setError(null)
    try {
      const existing = (categorySelectedQueries?.items || []).map((item) => item.query_text)
      const merged: string[] = []
      const seen = new Set<string>()
      for (const query of [...existing, ...currentSelectedQueries]) {
        const key = normalizeQueryKey(query)
        if (!key || seen.has(key)) continue
        seen.add(key)
        merged.push(query)
      }
      const saved = await putSeoCategorySelectedQueries(projectId, Number(resolvedCat), { queries: merged })
      setCategorySelectedQueries(saved)
      setCategoryListDraft(categoryQueriesText(saved.items))
      setCategorySelectedQueryKeys(new Set())
      setQuerySaveMessage(`Список категории обновлён: ${saved.total} запросов.`)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setCategoryListSaving(false)
    }
  }

  const resolvedCategory = summary?.category_id || categoryId
  const product = summary?.product || {}
  const productImageUrls = imageUrlsFromProduct(product)
  const candidateMeta = (cmp?.candidate?.meta || {}) as Record<string, any>
  const matcherRunId = candidateMeta.matcher_run_id as number | undefined
  const approvalState = candidateMeta.approval_state as string | undefined
  const trustState = candidateMeta.trust_state as string | undefined
  const categoryProfileVersion = candidateMeta.category_profile_version as string | undefined
  const candidateItems = ((cmp?.candidate?.items || []) as Record<string, any>[]).slice(0, 8)
  const productionRows = productionRowsFromResult(querySelectionResult)
  const selectedPreviewItems = querySelectionResult?.selected_queries || candidateItems
  const selectedCount = querySelectionResult ? selectedQueryKeys.size : readiness?.existing_query_set?.selected_items ?? candidateItems.length
  const itemsTotal = readiness?.existing_query_set?.items_total ?? candidateItems.length
  const savedSelectedItems = (savedQuerySet?.items || []).filter((item) => item.selection_state !== 'excluded')
  const generatedTitle = generation?.generated_card?.title || latestGeneration?.title || ''
  const generatedDescription = generation?.generated_card?.description || latestGeneration?.description || ''
  const generatedModel = generation?.model_name || latestGeneration?.response_payload?.model_name || null
  const savedQuerySetId = readiness?.existing_query_set?.query_set_id || null
  const canGenerateText = Boolean(resolvedCategory && savedQuerySetId && selectedCount > 0 && !generationLoading)
  const productTitle = textValue(product.title || product.name, `SKU ${nmId}`)
  const vendorCode = textValue(product.vendor_code || product.article || product.supplierArticle, 'SKU')
  const categoryName = textValue(product.subject_name || product.category_name || product.subject || resolvedCategory, 'без категории')
  const description = textValue(product.description, 'Описание карточки пока не найдено.')
  const feedbacks = product.feedbacks ?? product.review_count ?? product.reviews_count
  const fallbackReadiness = [
    { key: 'product', label: 'Карточка найдена', ready: Boolean(summary?.product) },
    { key: 'category', label: `Категория: ${categoryName}`, ready: Boolean(resolvedCategory) },
    { key: 'query-data', label: summary?.category_status_label || 'Query data категории', ready: summary?.category_status_label === 'Готова к подбору' },
    { key: 'vision', label: summary?.vision_status_label || 'AI vision', ready: summary?.vision_status_label === 'Фото учтены' },
  ]
  const readinessRows = readiness?.readiness || fallbackReadiness
  const categoryListItems = categorySelectedQueries?.items || []
  const selectedCategoryListItems = categoryListItems.filter((item) => categorySelectedQueryKeys.has(normalizeQueryKey(item.query_text)))

  const toggleImageSelection = (url: string) => {
    setImageSelectionMessage(null)
    setSelectedImageUrls((current) => {
      if (current.includes(url)) {
        const next = current.filter((item) => item !== url)
        return next.length ? next : current
      }
      if (current.length >= 4) {
        setImageSelectionMessage('Можно выбрать максимум 4 фото для AI vision.')
        return current
      }
      return [...current, url]
    })
  }

  const toggleQuerySelection = (key: string) => {
    setSelectedQueryKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const selectAllProductionRows = () => {
    setSelectedQueryKeys(new Set(productionRows.map((row) => row.key)))
  }

  const clearProductionRows = () => {
    setSelectedQueryKeys(new Set())
  }

  const toggleCategorySelectedQuery = (key: string) => {
    setCategorySelectedQueryKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const selectAllCategoryQueries = () => {
    setCategorySelectedQueryKeys(new Set(categoryListItems.map((item) => normalizeQueryKey(item.query_text))))
  }

  const clearCategoryQueries = () => {
    setCategorySelectedQueryKeys(new Set())
  }

  const showGenerationPromptPreview = async () => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat) {
      setError('Нельзя собрать prompt: категория товара не определена.')
      return
    }
    setGenerationPromptLoading(true)
    setGenerationPromptMessage(null)
    setError(null)
    try {
      const selectedRows = productionRows.filter((row) => selectedQueryKeys.has(row.key))
      const selectedPreviewQuery = selectedRows[0]?.query || (selectedPreviewItems[0] ? queryText(selectedPreviewItems[0]) : null)
      const prompt = await postSeoGenerationPromptPreview(projectId, Number(nmId), {
        category_id: Number(resolvedCat),
        query_set_id: readiness?.existing_query_set?.query_set_id || null,
        main_query_text: selectedRows[0]?.query || selectedPreviewQuery,
        brand_voice: 'тёплый',
      })
      setGenerationPromptPreview(prompt)
      setGenerationPromptMessage('Prompt собран из текущего сохранённого набора запросов.')
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setGenerationPromptLoading(false)
    }
  }

  const runGeneration = async (strategy: 'two_pass' | 'single_pass_sonnet' = 'two_pass') => {
    const resolvedCat = summary?.category_id || readiness?.category_id || (categoryId ? Number(categoryId) : undefined)
    if (!resolvedCat || !savedQuerySetId) {
      setError('Нельзя сгенерировать текст: сначала сохраните выбор запросов.')
      return
    }
    setGenerationLoading(true)
    setGenerationMessage(null)
    setGeneration(null)
    setError(null)
    try {
      const selectedRows = productionRows.filter((row) => selectedQueryKeys.has(row.key))
      const selectedPreviewQuery = selectedRows[0]?.query || (selectedPreviewItems[0] ? queryText(selectedPreviewItems[0]) : null)
      const response = await postSeoGenerationRun(projectId, Number(nmId), {
        category_id: Number(resolvedCat),
        query_set_id: savedQuerySetId,
        main_query_text: selectedRows[0]?.query || selectedPreviewQuery,
        brand_voice: 'тёплый',
        strategy,
      })
      setGeneration(response)
      const latest = await getSeoGenerationLatest(projectId, Number(nmId), { category_id: Number(resolvedCat) }).catch(() => null)
      setLatestGeneration(latest)
      setGenerationMessage(
        response.status === 'completed'
          ? 'Текст сгенерирован и сохранён.'
          : response.status === 'needs_review'
            ? 'Текст сохранён, но validator просит review.'
            : 'Генерация завершилась с ошибкой.',
      )
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setGenerationLoading(false)
    }
  }

  return (
    <SeoShell projectId={projectId} title={productTitle} subtitle="Подбор запросов по evidence, prior и кластерам категории.">
      <div className={seoStyles.skuPage}>
        {error ? <Card><div style={{ color: error.startsWith('Анализ завершен') ? 'var(--seo-warning)' : 'var(--seo-danger)' }}>{error}</div></Card> : null}

        <div className={seoStyles.skuTopActions}>
          <Link className={buttonClass('light')} href={`/app/project/${projectId}/seo/products`}>← Товары</Link>
        </div>

        <section className={`${seoStyles.panel} ${seoStyles.skuHero}`}>
          <div className={seoStyles.skuHeroImage}>
            {productImageUrls[0] ? <img src={productImageUrls[0]} alt="" /> : <span>{vendorCode.slice(0, 3).toLowerCase()}</span>}
          </div>
          <div className={seoStyles.skuHeroInfo}>
            <h2>{productTitle}</h2>
            <div className={seoStyles.subtext}>{vendorCode} · nm_id: {nmId}</div>
            <div className={seoStyles.skuFacts}>
              <div>
                <span>Категория</span>
                <strong>{categoryName}</strong>
              </div>
              <div>
                <span>Описание</span>
                <p>{description}</p>
              </div>
              <div>
                <span>Отзывов</span>
                <strong>{feedbacks != null ? formatCount(Number(feedbacks)) : '-'}</strong>
              </div>
            </div>
            <div className={seoStyles.skuBadgeRow}>
              {summary ? <StatusPill label={summary.product_status_label} tone={summary.product_status_label === 'Готов к подбору' ? 'good' : 'warn'} /> : null}
              {summary ? <StatusPill label={summary.vision_status_label} tone={summary.vision_status_label === 'Фото учтены' ? 'good' : 'neutral'} /> : null}
              {summary ? <StatusPill label={summary.category_status_label} tone={summary.category_status_label === 'Готова к подбору' ? 'good' : 'warn'} /> : null}
              <CategoryTierBadge tier={eligibilityTier} profileVersion={categoryProfileVersion || null} />
              {summary?.quality_mode ? <QualityBadge mode={summary.quality_mode} reasons={(summary.degraded_reasons || []) as any} /> : null}
              <ApprovalStateBadge approvalState={approvalState} trustState={trustState} />
            </div>
          </div>
        </section>

        <div className={seoStyles.skuWorkbenchGrid}>
          <Panel
            title="Готовность к подбору"
            actions={<StatusPill label={readiness?.can_select_queries ? 'Можно запускать' : 'Есть блокер'} tone={readiness?.can_select_queries ? 'good' : 'warn'} />}
          >
            <>
              <div className={seoStyles.readinessList}>
                {readinessRows.map((item) => (
                  <div key={item.key} className={seoStyles.readinessRow}>
                    <span className={item.ready ? seoStyles.readyMark : seoStyles.blockedMark}>{item.ready ? '✓' : '✗'}</span>
                    <span>{item.label}{'details' in item && item.details ? `: ${item.details}` : ''}</span>
                  </div>
                ))}
              </div>
              {readiness && !readiness.can_select_queries && readiness.blocking_reasons.length ? (
                <div className={seoStyles.warningStrip}>
                  Нельзя запустить подбор: {readiness.blocking_reasons.join(' ')}
                </div>
              ) : null}
              <div className={seoStyles.skuPanelActions}>
                <button
                  type="button"
                  className={buttonClass(readiness?.can_select_queries ? 'primary' : 'light')}
                  onClick={runProductionSelection}
                  disabled={querySelectionLoading || !resolvedCategory || readiness?.can_select_queries === false}
                  title={readiness?.can_select_queries === false ? 'Подбор заблокирован: проверьте готовность категории, SKU и vision.' : undefined}
                >
                  {querySelectionLoading ? 'Подбираем...' : readiness?.can_select_queries ? 'Запустить подбор' : 'Сначала AI vision'}
                </button>
                <button type="button" onClick={analyze} disabled={loading || visionLoading} className={buttonClass('light')}>
                  {loading ? 'Анализируем...' : 'Обновить анализ'}
                </button>
              </div>
            </>
          </Panel>

          <Panel
            title="AI Vision"
            actions={
              <button type="button" onClick={runAiVision} disabled={visionLoading || !selectedImageUrls.length} className={buttonClass('light')}>
                {visionLoading ? 'Обновляем...' : readiness?.ai_vision.ready ? 'Обновить vision' : 'Запустить vision'}
              </button>
            }
          >
            <div className={seoStyles.photoPickerLabel}>Выберите фото для анализа</div>
            <div className={seoStyles.photoPicker}>
              {(productImageUrls.length ? productImageUrls : ['', '', '', '', '']).slice(0, 5).map((url, index) => {
                const selected = Boolean(url && selectedImageUrls.includes(url))
                return (
                  <button
                    key={url || `empty-${index}`}
                    type="button"
                    onClick={() => url && toggleImageSelection(url)}
                    className={`${seoStyles.photoTile} ${selected ? seoStyles.photoTileSelected : ''}`.trim()}
                    disabled={!url}
                  >
                    {url ? <img src={url} alt="" /> : null}
                    <span>{url ? `фото ${index + 1}` : `фото ${index + 1}`}</span>
                    {selected ? <strong>✓</strong> : null}
                  </button>
                )
              })}
            </div>
            <div className={seoStyles.subtext}>Будет отправлено: {selectedImageUrls.length} из {productImageUrls.length || 0} фото</div>
            {imageSelectionMessage ? <div className={seoStyles.warningStrip}>{imageSelectionMessage}</div> : null}
            <div className={seoStyles.visionVerdict}>
              <strong>AI vision verdict</strong>
              <p>{readiness?.ai_vision.label || 'AI vision не выполнен.'}</p>
              {readiness?.ai_vision.items.length ? (
                <div className={seoStyles.skuBadgeRow}>
                  {readiness.ai_vision.items.slice(0, 8).map((item, index) => <StatusPill key={`${item}-${index}`} label={item} />)}
                </div>
              ) : null}
              <span>Vision — evidence для подбора запросов, не финальный SEO-результат.</span>
            </div>
          </Panel>
        </div>

        <Panel
          title="Список запросов категории"
          subtitle={
            !categoryListLoaded
              ? 'Загружаем список запросов категории'
              : categoryListItems.length
              ? `${formatCount(categoryListItems.length)} запросов из списка категории и сохранённых выборов товаров`
              : 'Для этой категории ещё нет заранее выбранного списка'
          }
          actions={
            resolvedCategory ? (
              <button
                type="button"
                className={buttonClass('light')}
                onClick={() => {
                  setCategoryListDraft(categoryQueriesText(categorySelectedQueries?.items))
                  setCategoryListEditorOpen((value) => !value)
                }}
              >
                {categoryListEditorOpen ? 'Скрыть список категории' : 'Открыть список категории'}
              </button>
            ) : null
          }
        >
          {categoryListEditorOpen ? (
            <div style={{ display: 'grid', gap: 10, marginBottom: 14 }}>
              <label style={{ display: 'block' }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Вручную закреплённые запросы категории</div>
                <textarea
                  value={categoryListDraft}
                  onChange={(event) => setCategoryListDraft(event.target.value)}
                  placeholder="Один запрос на строку"
                  style={{
                    width: '100%',
                    minHeight: 180,
                    padding: 12,
                    border: '1px solid #cbd5e1',
                    borderRadius: 8,
                    resize: 'vertical',
                    fontSize: 14,
                    lineHeight: 1.5,
                  }}
                />
              </label>
              <div className={seoStyles.skuPanelActions}>
                <button
                  type="button"
                  className={buttonClass('light')}
                  onClick={() => setCategoryListDraft(categoryQueriesText(categorySelectedQueries?.items))}
                  disabled={categoryListSaving}
                >
                  Отменить правки
                </button>
                <button
                  type="button"
                  className={buttonClass('primary')}
                  onClick={saveCategorySelectedList}
                  disabled={categoryListSaving}
                >
                  {categoryListSaving ? 'Сохраняем...' : 'Сохранить список'}
                </button>
              </div>
            </div>
          ) : null}
          {!categoryListLoaded ? (
            <div className={seoStyles.muted}>Загружаем список запросов категории...</div>
          ) : categoryListItems.length ? (
            <>
              <div className={seoStyles.selectionToolbar}>
                <div className={seoStyles.querySelectionMeta}>
                  Отмечено {formatCount(selectedCategoryListItems.length)} из {formatCount(categoryListItems.length)}. По умолчанию список не выбран.
                </div>
                <div className={seoStyles.pager}>
                  <button type="button" className={buttonClass('light')} onClick={selectAllCategoryQueries}>Выбрать все</button>
                  <button type="button" className={buttonClass('light')} onClick={clearCategoryQueries}>Снять все</button>
                </div>
              </div>
              <div className={`${seoStyles.tableWrap} ${seoStyles.queryScroll}`}>
                <table className={`${seoStyles.table} ${seoStyles.queryChoiceTable}`}>
                  <thead>
                    <tr>
                      <th>Выбор</th>
                      <th>Запрос</th>
                      <th>Источник</th>
                      <th>Частотность</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categoryListItems.map((item) => {
                      const key = normalizeQueryKey(item.query_text)
                      return (
                        <tr key={item.id}>
                          <td>
                            <input
                              type="checkbox"
                              checked={categorySelectedQueryKeys.has(key)}
                              onChange={() => toggleCategorySelectedQuery(key)}
                              aria-label={`Выбрать ${item.query_text}`}
                            />
                          </td>
                          <td className={seoStyles.queryChoiceCell}><strong>{item.query_text}</strong></td>
                          <td>{categoryQuerySourceLabel(item)}</td>
                          <td className={seoStyles.num}>{item.ranking_value_used != null ? formatCount(Number(item.ranking_value_used)) : '-'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div className={seoStyles.skuPanelActions}>
                <button
                  type="button"
                  className={buttonClass('primary')}
                  onClick={applyCategorySelectedList}
                  disabled={categoryListApplying || !resolvedCategory || !selectedCategoryListItems.length}
                >
                  {categoryListApplying ? 'Применяем...' : 'Применить выбранные к товару'}
                </button>
                <button
                  type="button"
                  className={buttonClass('light')}
                  onClick={runProductionSelection}
                  disabled={querySelectionLoading || !resolvedCategory}
                >
                  {querySelectionLoading ? 'Подбираем...' : 'Всё-таки подобрать индивидуально'}
                </button>
              </div>
            </>
          ) : (
            <div className={seoStyles.muted}>
              Откройте список категории в этом блоке и добавьте запросы, после этого здесь появится кнопка применения.
            </div>
          )}
          {savedSelectedItems.length || querySelectionResult ? (
            <div className={seoStyles.skuPanelActions}>
              <button
                type="button"
                className={buttonClass('light')}
                onClick={addCurrentSelectionToCategoryList}
                disabled={categoryListSaving}
              >
                {categoryListSaving ? 'Добавляем...' : 'Добавить текущий выбор в список категории'}
              </button>
            </div>
          ) : null}
        </Panel>

        <div id="seo-query-selection" className={seoStyles.querySelectionAnchor}>
        <Panel
          title={`Подбор запросов${matcherRunId ? ` · run #${matcherRunId}` : ''}`}
          subtitle={`Кандидатов: ${formatCount(queryPromptPreview?.candidates.total_candidate_count || querySelectionResult?.candidate_count || itemsTotal)} · выбрано: ${formatCount(selectedCount)} · подбор выполняется на этой странице`}
          actions={
            <div className={seoStyles.pager}>
              <button type="button" className={buttonClass('light')} onClick={runProductionSelection} disabled={querySelectionLoading || !resolvedCategory}>
                {querySelectionLoading ? 'Подбираем...' : selectedPreviewItems.length ? 'Запустить подбор заново' : 'Запустить подбор здесь'}
              </button>
            </div>
          }
        >
          {querySelectionMessage ? <div className={seoStyles.successStrip}>{querySelectionMessage}</div> : null}
          {querySaveMessage ? <div className={seoStyles.successStrip}>{querySaveMessage}</div> : null}
          {querySelectionResult ? (
            <>
              <div className={seoStyles.selectionToolbar}>
                <div className={seoStyles.querySelectionMeta}>
                  Показано {formatCount(productionRows.length)} запросов: {formatCount(querySelectionResult.selected_queries.length)} выбрано LLM, {formatCount(productionRows.length - querySelectionResult.selected_queries.length)} на ручной выбор.
                </div>
                <div className={seoStyles.pager}>
                  <button type="button" className={buttonClass('light')} onClick={selectAllProductionRows}>Выбрать все</button>
                  <button type="button" className={buttonClass('light')} onClick={clearProductionRows}>Снять все</button>
                  <button type="button" className={buttonClass('primary')} onClick={saveProductionSelection} disabled={querySaveLoading || !productionRows.length}>
                    {querySaveLoading ? 'Сохраняем...' : 'Сохранить выбор'}
                  </button>
                </div>
              </div>
              <div className={`${seoStyles.tableWrap} ${seoStyles.queryScroll}`}>
                <table className={`${seoStyles.table} ${seoStyles.queryChoiceTable}`}>
                  <thead>
                    <tr>
                      <th>Выбор</th>
                      <th>Запрос</th>
                      <th>Частотность</th>
                      <th>Линия</th>
                      <th>Статус</th>
                      <th>Комментарий</th>
                    </tr>
                  </thead>
                  <tbody>
                    {productionRows.map((row) => (
                      <tr key={row.key}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedQueryKeys.has(row.key)}
                            onChange={() => toggleQuerySelection(row.key)}
                            aria-label={`Выбрать ${row.query}`}
                          />
                        </td>
                        <td className={seoStyles.queryChoiceCell}><strong>{row.query}</strong></td>
                        <td className={seoStyles.num}>{row.frequency != null ? formatCount(Number(row.frequency)) : '-'}</td>
                        <td>{row.meaningLine || '-'}</td>
                        <td>
                          <StatusPill label={row.source === 'selected' ? 'LLM выбрал' : 'кандидат'} tone={row.source === 'selected' ? 'good' : 'neutral'} />
                          {row.risk ? <span className={seoStyles.queryRisk}>{row.risk}</span> : null}
                        </td>
                        <td>{row.explanation || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : savedSelectedItems.length ? (
            <div className={seoStyles.tableWrap}>
              <table className={seoStyles.table}>
                <thead>
                  <tr>
                    <th>Сохранённый запрос</th>
                    <th>Источник</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {savedSelectedItems.map((item) => (
                    <tr key={item.normalized_query_text}>
                      <td><strong>{item.display_query || item.normalized_query_text}</strong></td>
                      <td>{savedQuerySet?.matcher_version || 'category list'}</td>
                      <td><StatusPill label="сохранён" tone="good" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : selectedPreviewItems.length ? (
            <div className={seoStyles.tableWrap}>
              <table className={seoStyles.table}>
                <thead>
                  <tr>
                    <th>Запрос</th>
                    <th>Частотность</th>
                    <th>Линия</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedPreviewItems.map((item, index) => (
                    <tr key={`${queryText(item)}-${index}`}>
                      <td><strong>{queryText(item)}</strong></td>
                      <td className={seoStyles.num}>{queryFrequency(item)}</td>
                      <td>{queryLine(item)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className={seoStyles.muted}>Подбор ещё не запускался. Нажмите «Запустить подбор здесь» — результат появится в этом блоке без перехода на старый экран.</div>
          )}
        </Panel>
        </div>

        <Panel
          title="Генерация текста"
          subtitle="Генерирует название и описание по сохранённому выбору запросов."
          actions={
            <div className={seoStyles.pager}>
              <button type="button" className={buttonClass('light')} onClick={showGenerationPromptPreview} disabled={generationPromptLoading || !resolvedCategory}>
                {generationPromptLoading ? 'Собираем prompt...' : 'Показать prompt'}
              </button>
              <button type="button" className={buttonClass('primary')} onClick={() => runGeneration('two_pass')} disabled={!canGenerateText}>
                {generationLoading ? 'Генерируем...' : 'Сгенерировать two-pass'}
              </button>
              <button type="button" className={buttonClass('light')} onClick={() => runGeneration('single_pass_sonnet')} disabled={!canGenerateText}>
                Sonnet single-pass
              </button>
            </div>
          }
        >
          <div className={seoStyles.draftPreview}>
            <div>
              <strong>Черновик карточки</strong>
              <p>{savedQuerySetId ? 'Сохранённый выбор запросов готов для генерации.' : 'Сначала сохраните выбор запросов, затем соберите текст.'}</p>
            </div>
            <div>
              <strong>Что проверить перед копированием</strong>
              <ul>
                <li>Использованы только утверждённые запросы.</li>
                <li>Не добавлены свойства, которых нет в карточке или на фото.</li>
                <li>Материал, объём и назначение совпадают с evidence.</li>
              </ul>
            </div>
          </div>
          {generationMessage ? <div className={generation?.status === 'completed' ? seoStyles.successStrip : seoStyles.warningStrip}>{generationMessage}</div> : null}
          {generation?.error_text ? <div className={seoStyles.warningStrip}>{generation.error_text}</div> : null}
          {generatedTitle || generatedDescription ? (
            <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
              <div className={seoStyles.skuBadgeRow}>
                {generation?.content_version_id || latestGeneration?.content_version_id ? <StatusPill label={`content #${generation?.content_version_id || latestGeneration?.content_version_id}`} tone="neutral" /> : null}
                {generatedModel ? <StatusPill label={generatedModel} tone="neutral" /> : null}
                {generation ? <StatusPill label={generation.status} tone={generationStatusTone(generation.status)} /> : null}
                <StatusPill label="текст сохранён" tone="good" />
              </div>
              <SinglePassValidationBadges validation={generation?.single_pass_validation} />
              <label style={{ display: 'block' }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Название</div>
                <input
                  readOnly
                  value={generatedTitle}
                  style={{ width: '100%', padding: 12, border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 16, fontWeight: 700 }}
                />
              </label>
              <label style={{ display: 'block' }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Описание</div>
                <textarea
                  readOnly
                  value={generatedDescription}
                  style={{ width: '100%', minHeight: 260, padding: 12, border: '1px solid #cbd5e1', borderRadius: 8, resize: 'vertical', fontSize: 14, lineHeight: 1.55 }}
                />
              </label>
            </div>
          ) : null}
          {generationPromptMessage ? <div className={seoStyles.successStrip}>{generationPromptMessage}</div> : null}
          {generationPromptPreview ? (
            <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
              <div className={seoStyles.skuBadgeRow}>
                <StatusPill label={generationPromptPreview.model_name} tone="neutral" />
                <StatusPill label={generationPromptPreview.prompt_version} tone="neutral" />
                <StatusPill label={`выбор #${generationPromptPreview.query_set_id}`} tone="neutral" />
              </div>
              <label style={{ display: 'block' }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>User prompt</div>
                <textarea
                  readOnly
                  value={generationPromptPreview.user_prompt}
                  style={{ width: '100%', minHeight: 360, padding: 12, border: '1px solid #cbd5e1', borderRadius: 8, resize: 'vertical', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 13, lineHeight: 1.45 }}
                />
              </label>
              <details>
                <summary style={{ cursor: 'pointer', fontWeight: 800 }}>System prompt</summary>
                <textarea
                  readOnly
                  value={generationPromptPreview.system_prompt}
                  style={{ width: '100%', minHeight: 260, marginTop: 10, padding: 12, border: '1px solid #cbd5e1', borderRadius: 8, resize: 'vertical', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 13, lineHeight: 1.45 }}
                />
              </details>
            </div>
          ) : null}
        </Panel>

        {loading && !summary ? <Card>Загружаем...</Card> : null}
      </div>
    </SeoShell>
  )
}
