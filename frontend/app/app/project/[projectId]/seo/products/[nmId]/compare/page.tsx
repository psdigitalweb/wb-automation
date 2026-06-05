'use client'

/**
 * Matcher compare page (Iteration 2, compare).
 *
 * Side-by-side view of the legacy persisted query-set vs. the candidate
 * matcher_v2 trace for a single SKU. Read-only: this page never mutates
 * matcher state. Operators can capture a verdict via
 * ``POST /seo/compare/matcher/verdict`` which writes to the append-only
 * ``seo_compare_verdicts`` table.
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoCompareMatcher,
  postSeoCompareVerdict,
  type SeoMatcherCompareResponse,
} from '@/lib/apiClient'
import { Card, SeoShell, buttonStyle, normalizeError } from '../../../_components/SeoShell'
import { CategoryTierBadge } from '../../../_components/CategoryTierBadge'

type StatusFilter =
  | 'all'
  | 'diff'
  | 'bucket_changed'
  | 'primary_rejected_flip'
  | 'only_in_current'
  | 'only_in_candidate'
  | 'same'

type BucketFilter = 'any' | 'primary' | 'secondary' | 'broad' | 'rejected'
type BucketScope = 'either' | 'current' | 'candidate' | 'both'

function Chip({
  active,
  onClick,
  children,
  accent,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  accent?: string
}) {
  const borderActive = accent || '#0f172a'
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        border: '1px solid ' + (active ? borderActive : '#d1d5db'),
        background: active ? borderActive : 'white',
        color: active ? 'white' : '#0f172a',
        padding: '4px 10px',
        borderRadius: 999,
        fontSize: 12,
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  )
}

function CompareFilters({
  statusFilter,
  setStatusFilter,
  bucketFilter,
  setBucketFilter,
  bucketScope,
  setBucketScope,
  queryFilter,
  setQueryFilter,
  statusCounts,
  bucketCounts,
  total,
}: {
  statusFilter: StatusFilter
  setStatusFilter: (v: StatusFilter) => void
  bucketFilter: BucketFilter
  setBucketFilter: (v: BucketFilter) => void
  bucketScope: BucketScope
  setBucketScope: (v: BucketScope) => void
  queryFilter: string
  setQueryFilter: (v: string) => void
  statusCounts: Record<string, number>
  bucketCounts: Record<BucketFilter, number>
  total: number
}) {
  const statusOptions: Array<{ id: StatusFilter; label: string; count?: number }> = [
    { id: 'diff', label: 'Только расхождения', count: total - (statusCounts.same || 0) },
    { id: 'bucket_changed', label: 'bucket_changed', count: statusCounts.bucket_changed },
    { id: 'primary_rejected_flip', label: 'primary↔rejected', count: statusCounts.primary_rejected_flip },
    { id: 'only_in_current', label: 'only_in_current', count: statusCounts.only_in_current },
    { id: 'only_in_candidate', label: 'only_in_candidate', count: statusCounts.only_in_candidate },
    { id: 'same', label: 'same', count: statusCounts.same },
    { id: 'all', label: `Все (${total})` },
  ]
  const bucketOptions: Array<{ id: BucketFilter; label: string; accent?: string }> = [
    { id: 'any', label: 'Любой' },
    { id: 'primary', label: 'primary', accent: '#047857' },
    { id: 'secondary', label: 'secondary', accent: '#1d4ed8' },
    { id: 'broad', label: 'broad', accent: '#92400e' },
    { id: 'rejected', label: 'rejected', accent: '#b91c1c' },
  ]
  const scopeOptions: Array<{ id: BucketScope; label: string }> = [
    { id: 'either', label: 'в любой колонке' },
    { id: 'current', label: 'только Current' },
    { id: 'candidate', label: 'только Candidate' },
    { id: 'both', label: 'в обеих' },
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#6b7280', minWidth: 62 }}>Статус:</span>
        {statusOptions.map((opt) => (
          <Chip
            key={opt.id}
            active={statusFilter === opt.id}
            onClick={() => setStatusFilter(opt.id)}
          >
            {opt.label}
            {typeof opt.count === 'number' ? (
              <span style={{ marginLeft: 6, opacity: 0.7 }}>· {opt.count}</span>
            ) : null}
          </Chip>
        ))}
        <input
          type="text"
          value={queryFilter}
          onChange={(e) => setQueryFilter(e.target.value)}
          placeholder="Поиск по запросу…"
          style={{
            marginLeft: 'auto',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            padding: '5px 10px',
            fontSize: 12,
            minWidth: 220,
          }}
        />
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#6b7280', minWidth: 62 }}>Бакет:</span>
        {bucketOptions.map((opt) => (
          <Chip
            key={opt.id}
            active={bucketFilter === opt.id}
            onClick={() => setBucketFilter(opt.id)}
            accent={opt.accent}
          >
            {opt.label}
            {opt.id !== 'any' ? (
              <span style={{ marginLeft: 6, opacity: 0.7 }}>· {bucketCounts[opt.id] ?? 0}</span>
            ) : null}
          </Chip>
        ))}
        <span
          style={{
            fontSize: 12,
            color: '#6b7280',
            marginLeft: 8,
            opacity: bucketFilter === 'any' ? 0.4 : 1,
          }}
        >
          совпадение:
        </span>
        {scopeOptions.map((opt) => (
          <Chip
            key={opt.id}
            active={bucketScope === opt.id}
            onClick={() => {
              if (bucketFilter !== 'any') setBucketScope(opt.id)
            }}
          >
            {opt.label}
          </Chip>
        ))}
      </div>
    </div>
  )
}

function bucketColor(bucket: string | null | undefined) {
  if (!bucket) return '#9ca3af'
  const map: Record<string, string> = {
    primary: '#047857',
    secondary: '#1d4ed8',
    broad: '#92400e',
    rejected: '#b91c1c',
  }
  return map[bucket] || '#334155'
}

export default function SeoMatcherComparePage({
  params,
  searchParams,
}: {
  params: { projectId: string; nmId: string }
  searchParams?: { category_id?: string }
}) {
  const { projectId, nmId } = params
  const categoryIdRaw = searchParams?.category_id || '812'
  const [cmp, setCmp] = useState<SeoMatcherCompareResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [verdictState, setVerdictState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [notes, setNotes] = useState('')
  const [statusFilter, setStatusFilter] = useState<
    'all' | 'diff' | 'bucket_changed' | 'primary_rejected_flip' | 'only_in_current' | 'only_in_candidate' | 'same'
  >('diff')
  const [bucketFilter, setBucketFilter] = useState<BucketFilter>('any')
  const [bucketScope, setBucketScope] = useState<BucketScope>('either')
  const [queryFilter, setQueryFilter] = useState('')
  const [rowLimit, setRowLimit] = useState(300)
  usePageTitle(`SEO compare · SKU ${nmId}`, projectId)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getSeoCompareMatcher(projectId, {
        category_id: Number(categoryIdRaw),
        nm_id: Number(nmId),
      })
      setCmp(res)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }, [projectId, nmId, categoryIdRaw])

  useEffect(() => {
    load()
  }, [load])

  const onVerdict = async (verdict: 'accept' | 'reject' | 'needs_changes') => {
    if (!cmp) return
    setVerdictState('saving')
    try {
      await postSeoCompareVerdict(projectId, 'matcher', {
        subject_id: Number(cmp.candidate?.meta?.matcher_run_id || 0),
        related_id: Number(cmp.current?.meta?.query_set_id || 0) || undefined,
        verdict,
        notes: notes || undefined,
      })
      setVerdictState('saved')
      setTimeout(() => setVerdictState('idle'), 2500)
    } catch (e) {
      setError(normalizeError(e))
      setVerdictState('idle')
    }
  }

  return (
    <SeoShell projectId={projectId} title={`SKU ${nmId} — сравнение matcher'ов`}>
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span>Категория: <strong>{categoryIdRaw}</strong></span>
          <Link
            href={`/app/project/${projectId}/seo/products/${nmId}?category_id=${categoryIdRaw}#seo-query-selection`}
            style={{ color: '#2563eb', fontSize: 13 }}
          >
            ← Поиск. запросы
          </Link>
          <Link
            href={`/app/project/${projectId}/seo/categories/${categoryIdRaw}/eval`}
            style={{ color: '#2563eb', fontSize: 13 }}
          >
            Eval →
          </Link>
        </div>
      </Card>

      {error ? (
        <Card>
          <div style={{ color: '#b91c1c' }}>{error}</div>
        </Card>
      ) : null}

      {cmp ? (
        <Card>
          <h3 style={{ marginTop: 0 }}>Итог по SKU</h3>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <CategoryTierBadge
              tier={cmp.candidate?.meta?.quality_mode}
              profileVersion={cmp.candidate?.meta?.category_profile_version}
            />
            <span>
              Изменений ведра: <strong>{cmp.diff?.bucket_changes ?? 0}</strong>
              {' '}/ всего сравнено: {cmp.diff?.total_queries_compared ?? 0}
            </span>
            <span>
              Доля изменений:{' '}
              <strong>
                {((cmp.diff?.bucket_change_ratio ?? 0) * 100).toFixed(1)}%
              </strong>
              {(cmp.diff?.bucket_change_ratio ?? 0) > 0.1 ? (
                <span style={{ color: '#b91c1c', marginLeft: 8 }}>D1 breach</span>
              ) : null}
            </span>
            <span>
              Primary↔Rejected flips:{' '}
              <strong>{(cmp.diff?.primary_rejected_flips || []).length}</strong>
              {(cmp.diff?.primary_rejected_flips || []).length > 0 ? (
                <span style={{ color: '#b91c1c', marginLeft: 8 }}>требует проверки</span>
              ) : null}
            </span>
          </div>
        </Card>
      ) : null}

      {cmp ? (
        <Card>
          <h3 style={{ marginTop: 0 }}>Per-query diff</h3>
          <CompareFilters
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            bucketFilter={bucketFilter}
            setBucketFilter={setBucketFilter}
            bucketScope={bucketScope}
            setBucketScope={setBucketScope}
            queryFilter={queryFilter}
            setQueryFilter={setQueryFilter}
            statusCounts={(cmp.diff?.per_query_bucket || []).reduce<Record<string, number>>((acc, r: any) => {
              const s = String(r?.status || 'same')
              acc[s] = (acc[s] || 0) + 1
              return acc
            }, {})}
            bucketCounts={(cmp.diff?.per_query_bucket || []).reduce<Record<BucketFilter, number>>(
              (acc, r: any) => {
                const cur = String(r?.current_bucket || '')
                const cand = String(r?.candidate_bucket || '')
                ;(['primary', 'secondary', 'broad', 'rejected'] as BucketFilter[]).forEach((b) => {
                  if (cur === b || cand === b) acc[b] = (acc[b] || 0) + 1
                })
                return acc
              },
              { any: 0, primary: 0, secondary: 0, broad: 0, rejected: 0 },
            )}
            total={(cmp.diff?.per_query_bucket || []).length}
          />
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Запрос</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Текущий</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Кандидат</th>
                  <th style={{ textAlign: 'left', padding: 6 }}>Статус</th>
                </tr>
              </thead>
              <tbody>
                {(cmp.diff?.per_query_bucket || [])
                  .filter((row: any) => {
                    const s = String(row?.status || 'same')
                    if (statusFilter === 'all') return true
                    if (statusFilter === 'diff') return s !== 'same'
                    return s === statusFilter
                  })
                  .filter((row: any) => {
                    if (bucketFilter === 'any') return true
                    const cur = String(row?.current_bucket || '')
                    const cand = String(row?.candidate_bucket || '')
                    if (bucketScope === 'current') return cur === bucketFilter
                    if (bucketScope === 'candidate') return cand === bucketFilter
                    if (bucketScope === 'both') return cur === bucketFilter && cand === bucketFilter
                    return cur === bucketFilter || cand === bucketFilter
                  })
                  .filter((row: any) => {
                    if (!queryFilter.trim()) return true
                    return String(row.normalized_query_text || '')
                      .toLowerCase()
                      .includes(queryFilter.trim().toLowerCase())
                  })
                  .slice(0, rowLimit)
                  .map((row: any, idx: number) => (
                  <tr key={`${row.normalized_query_text}-${idx}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: 6 }}>{row.normalized_query_text}</td>
                    <td style={{ padding: 6, color: bucketColor(row.current_bucket) }}>
                      {row.current_bucket ?? '—'}
                    </td>
                    <td style={{ padding: 6, color: bucketColor(row.candidate_bucket) }}>
                      {row.candidate_bucket ?? '—'}
                    </td>
                    <td style={{ padding: 6 }}>
                      {row.status === 'primary_rejected_flip' ? (
                        <span style={{ color: '#b91c1c', fontWeight: 700 }}>flip</span>
                      ) : row.status === 'bucket_changed' ? (
                        <span style={{ color: '#92400e' }}>bucket_changed</span>
                      ) : row.status === 'only_in_current' ? (
                        <span style={{ color: '#6b7280' }}>only_in_current</span>
                      ) : row.status === 'only_in_candidate' ? (
                        <span style={{ color: '#6b7280' }}>only_in_candidate</span>
                      ) : (
                        <span style={{ color: '#9ca3af' }}>same</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
            Показано не более <strong>{rowLimit}</strong> строк.{' '}
            <button
              type="button"
              onClick={() => setRowLimit((n) => n + 500)}
              style={{ ...buttonStyle('light'), padding: '4px 10px', fontSize: 12 }}
            >
              Показать ещё 500
            </button>
          </div>
        </Card>
      ) : null}

      {cmp ? (
        <Card>
          <h3 style={{ marginTop: 0 }}>Вердикт оператора</h3>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
            Запись в <code>seo_compare_verdicts</code>; не меняет matcher/generation state.
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Комментарий (опционально)"
            rows={3}
            style={{
              width: '100%',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              padding: '6px 10px',
              fontSize: 13,
              marginBottom: 8,
            }}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              style={buttonStyle('primary')}
              onClick={() => onVerdict('accept')}
              disabled={verdictState === 'saving'}
            >
              Accept
            </button>
            <button
              style={buttonStyle('light')}
              onClick={() => onVerdict('needs_changes')}
              disabled={verdictState === 'saving'}
            >
              Needs changes
            </button>
            <button
              style={buttonStyle('danger')}
              onClick={() => onVerdict('reject')}
              disabled={verdictState === 'saving'}
            >
              Reject
            </button>
            {verdictState === 'saved' ? (
              <span style={{ color: '#047857', alignSelf: 'center', fontSize: 12 }}>
                Сохранено
              </span>
            ) : null}
          </div>
        </Card>
      ) : null}

      {loading ? <Card>Загружаем…</Card> : null}
    </SeoShell>
  )
}
