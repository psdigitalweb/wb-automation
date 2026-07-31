'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  generateReviewOpinion,
  getReviewOpinion,
  type ReviewOpinionFinding,
  type ReviewOpinionState,
} from '@/lib/wbCatalogApi'
import styles from '../product.module.css'

const integer = new Intl.NumberFormat('ru-RU')

const categoryLabels = {
  product: 'Товар',
  packaging_delivery: 'Упаковка и доставка',
  service: 'Сервис',
} as const

function errorMessage(caught: unknown) {
  if (
    typeof caught === 'object' &&
    caught !== null &&
    'detail' in caught &&
    typeof caught.detail === 'string'
  ) {
    return caught.detail
  }
  return caught instanceof Error ? caught.message : 'Не удалось выполнить запрос'
}

function formatDateTime(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat('ru-RU', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(parsed)
}

function Findings({
  title,
  tone,
  findings,
}: {
  title: string
  tone: 'positive' | 'negative'
  findings: ReviewOpinionFinding[]
}) {
  return (
    <div className={styles.opinionColumn}>
      <h3 className={tone === 'positive' ? styles.positive : styles.negative}>
        {title}
      </h3>
      {findings.length ? (
        <div className={styles.opinionList}>
          {findings.map((finding) => (
            <article key={`${tone}:${finding.label}`}>
              <div className={styles.opinionFindingHeader}>
                <strong>{finding.label}</strong>
                <span>{integer.format(finding.support_count)} отзывов</span>
              </div>
              <small>{categoryLabels[finding.category]}</small>
              <p>{finding.summary}</p>
              <details>
                <summary>Примеры из отзывов</summary>
                {finding.evidence.map((item) => (
                  <blockquote key={`${item.review_id}:${item.quote}`}>
                    «{item.quote}»
                  </blockquote>
                ))}
              </details>
            </article>
          ))}
        </div>
      ) : (
        <p className={styles.opinionEmpty}>Устойчивых тем не найдено.</p>
      )}
    </div>
  )
}

export function CustomerOpinionSection({
  projectId,
  nmId,
  expanded,
  onToggle,
}: {
  projectId: string
  nmId: number
  expanded: boolean
  onToggle: () => void
}) {
  const [state, setState] = useState<ReviewOpinionState | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const next = await getReviewOpinion(projectId, String(nmId))
      setState(next)
      setError(null)
      return next
    } catch (caught: unknown) {
      setError(errorMessage(caught))
      return null
    } finally {
      setLoading(false)
    }
  }, [nmId, projectId])

  useEffect(() => {
    void load()
  }, [load])

  const active =
    state?.latest_run?.status === 'queued' ||
    state?.latest_run?.status === 'running'

  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => void load(), 2500)
    return () => window.clearInterval(timer)
  }, [active, load])

  async function requestAnalysis() {
    if (!state || submitting || active) return
    const refresh = Boolean(state.result)

    setSubmitting(true)
    setError(null)
    try {
      await generateReviewOpinion(projectId, String(nmId), refresh)
      await load()
    } catch (caught: unknown) {
      setError(errorMessage(caught))
    } finally {
      setSubmitting(false)
    }
  }

  const description = loading
    ? 'Проверяем текстовые отзывы…'
    : state
      ? `${integer.format(state.reviews_with_text)} отзывов с текстом · за всё время`
      : 'Выводы по текстовым отзывам за всё время'

  return (
    <section id="customer-opinion-section" className={styles.section}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>Мнение покупателей</h2>
          <p>{description}</p>
        </div>
        <button
          type="button"
          className={styles.collapseButton}
          aria-expanded={expanded}
          aria-controls="customer-opinion-content"
          onClick={onToggle}
        >
          <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        </button>
      </div>

      {expanded ? (
        <div id="customer-opinion-content" className={styles.opinionBody}>
          {error ? <div className={styles.opinionError}>{error}</div> : null}
          {!state || loading ? (
            <div className={styles.inlineStatus}>Загружаем состояние…</div>
          ) : !state.feature_enabled ? (
            <div className={styles.inlineStatus}>
              Анализ отзывов пока выключен в настройках сервиса.
            </div>
          ) : !state.can_analyze ? (
            <div className={styles.inlineStatus}>
              Для анализа нужно минимум два отзыва с текстом, плюсами или
              минусами. Оценки без текста не отправляются.
            </div>
          ) : (
            <>
              <div className={styles.opinionToolbar}>
                <div>
                  <strong>
                    {state.result
                      ? state.stale
                        ? 'Появились новые текстовые отзывы'
                        : `Выводы от ${formatDateTime(state.result_created_at)}`
                      : 'Выводы ещё не сформированы'}
                  </strong>
                  <small>
                    В анализ попадёт до {integer.format(state.reviews_sent)} из{' '}
                    {integer.format(state.reviews_with_text)} текстовых отзывов.
                    Оценки без текста исключены.
                  </small>
                </div>
                <button
                  type="button"
                  className={styles.opinionAction}
                  disabled={submitting || active || !state.can_generate}
                  onClick={requestAnalysis}
                >
                  {!state.can_generate
                    ? 'Только просмотр'
                    : submitting || active
                    ? 'Анализируем…'
                    : state.result
                      ? 'Обновить выводы'
                      : 'Проанализировать отзывы'}
                </button>
              </div>

              {state.latest_run?.status === 'failed' ? (
                <div className={styles.opinionError}>
                  Не удалось сформировать выводы. Запрос можно повторить вручную.
                </div>
              ) : null}

              {state.result ? (
                <>
                  <p className={styles.opinionConclusion}>
                    {state.result.overall_conclusion}
                  </p>
                  <div className={styles.opinionGrid}>
                    <Findings
                      title="Что покупателям нравится"
                      tone="positive"
                      findings={state.result.strengths}
                    />
                    <Findings
                      title="Что покупателям не нравится"
                      tone="negative"
                      findings={state.result.weaknesses}
                    />
                  </div>
                  {state.result.conflicts.length ? (
                    <div className={styles.opinionNotes}>
                      <strong>Мнения расходятся</strong>
                      {state.result.conflicts.map((conflict) => (
                        <p key={conflict.label}>
                          <b>{conflict.label}:</b> {conflict.summary}
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {state.result.isolated_observations.length ? (
                    <details className={styles.opinionNotes}>
                      <summary>Единичные наблюдения</summary>
                      {state.result.isolated_observations.map((finding) => (
                        <p key={finding.label}>
                          <b>{finding.label}:</b> {finding.summary}
                        </p>
                      ))}
                    </details>
                  ) : null}
                  <small className={styles.opinionDisclaimer}>
                    Сформировано автоматически по текстам покупателей. Проверяйте
                    выводы перед принятием решений.
                  </small>
                </>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </section>
  )
}
