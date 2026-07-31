'use client'

/**
 * Iteration 1 P1 — matcher_v2 run viewer (read-only).
 *
 * Renders the persisted trace of a candidate-matcher run so operators can
 * replay a decision without re-running the matcher. Source data comes from
 * ``GET /api/v1/projects/{projectId}/seo/matcher/v2/runs/{runId}``.
 *
 * This is intentionally minimal: four bucket lists, score components and
 * reasons per item, and the run-level quality_mode + degraded_reasons. No
 * mutation affordances — iteration 1 does not let the candidate matcher
 * write into `SeoSkuQuerySet`.
 */

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoMatcherV2Run,
  type MatcherV2ResultItem,
  type MatcherV2RunDetailResponse,
} from '@/lib/apiClient'
import { Card, SeoShell, StatusPill, buttonStyle, normalizeError } from '../../_components/SeoShell'
import { QualityBadge } from '../../_components/QualityBadge'

const bucketOrder = ['primary', 'secondary', 'broad', 'rejected'] as const
const bucketLabels: Record<string, string> = {
  primary: 'Primary',
  secondary: 'Secondary',
  broad: 'Broad',
  rejected: 'Rejected',
}

const bucketTone: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = {
  primary: 'good',
  secondary: 'neutral',
  broad: 'warn',
  rejected: 'bad',
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}>
      <div style={{ color: '#64748b', fontSize: 13 }}>{label}</div>
      <div style={{ fontWeight: 900, marginTop: 3, overflowWrap: 'anywhere' }}>{value}</div>
    </div>
  )
}

function ResultRow({ item }: { item: MatcherV2ResultItem }) {
  const components = Object.entries(item.score_components || {})
  return (
    <div
      style={{
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: 12,
        display: 'grid',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong style={{ overflowWrap: 'anywhere' }}>{item.query_display}</strong>
        <StatusPill label={bucketLabels[item.bucket] || item.bucket} tone={bucketTone[item.bucket] || 'neutral'} />
        <StatusPill label={`score ${item.score.toFixed(3)}`} tone="neutral" />
        <StatusPill label={item.eligibility_verdict} tone={item.eligibility_verdict === 'eligible' ? 'good' : 'warn'} />
        {item.ranking_value_used != null && (
          <StatusPill label={`freq ${Math.round(item.ranking_value_used)}`} tone="neutral" />
        )}
        {item.semantic_similarity != null && (
          <StatusPill label={`sem ${item.semantic_similarity.toFixed(2)}`} tone="neutral" />
        )}
      </div>
      {components.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 8,
          }}
        >
          {components.map(([key, value]) => (
            <Metric key={key} label={key} value={typeof value === 'number' ? value.toFixed(3) : String(value)} />
          ))}
        </div>
      )}
      {item.matched_atoms.length > 0 && (
        <div style={{ color: '#475569' }}>
          <strong>matched:</strong> {item.matched_atoms.join(', ')}
        </div>
      )}
      {item.missing_atoms.length > 0 && (
        <div style={{ color: '#b45309' }}>
          <strong>missing:</strong> {item.missing_atoms.join(', ')}
        </div>
      )}
      {item.conflict_atoms.length > 0 && (
        <div style={{ color: '#b91c1c' }}>
          <strong>conflict:</strong> {item.conflict_atoms.join(', ')}
        </div>
      )}
      {item.reasons.length > 0 && (
        <div style={{ color: '#64748b', fontSize: 13 }}>
          {item.reasons.map((reason, idx) => (
            <span key={`${reason}-${idx}`}>
              {reason}
              {idx < item.reasons.length - 1 ? ' · ' : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SeoMatcherV2RunViewerPage({
  params,
}: {
  params: { projectId: string; runId: string }
}) {
  const { projectId, runId } = params
  const [run, setRun] = useState<MatcherV2RunDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  usePageTitle(`Matcher run #${runId}`, projectId)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getSeoMatcherV2Run(projectId, Number(runId))
      setRun(data)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [projectId, runId])

  const buckets = useMemo(() => {
    const groups: Record<string, MatcherV2ResultItem[]> = {
      primary: [],
      secondary: [],
      broad: [],
      rejected: [],
    }
    for (const item of run?.results || []) {
      const key = groups[item.bucket] ? item.bucket : 'rejected'
      groups[key].push(item)
    }
    return groups
  }, [run])

  return (
    <SeoShell
      projectId={projectId}
      title={`Matcher run #${runId}`}
      subtitle="Replay персистентного матчер-прогона (matcher_v2). Только чтение."
    >
      <div style={{ display: 'grid', gap: 16 }}>
        {error && (
          <Card>
            <div style={{ color: '#b91c1c' }}>{error}</div>
          </Card>
        )}

        <Card>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: 10,
              alignItems: 'center',
            }}
          >
            <div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                <StatusPill label={run ? `nm ${run.nm_id}` : 'loading'} tone="neutral" />
                {run && <StatusPill label={`category ${run.category_id}`} tone="neutral" />}
                {run && <StatusPill label={run.matcher_version} tone="neutral" />}
                {run && <StatusPill label={run.policy_version} tone="neutral" />}
                {run?.completed_at ? (
                  <StatusPill label="completed" tone="good" />
                ) : run?.error ? (
                  <StatusPill label="failed" tone="bad" />
                ) : (
                  <StatusPill label="running" tone="warn" />
                )}
                <QualityBadge mode={run?.quality_mode || undefined} reasons={(run?.degraded_reasons || []) as any} />
              </div>
              <div style={{ color: '#64748b' }}>
                {run?.started_at ? `Запущен ${new Date(run.started_at).toLocaleString('ru-RU')}` : ''}
                {run?.completed_at ? ` · завершён ${new Date(run.completed_at).toLocaleString('ru-RU')}` : ''}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <button type="button" onClick={load} disabled={loading} style={buttonStyle('light')}>
                {loading ? 'Обновляем...' : 'Обновить'}
              </button>
              <Link href={`/app/project/${projectId}/seo/products`} style={buttonStyle('ghost')}>
                К списку товаров
              </Link>
            </div>
          </div>
        </Card>

        {run && Object.keys(run.metrics).length > 0 && (
          <Card>
            <h2 style={{ marginTop: 0 }}>Метрики прогона</h2>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: 8,
              }}
            >
              {Object.entries(run.metrics).map(([key, value]) => (
                <Metric
                  key={key}
                  label={key}
                  value={typeof value === 'number' ? Number(value).toFixed(3) : String(value)}
                />
              ))}
            </div>
          </Card>
        )}

        {run?.degraded_reasons && run.degraded_reasons.length > 0 && (
          <Card>
            <h2 style={{ marginTop: 0 }}>Degraded reasons</h2>
            <ul style={{ margin: 0, paddingLeft: 20, color: '#475569' }}>
              {run.degraded_reasons.map((reason, idx) => (
                <li key={idx}>
                  <strong>{reason.code}</strong>
                  {reason.details ? `: ${JSON.stringify(reason.details)}` : ''}
                </li>
              ))}
            </ul>
          </Card>
        )}

        {run?.error && (
          <Card>
            <h2 style={{ marginTop: 0, color: '#b91c1c' }}>Ошибка прогона</h2>
            <pre
              style={{
                margin: 0,
                padding: 12,
                background: '#0f172a',
                color: '#e2e8f0',
                borderRadius: 8,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(run.error, null, 2)}
            </pre>
          </Card>
        )}

        {bucketOrder.map((bucket) => (
          <Card key={bucket}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                marginBottom: 12,
              }}
            >
              <h2 style={{ margin: 0 }}>{bucketLabels[bucket]}</h2>
              <span style={{ color: '#64748b', fontWeight: 700 }}>{buckets[bucket]?.length || 0}</span>
            </div>
            <div style={{ display: 'grid', gap: 10 }}>
              {(buckets[bucket] || []).map((item) => (
                <ResultRow key={item.id} item={item} />
              ))}
              {!buckets[bucket]?.length && (
                <div style={{ color: '#64748b' }}>Нет результатов в этом bucket.</div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </SeoShell>
  )
}
