'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoEvalRuns,
  getSeoFeatureFlags,
  getSeoGenerationLatest,
  getSeoProductSummary,
  getSeoQuerySelection,
  postSeoGenerationHumanReview,
  postSeoGenerationPromote,
  postSeoGenerationRun,
  type SeoFeatureFlags,
  type SeoGenerationLatestResponse,
  type SeoGenerationRunResponse,
  type SeoProductSummaryResponse,
  type SeoQuerySelectionItem,
  type SeoQuerySetResponse,
  type SeoRelevanceReport,
  type SeoRelevanceV2Report,
} from '@/lib/apiClient'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../../../_components/SeoShell'
import { QualityBadge, ResearchPreviewBanner } from '../../../_components/QualityBadge'
import { CategoryTierBadge } from '../../../_components/CategoryTierBadge'

type BrandVoice = 'экспертный' | 'тёплый' | 'минималистичный' | 'игривый'
type Panel = 'brief' | 'queries' | 'rules' | 'draft'

const brandVoices: BrandVoice[] = ['экспертный', 'тёплый', 'минималистичный', 'игривый']

const bucketLabels: Record<string, string> = {
  primary: 'Primary',
  secondary: 'Secondary',
  broad: 'Broad context',
  rejected: 'Rejected',
}

const panelLabels: Record<Panel, string> = {
  brief: 'Бриф',
  queries: 'Запросы',
  rules: 'Правила',
  draft: 'Черновик',
}

const isSelected = (item: SeoQuerySelectionItem) => item.selection_state !== 'excluded' && item.bucket !== 'rejected'

const queryTone = (bucket: string): 'good' | 'warn' | 'bad' | 'neutral' => {
  if (bucket === 'primary') return 'good'
  if (bucket === 'secondary') return 'neutral'
  if (bucket === 'broad') return 'warn'
  return 'bad'
}

function unique(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((value) => String(value || '').trim()).filter(Boolean)))
}

function blockItems(summary: SeoProductSummaryResponse | null, title: string) {
  return summary?.blocks.find((block) => block.title === title)?.items || []
}

function topQueries(items: SeoQuerySelectionItem[], bucket: string, limit: number) {
  return items
    .filter((item) => item.bucket === bucket && isSelected(item))
    .sort((a, b) => {
      const byScore = b.score - a.score
      if (byScore !== 0) return byScore
      return (b.ranking_value_used || 0) - (a.ranking_value_used || 0)
    })
    .slice(0, limit)
}

function sortQueries(items: SeoQuerySelectionItem[]) {
  return [...items].sort((a, b) => {
    const bucketRank: Record<string, number> = { primary: 0, secondary: 1, broad: 2, rejected: 3 }
    const byBucket = (bucketRank[a.bucket] ?? 9) - (bucketRank[b.bucket] ?? 9)
    if (byBucket !== 0) return byBucket
    const byScore = b.score - a.score
    if (byScore !== 0) return byScore
    return (b.ranking_value_used || 0) - (a.ranking_value_used || 0)
  })
}

function defaultMainQuery(querySet: SeoQuerySetResponse | null, latest: SeoGenerationLatestResponse | null) {
  const latestMain = latest?.seo_relevance_v2?.main_query_text || latest?.seo_relevance?.main_query_text || latest?.score_breakdown?.seo_relevance?.main_query_text
  const selectedItems = sortQueries((querySet?.items || []).filter(isSelected))
  if (latestMain && selectedItems.some((item) => item.display_query === latestMain)) return latestMain
  return selectedItems.find((item) => item.bucket === 'primary')?.display_query || selectedItems[0]?.display_query || ''
}

function relevanceTone(report: { score: number } | null | undefined): 'good' | 'warn' | 'bad' | 'neutral' {
  if (!report) return 'neutral'
  if (report.score >= 80) return 'good'
  if (report.score >= 55) return 'warn'
  return 'bad'
}

export default function SeoGenerationPage({ params }: { params: { projectId: string; nmId: string } }) {
  const { projectId, nmId } = params
  const searchParams = useSearchParams()
  const categoryId = searchParams.get('category_id') || ''
  const [summary, setSummary] = useState<SeoProductSummaryResponse | null>(null)
  const [querySet, setQuerySet] = useState<SeoQuerySetResponse | null>(null)
  const [latest, setLatest] = useState<SeoGenerationLatestResponse | null>(null)
  const [generation, setGeneration] = useState<SeoGenerationRunResponse | null>(null)
  const [featureFlags, setFeatureFlags] = useState<SeoFeatureFlags | null>(null)
  const [eligibilityTier, setEligibilityTier] = useState<string | null>(null)
  const [brandVoice, setBrandVoice] = useState<BrandVoice>('экспертный')
  const [mainQueryText, setMainQueryText] = useState('')
  const [panel, setPanel] = useState<Panel>('brief')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reviewVerdict, setReviewVerdict] = useState<'accept' | 'reject' | 'needs_changes'>('accept')
  const [reviewReviewer, setReviewReviewer] = useState('operator')
  const [reviewNotes, setReviewNotes] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewMsg, setReviewMsg] = useState<string | null>(null)
  const [promoteTarget, setPromoteTarget] = useState<'candidate' | 'approved' | 'published'>('candidate')
  const [promoteBusy, setPromoteBusy] = useState(false)
  const [promoteMsg, setPromoteMsg] = useState<string | null>(null)
  usePageTitle(`SEO генерация: ${nmId}`, projectId)

  const load = async () => {
    if (!categoryId) {
      setError('category_id не передан в адресе страницы')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [summaryData, queryData, latestData, flagsData, evalRuns] = await Promise.all([
        getSeoProductSummary(projectId, Number(nmId), { category_id: Number(categoryId) }),
        getSeoQuerySelection(projectId, Number(nmId), { category_id: Number(categoryId) }),
        getSeoGenerationLatest(projectId, Number(nmId), { category_id: Number(categoryId) }).catch(() => null),
        getSeoFeatureFlags().catch(() => null),
        getSeoEvalRuns(projectId, { category_id: Number(categoryId), limit: 1 }).catch(() => null),
      ])
      setSummary(summaryData)
      setQuerySet(queryData)
      setLatest(latestData)
      setFeatureFlags(flagsData)
      setEligibilityTier(evalRuns?.eligibility_tier || 'preview_only')
      setMainQueryText(defaultMainQuery(queryData, latestData))
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId, nmId, categoryId])

  const selected = useMemo(() => (querySet?.items || []).filter(isSelected), [querySet])
  const selectedForPrompt = useMemo(() => sortQueries(selected), [selected])
  const primary = useMemo(() => topQueries(querySet?.items || [], 'primary', 80), [querySet])
  const secondary = useMemo(() => topQueries(querySet?.items || [], 'secondary', 120), [querySet])
  const broad = useMemo(() => topQueries(querySet?.items || [], 'broad', 80), [querySet])
  const expressive = useMemo(
    () => unique([...blockItems(summary, 'Стиль и эмоциональный контекст'), ...blockItems(summary, 'Для кого подходит')]),
    [summary],
  )
  const productFacts = useMemo(
    () => unique([...blockItems(summary, 'Что мы поняли о товаре'), ...blockItems(summary, 'Что видно на фото')]).slice(0, 16),
    [summary],
  )
  const negative = useMemo(() => blockItems(summary, 'Какие запросы не подходят'), [summary])
  const product = summary?.product || {}
  const isConfirmed = querySet?.status === 'confirmed'
  const hasProductMeaning = summary?.product_status_label === 'Готов к подбору'
  const hasSelectedQueries = selected.length > 0
  const hasPrimaryQueries = primary.length > 0
  const hasMainQuery = Boolean(mainQueryText && selected.some((item) => item.display_query === mainQueryText))
  // Iteration 1 (CD-1 / OD-1): the run button is gated on the
  // `SEO_GENERATION_PREVIEW_ENABLED` env flag exposed via
  // `GET /api/v1/seo/feature-flags`. The hardcoded `true` has been removed.
  const previewEnabled = Boolean(featureFlags?.generation_preview_enabled)
  const generationEndpointReady = previewEnabled
  const canGenerate = Boolean(isConfirmed && hasProductMeaning && hasSelectedQueries && hasPrimaryQueries && hasMainQuery && generationEndpointReady && !generating)
  const generatedCard = generation?.generated_card || null
  const draftTitle = generatedCard?.title || latest?.title || ''
  const draftDescription = generatedCard?.description || latest?.description || ''
  const draftCharacteristics = generatedCard?.characteristics || []
  const generationIssues = generation?.validation_results || []
  const seoRelevance = generation?.seo_relevance || latest?.seo_relevance || latest?.score_breakdown?.seo_relevance || null
  const seoRelevanceV2 = generation?.seo_relevance_v2 || latest?.seo_relevance_v2 || latest?.score_breakdown?.seo_relevance_v2 || null

  useEffect(() => {
    if (!querySet || !selected.length) return
    if (!mainQueryText || !selected.some((item) => item.display_query === mainQueryText)) {
      setMainQueryText(defaultMainQuery(querySet, latest))
    }
  }, [querySet, latest, selected, mainQueryText])

  const activeContentVersionId = generation?.content_version_id || latest?.content_version_id || null
  const activeMatcherRunId = generation?.matcher_run_id || latest?.matcher_run_id || null

  const submitHumanReview = async () => {
    if (!activeContentVersionId) {
      setReviewMsg('Нет content_version — сначала выполните генерацию.')
      return
    }
    setReviewBusy(true)
    setReviewMsg(null)
    try {
      const res = await postSeoGenerationHumanReview(projectId, activeContentVersionId, {
        verdict: reviewVerdict,
        reviewer: reviewReviewer || undefined,
        notes: reviewNotes || undefined,
      })
      setReviewMsg(`Human review #${res.id} записан: verdict=${res.verdict}.`)
    } catch (e) {
      setReviewMsg(normalizeError(e))
    } finally {
      setReviewBusy(false)
    }
  }

  const submitPromote = async () => {
    if (!activeContentVersionId) {
      setPromoteMsg('Нет content_version — сначала выполните генерацию.')
      return
    }
    setPromoteBusy(true)
    setPromoteMsg(null)
    try {
      const res = await postSeoGenerationPromote(projectId, activeContentVersionId, { target_kind: promoteTarget })
      setPromoteMsg(`Promote OK: ${res.previous_content_kind} → ${res.new_content_kind}; tier=${res.eligibility_tier}.`)
    } catch (e) {
      setPromoteMsg(normalizeError(e))
    } finally {
      setPromoteBusy(false)
    }
  }

  const runGeneration = async () => {
    if (!canGenerate || !categoryId) return
    setGenerating(true)
    setError(null)
    setGeneration(null)
    try {
      const response = await postSeoGenerationRun(projectId, Number(nmId), {
        category_id: Number(categoryId),
        query_set_id: querySet?.id || null,
        main_query_text: mainQueryText,
        brand_voice: brandVoice,
        allow_draft_query_set: false,
      })
      setGeneration(response)
      setPanel('draft')
      const latestData = await getSeoGenerationLatest(projectId, Number(nmId), { category_id: Number(categoryId) }).catch(() => null)
      setLatest(latestData)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setGenerating(false)
    }
  }

  const readiness = [
    { label: 'Товар проанализирован', ok: Boolean(hasProductMeaning), detail: summary?.product_status_label || 'Нет данных' },
    { label: 'Запросы выбраны для генерации', ok: Boolean(isConfirmed), detail: isConfirmed ? 'готово' : 'не выбраны' },
    { label: 'Есть выбранные запросы', ok: Boolean(hasSelectedQueries), detail: `${selected.length} выбрано` },
    { label: 'Главный запрос выбран', ok: Boolean(hasMainQuery), detail: mainQueryText || 'Не выбран' },
    {
      label: 'Generation preview включён',
      ok: generationEndpointReady,
      detail: generationEndpointReady
        ? 'research preview активен'
        : 'поднимите SEO_GENERATION_PREVIEW_ENABLED, чтобы запустить генерацию',
    },
  ]

  const briefPreview = {
    product: {
      project_id: Number(projectId),
      category_id: summary?.category_id || Number(categoryId),
      nm_id: Number(nmId),
      vendor_code: product.vendor_code || null,
      brand: product.brand || null,
      current_title: product.title || null,
      current_description: product.description || null,
      subject_name: product.subject_name || null,
    },
    generation_policy: {
      brand_voice: brandVoice,
      primary_model: 'anthropic/claude-haiku-4.5',
      fallback_model: 'anthropic/claude-sonnet-4.5',
      max_title_chars: 60,
      max_description_chars: 5000,
    },
    evidence: {
      product_facts: productFacts,
      expressive_context: expressive,
      negative_constraints: negative,
    },
    query_set: {
      id: querySet?.id || null,
      status: querySet?.status || 'draft',
      main_query_text: mainQueryText || null,
      primary: primary.slice(0, 12).map((item) => item.display_query),
      secondary: secondary.slice(0, 12).map((item) => item.display_query),
      broad_context: broad.slice(0, 8).map((item) => item.display_query),
    },
  }

  return (
    <SeoShell
      projectId={projectId}
      title={`Генерация для ${nmId}`}
      subtitle={String(product.title || 'Черновик карточки на основе подтвержденных запросов и смысла товара.')}
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <ResearchPreviewBanner previewEnabled={previewEnabled} />
        {error && <Card><div style={{ color: '#b91c1c' }}>{error}</div></Card>}

        <Card>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, alignItems: 'center' }}>
            <div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                <StatusPill label={isConfirmed ? 'Запросы выбраны для генерации' : 'Запросы не выбраны для генерации'} tone={isConfirmed ? 'good' : 'warn'} />
                <StatusPill label={`${selected.length} выбрано`} tone={hasSelectedQueries ? 'good' : 'warn'} />
                <StatusPill label={mainQueryText ? `главный: ${mainQueryText}` : 'главный не выбран'} tone={hasMainQuery ? 'good' : 'warn'} />
                {seoRelevanceV2 ? (
                  <StatusPill label={`Lint V2 ${seoRelevanceV2.score}/100`} tone={relevanceTone(seoRelevanceV2)} />
                ) : seoRelevance ? (
                  <StatusPill label={`Lint ${seoRelevance.score}/100`} tone={relevanceTone(seoRelevance)} />
                ) : null}
                {latest?.status && <StatusPill label={`Текст: ${latest.status}`} tone="neutral" />}
                <QualityBadge
                  mode={generation?.quality_mode || latest?.quality_mode}
                  reasons={(generation?.degraded_reasons || latest?.degraded_reasons || []) as any}
                />
                <CategoryTierBadge tier={eligibilityTier} />
                {activeMatcherRunId ? (
                  <Link
                    href={`/app/project/${projectId}/seo/matcher-runs/${activeMatcherRunId}`}
                    style={{ fontSize: 12, color: '#2563eb' }}
                  >
                    matcher run #{activeMatcherRunId}
                  </Link>
                ) : null}
              </div>
              <h2 style={{ margin: 0, fontSize: 22 }}>Generation brief</h2>
              <div style={{ marginTop: 6, color: '#64748b' }}>
                Haiku 4.5 как основная модель, Sonnet 4.5 как fallback после validation failure.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <button type="button" onClick={load} disabled={loading} style={buttonStyle('light')}>
                {loading ? 'Обновляем...' : 'Обновить'}
              </button>
              <button
                type="button"
                onClick={runGeneration}
                disabled={!canGenerate}
                style={{ ...buttonStyle('primary'), opacity: canGenerate ? 1 : 0.52, cursor: canGenerate ? 'pointer' : 'not-allowed' }}
              >
                {generating ? 'Генерируем...' : 'Сгенерировать'}
              </button>
            </div>
          </div>
        </Card>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
          <Card>
            <h2 style={{ marginTop: 0 }}>Готовность</h2>
            <div style={{ display: 'grid', gap: 10 }}>
              {readiness.map((item) => (
                <div key={item.label} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, alignItems: 'center', borderTop: '1px solid #e2e8f0', paddingTop: 10 }}>
                  <div>
                    <div style={{ fontWeight: 800 }}>{item.label}</div>
                    <div style={{ color: '#64748b', marginTop: 2 }}>{item.detail}</div>
                  </div>
                  <StatusPill label={item.ok ? 'OK' : 'Нужно действие'} tone={item.ok ? 'good' : 'warn'} />
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h2 style={{ marginTop: 0 }}>Голос бренда</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(132px, 1fr))', gap: 8 }}>
              {brandVoices.map((voice) => (
                <button
                  key={voice}
                  type="button"
                  onClick={() => setBrandVoice(voice)}
                  style={{
                    ...buttonStyle(brandVoice === voice ? 'primary' : 'light'),
                    width: '100%',
                  }}
                >
                  {voice}
                </button>
              ))}
            </div>
            <div style={{ color: '#64748b', marginTop: 12 }}>
              Текущий режим: {brandVoice}
            </div>
          </Card>
        </div>

        <Card>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
            {(Object.keys(panelLabels) as Panel[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setPanel(item)}
                style={buttonStyle(panel === item ? 'primary' : 'light')}
              >
                {panelLabels[item]}
              </button>
            ))}
          </div>

          {panel === 'brief' && (
            <div style={{ display: 'grid', gap: 14 }}>
              <h2 style={{ margin: 0 }}>Собранный бриф</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
                <BriefBlock title="Факты товара" items={productFacts} empty="Факты пока не собраны. Запустите анализ товара." />
                <BriefBlock title="Стиль и аудитория" items={expressive} empty="Expressive context пока пуст." />
                <BriefBlock title="Нельзя обещать" items={negative} empty="Явных ограничений нет." />
              </div>
              <pre style={{ margin: 0, padding: 14, overflow: 'auto', background: '#0f172a', color: '#e2e8f0', borderRadius: 8, fontSize: 13, lineHeight: 1.45 }}>
                {JSON.stringify(briefPreview, null, 2)}
              </pre>
            </div>
          )}

          {panel === 'queries' && (
            <div style={{ display: 'grid', gap: 14 }}>
              <h2 style={{ margin: 0 }}>Запросы для prompt</h2>
              <div style={{ display: 'grid', gap: 8 }}>
                {selectedForPrompt.map((item) => (
                  <QueryChoice
                    key={item.normalized_query_text}
                    item={item}
                    checked={item.display_query === mainQueryText}
                    onPick={() => setMainQueryText(item.display_query)}
                  />
                ))}
              </div>
              {!selected.length && <div style={{ color: '#64748b' }}>Выбранных запросов пока нет.</div>}
            </div>
          )}

          {panel === 'rules' && (
            <div style={{ display: 'grid', gap: 12 }}>
              <h2 style={{ margin: 0 }}>Validation gates</h2>
              <RuleLine label="Название" value="до 60 символов, главный primary query в первых 1-3 словах" />
              <RuleLine label="Описание" value="до 5000 символов, ровно 6 блоков через пустую строку" />
              <RuleLine label="Запросы" value="selected query не чаще 3 раз, rejected/excluded запрещены" />
              <RuleLine label="Модели" value="Haiku 4.5 primary, Sonnet 4.5 fallback после ошибки валидации" />
              <RuleLine label="Статус" value="результат должен попасть в SeoContentVersion как draft/needs_review" />
            </div>
          )}

          {panel === 'draft' && (
            <div style={{ display: 'grid', gap: 14 }}>
              <h2 style={{ margin: 0 }}>Черновик карточки</h2>
              {generation && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <StatusPill label={generation.status === 'completed' ? 'Сохранено в draft' : 'Ошибка генерации'} tone={generation.status === 'completed' ? 'good' : 'bad'} />
                  <StatusPill label={generation.model_name || 'model unknown'} tone="neutral" />
                  <StatusPill label={`${generation.attempts} attempts`} tone="neutral" />
                  {generation.content_version_id && <StatusPill label={`content #${generation.content_version_id}`} tone="neutral" />}
                </div>
              )}
              {seoRelevanceV2 && <SeoRelevanceV2Panel report={seoRelevanceV2} />}
              {seoRelevance && <SeoRelevancePanel report={seoRelevance} />}
              {generation?.error_text && <div style={{ color: '#b91c1c' }}>{generation.error_text}</div>}
              {generationIssues.length > 0 && (
                <div style={{ display: 'grid', gap: 8 }}>
                  {generationIssues.map((issue, idx) => (
                    <div key={`${issue.check_name}-${idx}`} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}>
                      <StatusPill label={issue.severity} tone={issue.severity === 'error' ? 'bad' : 'warn'} />
                      <strong style={{ marginLeft: 8 }}>{issue.check_name}</strong>
                      <div style={{ color: '#475569', marginTop: 4 }}>{issue.message}</div>
                    </div>
                  ))}
                </div>
              )}
              <label style={{ display: 'block' }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Название</div>
                <input
                  readOnly
                  value={draftTitle}
                  placeholder="Появится после генерации"
                  style={{ width: '100%', padding: 12, border: '1px solid #cbd5e1', borderRadius: 8 }}
                />
              </label>
              {draftCharacteristics.length > 0 && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ fontWeight: 800 }}>Характеристики</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8 }}>
                    {draftCharacteristics.map((item, idx) => (
                      <div key={`${item.field}-${idx}`} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}>
                        <div style={{ fontWeight: 800 }}>{item.field}</div>
                        <div style={{ color: '#475569', marginTop: 3 }}>{item.value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <label style={{ display: 'block' }}>
                <div style={{ fontWeight: 800, marginBottom: 6 }}>Описание</div>
                <textarea
                  readOnly
                  value={draftDescription}
                  placeholder="Здесь будет 6-блочный draft описания"
                  style={{ width: '100%', minHeight: 220, padding: 12, border: '1px solid #cbd5e1', borderRadius: 8, resize: 'vertical' }}
                />
              </label>
            </div>
          )}
        </Card>

        <Card>
          <h2 style={{ marginTop: 0 }}>Human review</h2>
          <div style={{ color: '#64748b', fontSize: 13, marginBottom: 10 }}>
            Пишется в <code>seo_generation_human_review</code>. Accept нужен как часть promote-gate — без него promote вернёт 409.
          </div>
          {!activeContentVersionId ? (
            <div style={{ color: '#b45309' }}>Нет <code>content_version_id</code> — сначала выполните генерацию.</div>
          ) : (
            <div style={{ display: 'grid', gap: 10, maxWidth: 720 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
                <label>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Reviewer</div>
                  <input
                    value={reviewReviewer}
                    onChange={(e) => setReviewReviewer(e.target.value)}
                    placeholder="operator"
                    style={{ width: '100%', padding: 8, border: '1px solid #cbd5e1', borderRadius: 6 }}
                  />
                </label>
                <label>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Verdict</div>
                  <select
                    value={reviewVerdict}
                    onChange={(e) => setReviewVerdict(e.target.value as typeof reviewVerdict)}
                    style={{ width: '100%', padding: 8, border: '1px solid #cbd5e1', borderRadius: 6 }}
                  >
                    <option value="accept">accept</option>
                    <option value="reject">reject</option>
                    <option value="needs_changes">needs_changes</option>
                  </select>
                </label>
              </div>
              <label>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>Notes</div>
                <textarea
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  placeholder="опционально"
                  rows={2}
                  style={{ width: '100%', padding: 8, border: '1px solid #cbd5e1', borderRadius: 6 }}
                />
              </label>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <button type="button" onClick={submitHumanReview} disabled={reviewBusy} style={buttonStyle('primary')}>
                  {reviewBusy ? 'Сохраняем...' : 'Записать review'}
                </button>
                {reviewMsg ? <span style={{ color: reviewMsg.startsWith('Human review') ? '#047857' : '#b91c1c', fontSize: 13 }}>{reviewMsg}</span> : null}
              </div>
            </div>
          )}
        </Card>

        <Card>
          <h2 style={{ marginTop: 0 }}>Promote</h2>
          <div style={{ color: '#64748b', fontSize: 13, marginBottom: 10, display: 'grid', gap: 2 }}>
            <div><strong>preview → candidate:</strong> нужен <code>eligibility_tier ∈ {'{evaluated, approved}'}</code> и accepted human review.</div>
            <div><strong>candidate → approved:</strong> нужен <code>eligibility_tier == approved</code> и ещё один accepted human review.</div>
            <div><strong>approved → published:</strong> всегда <code>409 production_generation_off</code>. Этот путь в Iteration 2 заблокирован on-purpose.</div>
          </div>
          {!activeContentVersionId ? (
            <div style={{ color: '#b45309' }}>Нет <code>content_version_id</code> — сначала выполните генерацию.</div>
          ) : (
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <select
                value={promoteTarget}
                onChange={(e) => setPromoteTarget(e.target.value as typeof promoteTarget)}
                style={{ padding: 8, border: '1px solid #cbd5e1', borderRadius: 6 }}
              >
                <option value="candidate">candidate</option>
                <option value="approved">approved</option>
                <option value="published">published (должен вернуть 409)</option>
              </select>
              <button type="button" onClick={submitPromote} disabled={promoteBusy} style={buttonStyle('primary')}>
                {promoteBusy ? 'Promote...' : `Promote → ${promoteTarget}`}
              </button>
              {promoteMsg ? (
                <span style={{ color: promoteMsg.startsWith('Promote OK') ? '#047857' : '#b91c1c', fontSize: 13, overflowWrap: 'anywhere' }}>
                  {promoteMsg}
                </span>
              ) : null}
            </div>
          )}
        </Card>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link href={`/app/project/${projectId}/seo/products/${nmId}?category_id=${categoryId}`} style={buttonStyle('light')}>К товару</Link>
          <Link href={`/app/project/${projectId}/seo/products/${nmId}/queries?category_id=${categoryId}`} style={buttonStyle('ghost')}>К запросам</Link>
          <Link href={`/app/project/${projectId}/seo/products/${nmId}/compare?category_id=${categoryId}`} style={buttonStyle('ghost')}>Compare</Link>
          {activeMatcherRunId ? (
            <Link href={`/app/project/${projectId}/seo/matcher-runs/${activeMatcherRunId}`} style={buttonStyle('ghost')}>
              Matcher run viewer
            </Link>
          ) : null}
        </div>
      </div>
    </SeoShell>
  )
}

function BriefBlock({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 14, minHeight: 132 }}>
      <h3 style={{ margin: '0 0 10px', fontSize: 16 }}>{title}</h3>
      {items.length ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {items.map((item, idx) => <StatusPill key={`${item}-${idx}`} label={item} />)}
        </div>
      ) : (
        <div style={{ color: '#64748b' }}>{empty}</div>
      )}
    </div>
  )
}

function QueryChoice({ item, checked, onPick }: { item: SeoQuerySelectionItem; checked: boolean; onPick: () => void }) {
  return (
    <label
      style={{
        display: 'grid',
        gridTemplateColumns: '24px minmax(0, 1fr) auto',
        gap: 10,
        alignItems: 'center',
        border: checked ? '1px solid #0f172a' : '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 10,
      }}
    >
      <input type="radio" name="main-query" checked={checked} onChange={onPick} style={{ width: 18, height: 18 }} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 800, overflowWrap: 'anywhere' }}>{item.display_query}</div>
        <div style={{ color: '#64748b', marginTop: 3 }}>
          score {item.score.toFixed(3)}{item.ranking_value_used ? ` · частотность ${item.ranking_value_used}` : ''}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        <StatusPill label={bucketLabels[item.bucket] || item.bucket} tone={queryTone(item.bucket)} />
        {checked && <StatusPill label="Главный" tone="good" />}
      </div>
    </label>
  )
}

function SeoRelevanceV2Panel({ report }: { report: SeoRelevanceV2Report }) {
  const weak = report.query_scores.filter((item) => item.score < 55).slice(0, 8)
  const strong = report.query_scores.filter((item) => item.score >= 70).length
  return (
    <div style={{ border: '1px solid #cbd5e1', borderRadius: 8, padding: 14, display: 'grid', gap: 12 }}>
      <h3 style={{ margin: 0 }}>
        Internal lint (relevance V2)
        <span style={{ color: '#64748b', fontWeight: 500, fontSize: 13, marginLeft: 8 }}>
          — диагностический сигнал, не является quality gate
        </span>
      </h3>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <StatusPill label={`Lint V2 ${report.score}/100`} tone={relevanceTone(report)} />
        <StatusPill label={report.grade} tone={relevanceTone(report)} />
        <StatusPill label={`${strong}/${report.evaluated_queries_count} сильных`} tone="neutral" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
        <Metric label="Intent fit" value={`${Math.round(report.intent_fit * 100)}%`} />
        <Metric label="Семантика" value={`${Math.round(report.semantic_similarity * 100)}%`} />
        <Metric label="Лексика" value={`${Math.round(report.lexical_relevance * 100)}%`} />
        <Metric label="Зоны текста" value={`${Math.round(report.zone_placement * 100)}%`} />
        <Metric label="Естественность" value={`${Math.round(report.naturalness * 100)}%`} />
        <Metric label="Фактическость" value={`${Math.round(report.product_truthfulness * 100)}%`} />
      </div>
      {report.notes.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {report.notes.map((note) => <StatusPill key={note} label={note} tone="neutral" />)}
        </div>
      )}
      {weak.length > 0 && (
        <div>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Слабые смысловые совпадения</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {weak.map((item) => (
              <div key={`${item.bucket}-${item.query}`} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <StatusPill label={`${item.score}/100`} tone="warn" />
                  <strong>{item.query}</strong>
                  <StatusPill label={bucketLabels[item.bucket] || item.bucket} tone={queryTone(item.bucket)} />
                </div>
                {item.unsupported_atoms.length > 0 && (
                  <div style={{ color: '#64748b', marginTop: 6, overflowWrap: 'anywhere' }}>
                    Не раскрыто: {item.unsupported_atoms.slice(0, 5).join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SeoRelevancePanel({ report }: { report: SeoRelevanceReport }) {
  const missed = report.query_coverage.filter((item) => !item.found).slice(0, 8)
  const covered = report.query_coverage.filter((item) => item.found).length
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 14, display: 'grid', gap: 12 }}>
      <h3 style={{ margin: 0 }}>
        Internal lint (relevance)
        <span style={{ color: '#64748b', fontWeight: 500, fontSize: 13, marginLeft: 8 }}>
          — диагностический сигнал, не является quality gate
        </span>
      </h3>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <StatusPill label={`Lint ${report.score}/100`} tone={relevanceTone(report)} />
        <StatusPill label={report.grade} tone={relevanceTone(report)} />
        <StatusPill label={`${covered}/${report.selected_queries_count} покрыто`} tone="neutral" />
        <StatusPill label={`${Math.round(report.weighted_coverage * 100)}% weighted`} tone="neutral" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
        <Metric label="Главный запрос" value={report.main_query_text || 'не выбран'} />
        <Metric label="В названии" value={report.main_query_in_title ? 'да' : 'нет'} />
        <Metric label="В первых 3 словах" value={report.main_query_in_title_start ? 'да' : 'нет'} />
        <Metric label="Запросов в описании" value={String(report.description_queries_count)} />
      </div>
      {report.notes.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {report.notes.map((note) => <StatusPill key={note} label={note} tone="warn" />)}
        </div>
      )}
      {missed.length > 0 && (
        <div>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Не найдены в тексте</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {missed.map((item) => <StatusPill key={`${item.bucket}-${item.query}`} label={item.query} tone={item.bucket === 'primary' ? 'bad' : 'warn'} />)}
          </div>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}>
      <div style={{ color: '#64748b', fontSize: 13 }}>{label}</div>
      <div style={{ fontWeight: 900, marginTop: 3, overflowWrap: 'anywhere' }}>{value}</div>
    </div>
  )
}

function RuleLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '180px minmax(0, 1fr)', gap: 12, borderTop: '1px solid #e2e8f0', paddingTop: 10 }}>
      <div style={{ fontWeight: 800 }}>{label}</div>
      <div style={{ color: '#475569' }}>{value}</div>
    </div>
  )
}
