'use client'

/**
 * Category-scoped eval page (Iteration 2, WS-F).
 *
 * Surfaces:
 *  - current ``eligibility_tier`` via :component:`CategoryTierBadge`,
 *  - latest eval-run metrics + thresholds + verdict,
 *  - the label-set coverage summary for the category,
 *  - a "Run eval" button that calls
 *    ``POST /api/v1/projects/{id}/seo/eval/matcher/run``.
 *
 * The eval endpoint is the single writer of ``eligibility_tier`` — this page
 * is the operator-facing entry point to that gate.
 */

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getSeoEvalLabelStats,
  getSeoEvalRuns,
  postSeoMatcherEvalRun,
  type SeoEvalLabelStatsResponse,
  type SeoEvalRunListItem,
  type SeoEvalRunListResponse,
} from '@/lib/apiClient'
import { SeoShell, Card, buttonStyle, normalizeError } from '../../../_components/SeoShell'
import { CategoryTierBadge } from '../../../_components/CategoryTierBadge'

function formatPct(value: number | undefined | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function formatNumber(value: number | undefined | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return String(value)
}

export default function SeoCategoryEvalPage({
  params,
}: {
  params: { projectId: string; categoryId: string }
}) {
  const { projectId, categoryId } = params
  const [runs, setRuns] = useState<SeoEvalRunListResponse | null>(null)
  const [stats, setStats] = useState<SeoEvalLabelStatsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [nmIdsInput, setNmIdsInput] = useState('')
  usePageTitle(`SEO eval · категория ${categoryId}`, projectId)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [r, s] = await Promise.all([
        getSeoEvalRuns(projectId, { category_id: Number(categoryId), limit: 25 }),
        getSeoEvalLabelStats(projectId, { category_id: Number(categoryId) }),
      ])
      setRuns(r)
      setStats(s)
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setLoading(false)
    }
  }, [projectId, categoryId])

  useEffect(() => {
    load()
  }, [load])

  const onRunEval = async () => {
    setRunning(true)
    setError(null)
    setInfo(null)
    try {
      const nmIds = nmIdsInput
        .split(/[\s,]+/)
        .map((x) => x.trim())
        .filter(Boolean)
        .map((x) => Number(x))
        .filter((x) => Number.isFinite(x) && x > 0)
      const body = {
        category_id: Number(categoryId),
        ...(nmIds.length ? { nm_ids: nmIds } : {}),
      }
      const res = await postSeoMatcherEvalRun(projectId, body)
      setInfo(
        `Eval complete: verdict=${res.verdict}, accuracy=${formatPct(
          res.metrics?.accuracy,
        )}, eligibility_tier=${res.eligibility_tier_after}`,
      )
      await load()
    } catch (e) {
      setError(normalizeError(e))
    } finally {
      setRunning(false)
    }
  }

  const currentTier = runs?.eligibility_tier || 'preview_only'
  const latest: SeoEvalRunListItem | undefined = runs?.items?.[0]

  return (
    <SeoShell projectId={projectId} title={`Категория ${categoryId} — Eval`}>
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <CategoryTierBadge tier={currentTier} size="md" />
          <Link
            href={`/app/project/${projectId}/seo/categories/${categoryId}`}
            style={{ color: '#2563eb', fontSize: 13 }}
          >
            ← Вернуться к категории
          </Link>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, marginBottom: 6 }}>
            Список SKU (опционально; через запятую/пробел). Пусто = все доступные matcher-runs.
          </div>
          <input
            type="text"
            value={nmIdsInput}
            onChange={(e) => setNmIdsInput(e.target.value)}
            placeholder="12345, 67890, ..."
            style={{
              width: '100%',
              padding: '6px 10px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              fontSize: 13,
            }}
          />
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
          <button
            style={buttonStyle('primary')}
            onClick={onRunEval}
            disabled={running}
          >
            {running ? 'Запускаем…' : 'Запустить eval'}
          </button>
          <button style={buttonStyle('ghost')} onClick={load} disabled={loading}>
            Обновить
          </button>
        </div>
        {info ? (
          <div style={{ color: '#047857', marginBottom: 10, fontSize: 13 }}>{info}</div>
        ) : null}
        {error ? (
          <div style={{ color: '#b91c1c', marginBottom: 10, fontSize: 13 }}>{error}</div>
        ) : null}
      </Card>

      <Card>
        <h3 style={{ marginTop: 0 }}>Последний eval-run</h3>
        {latest ? (
          <table style={{ width: '100%', fontSize: 13 }}>
            <tbody>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Verdict</th>
                <td style={{ padding: 4 }}>
                  <CategoryTierBadge tier={latest.verdict} />
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Accuracy</th>
                <td style={{ padding: 4 }}>{formatPct(latest.metrics?.accuracy)}</td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Primary precision</th>
                <td style={{ padding: 4 }}>{formatPct(latest.metrics?.primary_precision)}</td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Primary recall</th>
                <td style={{ padding: 4 }}>{formatPct(latest.metrics?.primary_recall)}</td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Bad primary rate</th>
                <td style={{ padding: 4 }}>{formatPct(latest.metrics?.bad_primary_rate)}</td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Hard-conflict primary</th>
                <td style={{ padding: 4 }}>
                  {formatNumber(latest.metrics?.hard_conflict_primary_count)}
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Labels scored / missing</th>
                <td style={{ padding: 4 }}>
                  {formatNumber(latest.metrics?.labels_scored)} /{' '}
                  {formatNumber(latest.metrics?.labels_missing)}
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Thresholds</th>
                <td style={{ padding: 4, fontFamily: 'monospace', fontSize: 12 }}>
                  acc ≥ {latest.thresholds?.accuracy_min}, bad_primary ≤{' '}
                  {latest.thresholds?.bad_primary_rate_max}, hard_conflict ≤{' '}
                  {latest.thresholds?.hard_conflict_primary_count_max}
                </td>
              </tr>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Created</th>
                <td style={{ padding: 4 }}>{latest.created_at}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <div style={{ color: '#6b7280', fontSize: 13 }}>
            Ещё ни одного eval-run для этой категории. Запустите, чтобы зафиксировать tier.
          </div>
        )}
      </Card>

      <Card>
        <h3 style={{ marginTop: 0 }}>Датасет меток</h3>
        {stats ? (
          <div style={{ fontSize: 13 }}>
            <div>Всего меток: <strong>{stats.total_labels}</strong></div>
            <div>По ведрам:</div>
            <ul style={{ margin: '4px 0 10px 18px' }}>
              {Object.entries(stats.by_bucket).map(([bucket, count]) => (
                <li key={bucket}>
                  <code>{bucket}</code>: {count}
                </li>
              ))}
            </ul>
            <div>По SKU (топ-10):</div>
            <ul style={{ margin: '4px 0 0 18px' }}>
              {Object.entries(stats.by_nm_id)
                .sort((a, b) => Number(b[1]) - Number(a[1]))
                .slice(0, 10)
                .map(([nm, count]) => (
                  <li key={nm}>
                    <code>{nm}</code>: {count}
                  </li>
                ))}
            </ul>
          </div>
        ) : (
          <div style={{ color: '#6b7280', fontSize: 13 }}>Нет данных</div>
        )}
      </Card>

      <Card>
        <h3 style={{ marginTop: 0 }}>История запусков</h3>
        {runs && runs.items.length > 0 ? (
          <table style={{ width: '100%', fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 4 }}>Run</th>
                <th style={{ textAlign: 'left', padding: 4 }}>Verdict</th>
                <th style={{ textAlign: 'left', padding: 4 }}>Accuracy</th>
                <th style={{ textAlign: 'left', padding: 4 }}>Bad primary</th>
                <th style={{ textAlign: 'left', padding: 4 }}>Scored</th>
                <th style={{ textAlign: 'left', padding: 4 }}>Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.items.map((run) => (
                <tr key={run.eval_run_id} style={{ borderTop: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 4 }}>{run.eval_run_id}</td>
                  <td style={{ padding: 4 }}>{run.verdict}</td>
                  <td style={{ padding: 4 }}>{formatPct(run.metrics?.accuracy)}</td>
                  <td style={{ padding: 4 }}>{formatPct(run.metrics?.bad_primary_rate)}</td>
                  <td style={{ padding: 4 }}>
                    {formatNumber(run.metrics?.labels_scored)}
                  </td>
                  <td style={{ padding: 4 }}>{run.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: '#6b7280', fontSize: 13 }}>История пуста</div>
        )}
      </Card>
    </SeoShell>
  )
}
