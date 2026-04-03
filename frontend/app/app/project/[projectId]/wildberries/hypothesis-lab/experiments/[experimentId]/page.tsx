'use client'

import { useParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  getHypothesisExperimentDetail,
  startHypothesisExperiment,
  confirmHypothesisRun,
  stopHypothesisExperiment,
  type HypothesisExperimentDetail,
} from '@/lib/apiClient'
import PortalBackButton from '@/components/PortalBackButton'

const basePath = (projectId: string) => `/app/project/${projectId}/wildberries/hypothesis-lab/experiments`

export default function HypothesisLabExperimentDetailPage() {
  const params = useParams()
  const projectId = params.projectId as string
  const experimentId = Number(params.experimentId)
  const [exp, setExp] = useState<HypothesisExperimentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const load = () => {
    getHypothesisExperimentDetail(projectId, experimentId)
      .then(setExp)
      .catch((e) => setError(e?.detail ?? e?.message ?? 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [projectId, experimentId])

  const handleStart = () => {
    setActionLoading('start')
    startHypothesisExperiment(projectId, experimentId)
      .then(() => load())
      .catch((e) => setError(e?.detail ?? e?.message ?? 'Ошибка старта'))
      .finally(() => setActionLoading(null))
  }

  const handleConfirm = (runId: number) => {
    setActionLoading(`confirm-${runId}`)
    confirmHypothesisRun(projectId, runId)
      .then(() => load())
      .catch((e) => setError(e?.detail ?? e?.message ?? 'Ошибка подтверждения'))
      .finally(() => setActionLoading(null))
  }

  const handleStop = () => {
    setActionLoading('stop')
    stopHypothesisExperiment(projectId, experimentId)
      .then(() => load())
      .catch((e) => setError(e?.detail ?? e?.message ?? 'Ошибка остановки'))
      .finally(() => setActionLoading(null))
  }

  if (loading) return <div className="container"><p>Загрузка…</p></div>
  if (error && !exp) return <div className="container"><p style={{ color: 'red' }}>{error}</p><PortalBackButton href={basePath(projectId)} label="Назад" /></div>
  if (!exp) return <div className="container"><p>Эксперимент не найден.</p></div>

  const runningRun = exp.runs.find((r) => r.status === 'running')
  const canConfirm = runningRun && !runningRun.change_confirmed_at

  return (
    <div className="container">
      <h1>Эксперимент #{exp.id}</h1>
      <PortalBackButton href={basePath(projectId)} label="Назад к списку" />

      <div className="card" style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
          <span style={{ padding: '4px 10px', borderRadius: 6, backgroundColor: exp.status === 'completed' ? '#d4edda' : exp.status === 'running' ? '#cce5ff' : '#f8d7da', fontWeight: 500 }}>
            {exp.status}
          </span>
          <span><strong>Гипотеза:</strong> {exp.hypothesis_title ?? exp.hypothesis_id}</span>
          <span><strong>SKU:</strong> {exp.nm_id} {exp.product_title && `— ${exp.product_title.slice(0, 40)}…`}</span>
          <span><strong>Метрика:</strong> {exp.metric}</span>
          <span><strong>Change type:</strong> {exp.change_type}</span>
          <span><strong>Control:</strong> {exp.control_mode} {exp.controls_count != null ? `(${exp.controls_count})` : ''}</span>
        </div>
        <p><strong>Примечание к изменению:</strong> {exp.change_note}</p>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2 style={{ marginTop: 0 }}>Действия</h2>
        {exp.status === 'draft' && (
          <button
            type="button"
            onClick={handleStart}
            disabled={!!actionLoading}
            style={{ padding: '8px 16px', backgroundColor: '#28a745', color: 'white', border: 'none', borderRadius: 6, cursor: actionLoading ? 'wait' : 'pointer' }}
          >
            {actionLoading === 'start' ? 'Запуск…' : 'Запустить эксперимент'}
          </button>
        )}
        {exp.status === 'running' && canConfirm && runningRun && (
          <button
            type="button"
            onClick={() => handleConfirm(runningRun.id)}
            disabled={!!actionLoading}
            style={{ padding: '8px 16px', backgroundColor: '#0070f3', color: 'white', border: 'none', borderRadius: 6, marginRight: 8, cursor: actionLoading ? 'wait' : 'pointer' }}
          >
            {actionLoading === `confirm-${runningRun.id}` ? '…' : 'Подтвердить изменение'}
          </button>
        )}
        {exp.status === 'running' && (
          <button
            type="button"
            onClick={handleStop}
            disabled={!!actionLoading}
            style={{ padding: '8px 16px', backgroundColor: '#dc3545', color: 'white', border: 'none', borderRadius: 6, cursor: actionLoading ? 'wait' : 'pointer' }}
          >
            {actionLoading === 'stop' ? 'Остановка…' : 'Остановить эксперимент'}
          </button>
        )}
        {exp.status === 'completed' && <p style={{ color: '#666' }}>Эксперимент завершён. Результаты ниже.</p>}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2 style={{ marginTop: 0 }}>Runs</h2>
        {exp.runs.length === 0 ? (
          <p>Нет запусков.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ddd', textAlign: 'left' }}>
                <th style={{ padding: 8 }}>ID</th>
                <th style={{ padding: 8 }}>Started</th>
                <th style={{ padding: 8 }}>Confirmed</th>
                <th style={{ padding: 8 }}>Ended</th>
                <th style={{ padding: 8 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {exp.runs.map((r) => (
                <tr key={r.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: 8 }}>{r.id}</td>
                  <td style={{ padding: 8 }}>{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                  <td style={{ padding: 8 }}>{r.change_confirmed_at ? new Date(r.change_confirmed_at).toLocaleString() : '—'}</td>
                  <td style={{ padding: 8 }}>{r.ended_at ? new Date(r.ended_at).toLocaleString() : '—'}</td>
                  <td style={{ padding: 8 }}>{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {exp.status === 'completed' && exp.latest_result && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2 style={{ marginTop: 0 }}>Результат</h2>
          {exp.latest_result.control_mode === 'matched' ? (
            <div>
              <p><strong>DiD effect:</strong> {exp.latest_result.did_effect != null ? exp.latest_result.did_effect.toFixed(4) : '—'}</p>
              <p><strong>p-value:</strong> {exp.latest_result.p_value != null ? exp.latest_result.p_value.toFixed(4) : '—'}</p>
              <p><strong>CI:</strong> [{exp.latest_result.ci_low != null ? exp.latest_result.ci_low.toFixed(4) : '—'}, {exp.latest_result.ci_high != null ? exp.latest_result.ci_high.toFixed(4) : '—'}]</p>
              <p><strong>Pretrend pass:</strong> {exp.latest_result.pretrend_pass != null ? String(exp.latest_result.pretrend_pass) : '—'}</p>
            </div>
          ) : (
            <div>
              <p><strong>Before/after delta:</strong> {exp.latest_result.before_after_delta != null ? exp.latest_result.before_after_delta.toFixed(4) : '—'}</p>
              <p style={{ fontSize: 12, color: '#666' }}>Control mode = none: DiD не выполнялся.</p>
            </div>
          )}
          <p style={{ fontSize: 12, color: '#888' }}>Computed at: {exp.latest_result.computed_at ? new Date(exp.latest_result.computed_at).toLocaleString() : '—'}</p>
        </div>
      )}

      {error && <p style={{ color: 'red', marginTop: 12 }}>{error}</p>}
    </div>
  )
}
