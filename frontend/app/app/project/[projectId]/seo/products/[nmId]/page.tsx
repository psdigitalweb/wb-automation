'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoCompareMatcher,
  getSeoEvalRuns,
  getSeoProductSummary,
  postSeoProductAnalysisRun,
  type SeoMatcherCompareResponse,
  type SeoProductSummaryResponse,
} from '@/lib/apiClient'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../../_components/SeoShell'
import { QualityBadge } from '../../_components/QualityBadge'
import { ApprovalStateBadge, CategoryTierBadge } from '../../_components/CategoryTierBadge'

export default function SeoProductPage({ params }: { params: { projectId: string; nmId: string } }) {
  const { projectId, nmId } = params
  const searchParams = useSearchParams()
  const categoryId = searchParams.get('category_id')
  const [summary, setSummary] = useState<SeoProductSummaryResponse | null>(null)
  const [eligibilityTier, setEligibilityTier] = useState<string | null>(null)
  const [cmp, setCmp] = useState<SeoMatcherCompareResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  usePageTitle(`SEO: ${nmId}`, projectId)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const resolvedCatRaw = categoryId ? Number(categoryId) : undefined
      const summaryPromise = getSeoProductSummary(projectId, Number(nmId), { category_id: resolvedCatRaw })
      const summaryData = await summaryPromise
      setSummary(summaryData)
      const resolvedCat = summaryData.category_id || resolvedCatRaw
      if (resolvedCat) {
        const [evalRuns, compareRes] = await Promise.all([
          getSeoEvalRuns(projectId, { category_id: resolvedCat, limit: 1 }).catch(() => null),
          getSeoCompareMatcher(projectId, { category_id: resolvedCat, nm_id: Number(nmId) }).catch(() => null),
        ])
        setEligibilityTier(evalRuns?.eligibility_tier || 'preview_only')
        setCmp(compareRes)
      }
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId, nmId, categoryId])

  const analyze = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await postSeoProductAnalysisRun(projectId, Number(nmId), {
        category_id: summary?.category_id || (categoryId ? Number(categoryId) : undefined),
        force_refresh: false,
        include_vision: true,
      })
      await load()
      if (result.warnings.length) setError(`Анализ завершен с предупреждениями: ${result.warnings.join(', ')}`)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const resolvedCategory = summary?.category_id || categoryId
  const candidateMeta = (cmp?.candidate?.meta || {}) as Record<string, any>
  const currentMeta = (cmp?.current?.meta || {}) as Record<string, any>
  const matcherRunId = candidateMeta.matcher_run_id as number | undefined
  const approvalState = candidateMeta.approval_state as string | undefined
  const trustState = candidateMeta.trust_state as string | undefined
  const categoryProfileVersion = candidateMeta.category_profile_version as string | undefined
  const candidateQuerySetId = candidateMeta.query_set_id as number | undefined
  const currentQuerySetId = currentMeta.query_set_id as number | undefined

  return (
    <SeoShell projectId={projectId} title={`Товар ${nmId}`} subtitle={summary?.product?.title || 'Анализ товара для SEO-подбора.'}>
      <div style={{ display: 'grid', gap: 16 }}>
        {error && <Card><div style={{ color: error.startsWith('Анализ завершен') ? '#92400e' : '#b91c1c' }}>{error}</div></Card>}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              {summary && <StatusPill label={summary.product_status_label} tone={summary.product_status_label === 'Готов к подбору' ? 'good' : 'warn'} />}
              {summary && <StatusPill label={summary.vision_status_label} tone={summary.vision_status_label === 'Фото учтены' ? 'good' : 'neutral'} />}
              {summary && <StatusPill label={summary.category_status_label} tone={summary.category_status_label === 'Готова к подбору' ? 'good' : 'warn'} />}
              <CategoryTierBadge tier={eligibilityTier} profileVersion={categoryProfileVersion || null} />
              {summary?.quality_mode && (
                <QualityBadge mode={summary.quality_mode} reasons={(summary.degraded_reasons || []) as any} />
              )}
              <ApprovalStateBadge approvalState={approvalState} trustState={trustState} />
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <button type="button" onClick={analyze} disabled={loading} style={buttonStyle('primary')}>{loading ? 'Анализируем...' : 'Проанализировать товар'}</button>
              {resolvedCategory && <Link href={`/app/project/${projectId}/seo/products/${nmId}/queries?category_id=${resolvedCategory}`} style={buttonStyle('light')}>Подобрать запросы</Link>}
              {resolvedCategory && <Link href={`/app/project/${projectId}/seo/products/${nmId}/compare?category_id=${resolvedCategory}`} style={buttonStyle('light')}>Compare</Link>}
              {resolvedCategory && <Link href={`/app/project/${projectId}/seo/products/${nmId}/generation?category_id=${resolvedCategory}`} style={buttonStyle('ghost')}>Генерация</Link>}
            </div>
          </div>
          {(matcherRunId || candidateQuerySetId || currentQuerySetId) && (
            <div style={{ marginTop: 12, borderTop: '1px solid #e2e8f0', paddingTop: 12, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', fontSize: 13, color: '#475569' }}>
              {matcherRunId ? (
                <span>
                  Последний matcher run:{' '}
                  <Link href={`/app/project/${projectId}/seo/matcher-runs/${matcherRunId}`} style={{ color: '#2563eb' }}>
                    #{matcherRunId}
                  </Link>
                </span>
              ) : (
                <span>Matcher run ещё не запускался — запустите его на странице «Запросы».</span>
              )}
              {currentQuerySetId && <span>current query_set: #{currentQuerySetId}</span>}
              {candidateQuerySetId && <span>candidate query_set: #{candidateQuerySetId}</span>}
              {categoryProfileVersion && <span>profile v{categoryProfileVersion}</span>}
            </div>
          )}
        </Card>
        {loading && !summary ? <Card>Загружаем...</Card> : null}
        {summary?.blocks.map((block) => (
          <Card key={block.title}>
            <h2 style={{ marginTop: 0 }}>{block.title}</h2>
            {block.items.length ? (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {block.items.map((item, idx) => <StatusPill key={`${item}-${idx}`} label={item} />)}
              </div>
            ) : (
              <div style={{ color: '#64748b' }}>{block.empty_text}</div>
            )}
          </Card>
        ))}
      </div>
    </SeoShell>
  )
}
