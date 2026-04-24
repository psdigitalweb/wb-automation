'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoCompareMatcher,
  getSeoEvalRuns,
  getSeoQuerySelection,
  postSeoCandidateApproval,
  postSeoCandidateProject,
  postSeoQuerySelectionRun,
  putSeoQuerySelection,
  type SeoCandidateProjectResponse,
  type SeoMatcherCompareResponse,
  type SeoQuerySelectionItem,
  type SeoQuerySetResponse,
} from '@/lib/apiClient'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../../../_components/SeoShell'
import { QualityBadge } from '../../../_components/QualityBadge'
import { ApprovalStateBadge, CategoryTierBadge } from '../../../_components/CategoryTierBadge'

const topBucketOrder = ['primary', 'secondary', 'broad'] as const
const bucketLabels: Record<string, string> = {
  primary: 'Лучшие',
  secondary: 'Подходящие',
  broad: 'Слишком общие',
  rejected: 'Не подходят',
}
const querySelectionLimit = 400

const defaultSelectionState = (item: SeoQuerySelectionItem): SeoQuerySelectionItem['selection_state'] => {
  if (item.selection_state) return item.selection_state
  return item.bucket === 'primary' || item.bucket === 'secondary' ? 'auto_selected' : 'excluded'
}

const isSelectedState = (state: SeoQuerySelectionItem['selection_state'] | undefined) => state === 'auto_selected' || state === 'pinned'

const byFrequencyDesc = (left: SeoQuerySelectionItem, right: SeoQuerySelectionItem) => {
  const rightFrequency = right.ranking_value_used ?? -1
  const leftFrequency = left.ranking_value_used ?? -1
  if (rightFrequency !== leftFrequency) return rightFrequency - leftFrequency
  if (right.score !== left.score) return right.score - left.score
  return left.display_query.localeCompare(right.display_query, 'ru')
}

export default function SeoProductQueriesPage({ params }: { params: { projectId: string; nmId: string } }) {
  const { projectId, nmId } = params
  const searchParams = useSearchParams()
  const categoryId = searchParams.get('category_id') || ''
  const [querySet, setQuerySet] = useState<SeoQuerySetResponse | null>(null)
  const [states, setStates] = useState<Record<string, SeoQuerySelectionItem['selection_state']>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [candidateInfo, setCandidateInfo] = useState<SeoCandidateProjectResponse | null>(null)
  const [cmp, setCmp] = useState<SeoMatcherCompareResponse | null>(null)
  const [eligibilityTier, setEligibilityTier] = useState<string | null>(null)
  const [candidateBusy, setCandidateBusy] = useState(false)
  const [candidateMsg, setCandidateMsg] = useState<string | null>(null)
  usePageTitle(`SEO запросы: ${nmId}`, projectId)

  const load = async () => {
    if (!categoryId) return
    setLoading(true)
    setError(null)
    try {
      const [data, compareRes, evalRuns] = await Promise.all([
        getSeoQuerySelection(projectId, Number(nmId), { category_id: Number(categoryId) }),
        getSeoCompareMatcher(projectId, { category_id: Number(categoryId), nm_id: Number(nmId) }).catch(() => null),
        getSeoEvalRuns(projectId, { category_id: Number(categoryId), limit: 1 }).catch(() => null),
      ])
      setQuerySet(data)
      setStates(Object.fromEntries(data.items.map((item) => [item.normalized_query_text, defaultSelectionState(item)])))
      setCmp(compareRes)
      setEligibilityTier(evalRuns?.eligibility_tier || 'preview_only')
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId, nmId, categoryId])

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await postSeoQuerySelectionRun(projectId, Number(nmId), { category_id: Number(categoryId), limit: querySelectionLimit, include_rejected: true })
      setQuerySet(data)
      setStates(Object.fromEntries(data.items.map((item) => [item.normalized_query_text, defaultSelectionState(item)])))
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const refreshCandidate = async () => {
    if (!categoryId) return
    setCandidateBusy(true)
    setCandidateMsg(null)
    setError(null)
    try {
      const res = await postSeoCandidateProject(projectId, { category_id: Number(categoryId), nm_id: Number(nmId) })
      setCandidateInfo(res)
      setCandidateMsg(`Candidate обновлён: query_set #${res.query_set_id}, matcher_run #${res.matcher_run_id}, ${res.items_written} строк.`)
      const compareRes = await getSeoCompareMatcher(projectId, { category_id: Number(categoryId), nm_id: Number(nmId) }).catch(() => null)
      setCmp(compareRes)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setCandidateBusy(false)
    }
  }

  const setApprovalState = async (next: 'draft' | 'preview' | 'candidate' | 'approved') => {
    const candidateMeta = (cmp?.candidate?.meta || {}) as Record<string, any>
    const querySetId = (candidateInfo?.query_set_id as number | undefined) || (candidateMeta.query_set_id as number | undefined)
    if (!querySetId) {
      setError('Нет candidate query_set — сначала нажмите «Обновить candidate».')
      return
    }
    setCandidateBusy(true)
    setCandidateMsg(null)
    setError(null)
    try {
      const res = await postSeoCandidateApproval(projectId, querySetId, { approval_state: next })
      setCandidateMsg(`approval_state = ${res.approval_state}, trust_state = ${res.trust_state}.`)
      const compareRes = await getSeoCompareMatcher(projectId, { category_id: Number(categoryId), nm_id: Number(nmId) }).catch(() => null)
      setCmp(compareRes)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setCandidateBusy(false)
    }
  }

  const save = async (status: 'draft' | 'confirmed') => {
    setLoading(true)
    setError(null)
    try {
      const data = await putSeoQuerySelection(projectId, Number(nmId), {
        category_id: Number(categoryId),
        status,
        items: Object.entries(states).map(([normalized_query_text, selection_state]) => ({ normalized_query_text, selection_state })),
      })
      setQuerySet(data)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  const grouped = useMemo(() => {
    const result: Record<string, SeoQuerySelectionItem[]> = { primary: [], secondary: [], broad: [], rejected: [] }
    for (const item of querySet?.items || []) result[item.bucket]?.push(item)
    for (const bucket of Object.keys(result)) result[bucket].sort(byFrequencyDesc)
    return result
  }, [querySet])
  const selectedCount = useMemo(
    () => (querySet?.items || []).filter((item) => isSelectedState(states[item.normalized_query_text] || defaultSelectionState(item))).length,
    [querySet, states],
  )
  const querySetLabel = querySet?.status === 'confirmed' ? 'Выбран для генерации' : querySet?.items.length ? 'Выбор сохранен' : 'Нет подбора'

  const renderQueryItem = (item: SeoQuerySelectionItem) => {
    return (
      <div key={item.normalized_query_text} style={{ display: 'grid', gap: 6, borderTop: '1px solid #e2e8f0', paddingTop: 10 }}>
        <label style={{ display: 'grid', gridTemplateColumns: '18px minmax(0, 1fr)', alignItems: 'start', gap: 10, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={isSelectedState(states[item.normalized_query_text] || defaultSelectionState(item))}
            onChange={(e) => {
              setStates((prev) => {
                const previous = prev[item.normalized_query_text] || defaultSelectionState(item)
                return {
                  ...prev,
                  [item.normalized_query_text]: e.target.checked ? (previous === 'pinned' ? 'pinned' : 'auto_selected') : 'excluded',
                }
              })
            }}
            style={{ width: 18, height: 18, marginTop: 2 }}
          />
          <strong style={{ lineHeight: 1.35, overflowWrap: 'anywhere' }}>{item.display_query}</strong>
        </label>
        <div style={{ color: '#64748b', fontSize: 14, paddingLeft: 28 }}>
          score {item.score.toFixed(3)}{item.ranking_value_used ? ` · частотность ${item.ranking_value_used}` : ''}
        </div>
      </div>
    )
  }

  const renderBucketCard = (bucket: string, items = grouped[bucket], contentColumns = '1fr') => (
    <Card key={bucket}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>{bucketLabels[bucket]}</h2>
        <span style={{ color: '#64748b', fontWeight: 700 }}>{items.length}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: contentColumns, gap: 10, alignItems: 'start' }}>
        {items.map(renderQueryItem)}
        {!items.length && <div style={{ color: '#64748b' }}>Нет запросов в этом блоке.</div>}
      </div>
    </Card>
  )

  const candidateMeta = (cmp?.candidate?.meta || {}) as Record<string, any>
  const candidateMatcherRunId = (candidateInfo?.matcher_run_id as number | undefined) || (candidateMeta.matcher_run_id as number | undefined)
  const candidateQuerySetId = (candidateInfo?.query_set_id as number | undefined) || (candidateMeta.query_set_id as number | undefined)
  const candidateApprovalState = (candidateInfo?.approval_state as string | undefined) || (candidateMeta.approval_state as string | undefined)
  const candidateTrustState = (candidateInfo?.trust_state as string | undefined) || (candidateMeta.trust_state as string | undefined)
  const candidateProfileVersion = (candidateInfo?.category_profile_version as string | undefined) || (candidateMeta.category_profile_version as string | undefined)
  const candidateQualityMode = (candidateMeta.quality_mode as string | undefined)

  return (
    <SeoShell projectId={projectId} title={`Подбор запросов для ${nmId}`} subtitle="Current path (confirmed) и candidate path (matcher_v2 + projection) живут параллельно.">
      <div style={{ display: 'grid', gap: 16 }}>
        {error && <Card><div style={{ color: '#b91c1c' }}>{error}</div></Card>}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 16 }}>Candidate (matcher_v2)</strong>
              <CategoryTierBadge tier={eligibilityTier} profileVersion={candidateProfileVersion || null} />
              <ApprovalStateBadge approvalState={candidateApprovalState} trustState={candidateTrustState} />
              <QualityBadge mode={candidateQualityMode as any} />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button type="button" onClick={refreshCandidate} disabled={candidateBusy || !categoryId} style={buttonStyle('primary')}>
                {candidateBusy ? 'Работаем...' : 'Обновить candidate'}
              </button>
              {candidateMatcherRunId ? (
                <Link href={`/app/project/${projectId}/seo/matcher-runs/${candidateMatcherRunId}`} style={buttonStyle('light')}>
                  Matcher run #{candidateMatcherRunId}
                </Link>
              ) : null}
              <Link href={`/app/project/${projectId}/seo/products/${nmId}/compare?category_id=${categoryId}`} style={buttonStyle('light')}>Compare</Link>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', fontSize: 13, color: '#475569' }}>
            {candidateQuerySetId ? <span>query_set_id: #{candidateQuerySetId}</span> : <span>candidate ещё не спроецирован</span>}
            {candidateProfileVersion ? <span>profile v{candidateProfileVersion}</span> : null}
            {candidateMsg ? <span style={{ color: '#047857' }}>{candidateMsg}</span> : null}
          </div>
          {candidateQuerySetId ? (
            <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ color: '#64748b', fontSize: 13 }}>Approval:</span>
              {(['draft', 'preview', 'candidate', 'approved'] as const).map((stateValue) => (
                <button
                  key={stateValue}
                  type="button"
                  onClick={() => setApprovalState(stateValue)}
                  disabled={candidateBusy}
                  style={buttonStyle(candidateApprovalState === stateValue ? 'primary' : 'light')}
                >
                  {stateValue}
                </button>
              ))}
              <span style={{ color: '#64748b', fontSize: 12, marginLeft: 8 }}>
                trust_state пишется только eval-ом; здесь им не управляем.
              </span>
            </div>
          ) : null}
        </Card>

        <Card>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 16 }}>Current (legacy path)</strong>
              <StatusPill label={querySetLabel} tone={querySet?.status === 'confirmed' ? 'good' : 'neutral'} />
              <span style={{ color: '#64748b' }}>{querySet?.items.length || 0} запросов</span>
              <span style={{ color: '#64748b' }}>выбрано {selectedCount}</span>
              <QualityBadge
                mode={querySet?.quality_mode}
                reasons={(querySet?.degraded_reasons || []) as any}
              />
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="button" onClick={run} disabled={loading || !categoryId} style={buttonStyle('primary')}>{loading ? 'Работаем...' : 'Подобрать запросы'}</button>
              <button type="button" onClick={() => save('draft')} disabled={loading || !querySet?.items.length} style={buttonStyle('light')}>Сохранить выбор</button>
              <button type="button" onClick={() => save('confirmed')} disabled={loading || !querySet?.items.length} style={buttonStyle('light')}>Использовать для генерации</button>
              <Link href={`/app/project/${projectId}/seo/products/${nmId}/generation?category_id=${categoryId}`} style={buttonStyle('ghost')}>К генерации</Link>
            </div>
          </div>
        </Card>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(280px, 1fr))', gap: 16, alignItems: 'start', overflowX: 'auto', paddingBottom: 4 }}>
          {topBucketOrder.map((bucket) => renderBucketCard(bucket))}
        </div>
        {renderBucketCard('rejected', grouped.rejected, 'repeat(auto-fit, minmax(300px, 1fr))')}
      </div>
    </SeoShell>
  )
}
