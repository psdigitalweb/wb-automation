'use client'

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import { Badge } from '@/components/ui-v2/primitives/Badge'
import { Button } from '@/components/ui-v2/primitives/Button'
import { Card } from '@/components/ui-v2/primitives/Card'
import { PageHeader } from '@/components/ui-v2/primitives/PageHeader'
import {
  addCompetitorReviewTargets,
  collectCompetitorReviews,
  deleteCompetitorReviewTargets,
  generateCompetitorAnalysis,
  getCompetitorAnalysis,
  getCompetitorReviewRun,
  getCompetitorReviews,
  getCompetitorReviewTargets,
  type CompetitorAnalysisFinding,
  type CompetitorAnalysisState,
  type CompetitorReview,
  type CompetitorReviewRun,
  type CompetitorReviewTarget,
  type CompetitorReviewTargetStatus,
} from '@/lib/competitorReviewsApi'
import styles from './competitor-reviews.module.css'

const MAX_NM_IDS = 50
const REVIEWS_PAGE_SIZE = 20

type ParsedNmIds = {
  ids: number[]
  duplicateCount: number
  invalid: string[]
}

type ReviewListState = {
  items: CompetitorReview[]
  total: number
  hasMore: boolean
  loading: boolean
  loadingMore: boolean
  loaded: boolean
  error: string | null
}

function parseNmIds(value: string): ParsedNmIds {
  const tokens = value.split(/[\s,;]+/).map((token) => token.trim()).filter(Boolean)
  const seen = new Set<number>()
  const ids: number[] = []
  const invalid: string[] = []
  let duplicateCount = 0

  for (const token of tokens) {
    if (!/^\d+$/.test(token)) {
      invalid.push(token)
      continue
    }
    const nmId = Number(token)
    if (!Number.isSafeInteger(nmId) || nmId <= 0) {
      invalid.push(token)
      continue
    }
    if (seen.has(nmId)) {
      duplicateCount += 1
      continue
    }
    seen.add(nmId)
    ids.push(nmId)
  }

  return { ids, duplicateCount, invalid }
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null) {
    const response = error as { detail?: unknown; message?: unknown }
    if (typeof response.detail === 'string') return response.detail
    if (typeof response.message === 'string') return response.message
  }
  return fallback
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function formatRating(value: number | null, digits = 1): string {
  return value == null || Number.isNaN(value) ? '—' : value.toFixed(digits).replace('.', ',')
}

function formatCount(value: number | null): string {
  return value == null ? '—' : new Intl.NumberFormat('ru-RU').format(value)
}

function formatUsd(value: number | null): string {
  return value == null ? '—' : `$${value.toFixed(4)}`
}

function prevalenceLabel(value: CompetitorAnalysisFinding['prevalence']): string {
  return {
    frequent: 'Часто',
    occasional: 'Иногда',
    isolated: 'Единично',
  }[value]
}

function analysisStatusLabel(target: CompetitorReviewTarget): string {
  if (target.analysis_is_stale) return 'Есть новые отзывы'
  if (target.analysis_status === 'queued') return 'В очереди'
  if (target.analysis_status === 'running') return 'Анализируем'
  if (target.analysis_status === 'ready') return 'Анализ готов'
  if (target.analysis_status === 'failed') return 'Ошибка анализа'
  return 'Анализ не сформирован'
}

function analysisErrorMessage(errorCode: string | null, errorMessage: string | null): string {
  if (errorCode === 'invalid_evidence_review' || errorCode === 'invalid_evidence_quote') {
    return 'Не удалось проверить часть подтверждающих цитат. Запустите анализ повторно.'
  }
  return errorMessage || 'Попробуйте запустить анализ повторно.'
}

function statusMeta(status: CompetitorReviewTargetStatus): { label: string; tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' } {
  const statuses: Record<CompetitorReviewTargetStatus, { label: string; tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' }> = {
    queued: { label: 'В очереди', tone: 'info' },
    collecting: { label: 'Собираем', tone: 'info' },
    ready: { label: 'Готово', tone: 'success' },
    partial: { label: 'Частично', tone: 'warning' },
    failed: { label: 'Ошибка', tone: 'danger' },
    not_found: { label: 'Не найден', tone: 'danger' },
  }
  return statuses[status]
}

function isFinishedRun(run: CompetitorReviewRun): boolean {
  return run.status === 'completed' || run.status === 'failed'
}

function mergeReviews(existing: CompetitorReview[], incoming: CompetitorReview[]): CompetitorReview[] {
  const ids = new Set(existing.map((review) => String(review.id)))
  return [...existing, ...incoming.filter((review) => !ids.has(String(review.id)))]
}

function ReviewContent({ review }: { review: CompetitorReview }) {
  return (
    <article className={styles.reviewItem}>
      <div className={styles.reviewMeta}>
        <span className={styles.stars} aria-label={review.rating == null ? 'Без оценки' : `Оценка ${review.rating} из 5`}>
          {review.rating == null ? 'Без оценки' : `${'★'.repeat(Math.max(0, Math.min(5, Math.round(review.rating))))}${'☆'.repeat(Math.max(0, 5 - Math.round(review.rating)))}`}
        </span>
        <span>{formatDate(review.created_at)}</span>
      </div>
      {review.text ? <p className={styles.reviewText}>{review.text}</p> : null}
      {review.pros ? <p className={styles.reviewPart}><strong>Плюсы:</strong> {review.pros}</p> : null}
      {review.cons ? <p className={styles.reviewPart}><strong>Минусы:</strong> {review.cons}</p> : null}
    </article>
  )
}

function AnalysisFindingSection({
  title,
  items,
  tone,
}: {
  title: string
  items: CompetitorAnalysisFinding[]
  tone: 'success' | 'danger' | 'info'
}) {
  if (items.length === 0) return null
  return (
    <section className={styles.analysisSection}>
      <h3>{title}</h3>
      <div className={styles.analysisList}>
        {items.map((item) => (
          <article className={styles.analysisFinding} key={`${title}-${item.label}`}>
            <div className={styles.analysisFindingHeader}>
              <strong>{item.label}</strong>
              <div className={styles.analysisBadges}>
                <Badge tone={tone}>{prevalenceLabel(item.prevalence)}</Badge>
                <span>{formatCount(item.support_count)} отзывов</span>
              </div>
            </div>
            <p>{item.summary}</p>
            {item.evidence.length > 0 ? (
              <details className={styles.evidence}>
                <summary>Подтверждающие отзывы ({item.evidence.length})</summary>
                {item.evidence.map((evidence) => (
                  <blockquote key={`${item.label}-${evidence.review_id}`}>
                    «{evidence.quote}»
                  </blockquote>
                ))}
              </details>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  )
}

export default function CompetitorReviewsPage() {
  const params = useParams()
  const projectId = typeof params?.projectId === 'string' ? params.projectId : ''
  const [rawNmIds, setRawNmIds] = useState('')
  const [targets, setTargets] = useState<CompetitorReviewTarget[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [expandedNmId, setExpandedNmId] = useState<number | null>(null)
  const [reviewsByNmId, setReviewsByNmId] = useState<Record<number, ReviewListState>>({})
  const [activeRun, setActiveRun] = useState<CompetitorReviewRun | null>(null)
  const [analysisTarget, setAnalysisTarget] = useState<CompetitorReviewTarget | null>(null)
  const [analysisState, setAnalysisState] = useState<CompetitorAnalysisState | null>(null)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [startingAnalysis, setStartingAnalysis] = useState(false)
  const [deletingTargets, setDeletingTargets] = useState(false)
  const [loadingTargets, setLoadingTargets] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  usePageTitle('Анализ отзывов конкурентов', projectId || null)

  const parsed = useMemo(() => parseNmIds(rawNmIds), [rawNmIds])
  const canSubmitNmIds =
    parsed.ids.length > 0 &&
    parsed.ids.length <= MAX_NM_IDS &&
    parsed.invalid.length === 0 &&
    !submitting
  const activeRunInProgress = activeRun !== null && !isFinishedRun(activeRun)

  const loadTargets = useCallback(async () => {
    if (!projectId) return
    setLoadingTargets(true)
    try {
      const response = await getCompetitorReviewTargets(projectId)
      setTargets(response.items)
      setError(null)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось загрузить список конкурентов'))
    } finally {
      setLoadingTargets(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadTargets()
  }, [loadTargets])

  useEffect(() => {
    if (!projectId || !activeRun || isFinishedRun(activeRun)) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const poll = async () => {
      try {
        const response = await getCompetitorReviewRun(projectId, activeRun.id)
        if (cancelled) return
        setActiveRun(response.run)
        if (isFinishedRun(response.run)) {
          await loadTargets()
          if (response.run.status === 'failed') {
            setError('Сбор завершился с ошибкой. Проверьте статусы товаров и повторите запуск вручную.')
          } else if (response.run.failed_nm_ids && response.run.failed_nm_ids.length > 0) {
            setNotice(`Сбор завершён: готово ${response.run.completed_nm_ids?.length ?? 0}, с ошибкой ${response.run.failed_nm_ids.length}.`)
          } else {
            setNotice(`Сбор завершён: обновлено ${response.run.completed_nm_ids?.length ?? 0} товаров.`)
          }
          return
        }
      } catch (requestError: unknown) {
        if (cancelled) return
        setError(getErrorMessage(requestError, 'Не удалось проверить ход сбора'))
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 2500)
    }

    timer = setTimeout(() => void poll(), 1200)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [activeRun, loadTargets, projectId])

  const startCollection = useCallback(async (nmIds?: number[]) => {
    if (!projectId) return
    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const response = await collectCompetitorReviews(projectId, nmIds)
      setActiveRun(response.run)
      setNotice('Сбор отзывов запущен. Статусы в таблице обновятся автоматически.')
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось запустить сбор отзывов'))
    } finally {
      setSubmitting(false)
    }
  }, [projectId])

  const handleAddAndCollect = async () => {
    if (!projectId || !canSubmitNmIds) return
    if (!window.confirm(`Добавить ${parsed.ids.length} nmID и запустить ручной сбор отзывов?`)) return

    setSubmitting(true)
    setError(null)
    setNotice(null)
    try {
      const response = await addCompetitorReviewTargets(projectId, parsed.ids)
      await loadTargets()
      const collectResponse = await collectCompetitorReviews(projectId, parsed.ids)
      setActiveRun(collectResponse.run)
      setRawNmIds('')
      setNotice(`Добавлено: ${response.added_count}. Уже были в списке: ${response.existing_count}. Сбор запущен.`)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось добавить конкурентов или запустить сбор'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleRefresh = (nmIds?: number[]) => {
    if (activeRunInProgress || submitting) return
    const scope = nmIds && nmIds.length > 0 ? `${nmIds.length} выбранных nmID` : 'всех конкурентов'
    if (!window.confirm(`Обновить отзывы для ${scope}? Будет запущен ручной сбор.`)) return
    void startCollection(nmIds)
  }

  const loadAnalysis = useCallback(async (target: CompetitorReviewTarget) => {
    if (!projectId) return
    setAnalysisTarget(target)
    setLoadingAnalysis(true)
    try {
      const response = await getCompetitorAnalysis(projectId, target.nm_id)
      setAnalysisState(response)
      setError(null)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось загрузить анализ отзывов'))
    } finally {
      setLoadingAnalysis(false)
    }
  }, [projectId])

  const startAnalysis = useCallback(async (target: CompetitorReviewTarget, refresh = false) => {
    if (!projectId) return
    const estimate = target.analysis_estimated_cost_usd ?? analysisState?.estimated_cost_usd ?? 0.1
    if (!window.confirm(
      `Проанализировать ${formatCount(target.text_reviews_count)} отзывов?\n` +
      `Ориентировочная стоимость: ${formatUsd(estimate)}.\n` +
      'Максимальный лимит запуска: $0.2000.',
    )) return
    setStartingAnalysis(true)
    setError(null)
    try {
      const response = await generateCompetitorAnalysis(projectId, target.nm_id, {
        refresh,
        maxCostUsd: 0.2,
      })
      setAnalysisState((previous) => previous ? { ...previous, latest: response.run } : previous)
      setNotice(response.cached ? 'Показан сохранённый актуальный анализ.' : 'Анализ запущен вручную.')
      await loadTargets()
      if (response.cached) await loadAnalysis(target)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось запустить анализ'))
    } finally {
      setStartingAnalysis(false)
    }
  }, [analysisState?.estimated_cost_usd, loadAnalysis, loadTargets, projectId])

  const startSelectedAnalyses = useCallback(async () => {
    if (!projectId || selectedIds.size === 0) return
    const selected = targets.filter((target) => selectedIds.has(target.nm_id) && target.text_reviews_count >= 2)
    if (selected.length === 0) {
      setError('У выбранных товаров недостаточно текстовых отзывов для анализа.')
      return
    }
    const estimate = selected.reduce((sum, target) => sum + (target.analysis_estimated_cost_usd ?? 0.1), 0)
    if (!window.confirm(
      `Проанализировать выбранные товары: ${selected.length}?\n` +
      `Ориентировочная общая стоимость: ${formatUsd(estimate)}.\n` +
      'Максимальный лимит: $0.20 на товар.',
    )) return
    setStartingAnalysis(true)
    setError(null)
    try {
      for (const target of selected) {
        await generateCompetitorAnalysis(projectId, target.nm_id, { maxCostUsd: 0.2 })
      }
      setNotice(`Анализ запущен для ${selected.length} товаров.`)
      await loadTargets()
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось запустить анализ выбранных товаров'))
    } finally {
      setStartingAnalysis(false)
    }
  }, [loadTargets, projectId, selectedIds, targets])

  const deleteSelectedTargets = useCallback(async () => {
    if (!projectId || selectedIds.size === 0 || activeRunInProgress) return
    const nmIds = [...selectedIds]
    if (!window.confirm(
      `Удалить выбранные товары: ${nmIds.length}?\n` +
      'Собранные отзывы и результаты анализа также будут удалены. Это действие нельзя отменить.',
    )) return

    setDeletingTargets(true)
    setError(null)
    setNotice(null)
    try {
      const response = await deleteCompetitorReviewTargets(projectId, nmIds)
      const deleted = new Set(response.deleted_nm_ids)
      setTargets((previous) => previous.filter((target) => !deleted.has(target.nm_id)))
      setSelectedIds(new Set())
      setReviewsByNmId((previous) => Object.fromEntries(
        Object.entries(previous).filter(([nmId]) => !deleted.has(Number(nmId))),
      ))
      if (expandedNmId !== null && deleted.has(expandedNmId)) setExpandedNmId(null)
      if (analysisTarget && deleted.has(analysisTarget.nm_id)) {
        setAnalysisTarget(null)
        setAnalysisState(null)
      }
      setNotice(`Удалено товаров: ${response.deleted_count}.`)
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError, 'Не удалось удалить выбранные товары'))
    } finally {
      setDeletingTargets(false)
    }
  }, [activeRunInProgress, analysisTarget, expandedNmId, projectId, selectedIds])

  useEffect(() => {
    const status = analysisState?.latest?.status
    if (!analysisTarget || !projectId || (status !== 'queued' && status !== 'running')) return
    let cancelled = false
    const timer = setInterval(() => {
      void getCompetitorAnalysis(projectId, analysisTarget.nm_id).then((response) => {
        if (cancelled) return
        setAnalysisState(response)
        if (response.latest?.status === 'ready' || response.latest?.status === 'failed') {
          void loadTargets()
        }
      }).catch((requestError: unknown) => {
        if (!cancelled) setError(getErrorMessage(requestError, 'Не удалось проверить ход анализа'))
      })
    }, 2500)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [analysisState?.latest?.status, analysisTarget, loadTargets, projectId])

  useEffect(() => {
    if (!targets.some((target) => target.analysis_status === 'queued' || target.analysis_status === 'running')) return
    const timer = setInterval(() => void loadTargets(), 3000)
    return () => clearInterval(timer)
  }, [loadTargets, targets])

  const loadReviews = useCallback(async (nmId: number, append = false) => {
    if (!projectId) return
    const current = reviewsByNmId[nmId]
    const offset = append ? current?.items.length ?? 0 : 0
    setReviewsByNmId((previous) => ({
      ...previous,
      [nmId]: {
        items: append ? previous[nmId]?.items ?? [] : [],
        total: previous[nmId]?.total ?? 0,
        hasMore: previous[nmId]?.hasMore ?? false,
        loading: !append,
        loadingMore: append,
        loaded: previous[nmId]?.loaded ?? false,
        error: null,
      },
    }))
    try {
      const response = await getCompetitorReviews(projectId, nmId, { limit: REVIEWS_PAGE_SIZE, offset })
      setReviewsByNmId((previous) => ({
        ...previous,
        [nmId]: {
          items: append ? mergeReviews(previous[nmId]?.items ?? [], response.items) : response.items,
          total: response.total,
          hasMore: response.has_more,
          loading: false,
          loadingMore: false,
          loaded: true,
          error: null,
        },
      }))
    } catch (requestError: unknown) {
      setReviewsByNmId((previous) => ({
        ...previous,
        [nmId]: {
          items: previous[nmId]?.items ?? [],
          total: previous[nmId]?.total ?? 0,
          hasMore: previous[nmId]?.hasMore ?? false,
          loading: false,
          loadingMore: false,
          loaded: previous[nmId]?.loaded ?? false,
          error: getErrorMessage(requestError, 'Не удалось загрузить отзывы'),
        },
      }))
    }
  }, [projectId, reviewsByNmId])

  const toggleReviews = (nmId: number) => {
    if (expandedNmId === nmId) {
      setExpandedNmId(null)
      return
    }
    setExpandedNmId(nmId)
    const current = reviewsByNmId[nmId]
    if (!current?.loaded && !current?.loading) void loadReviews(nmId)
  }

  const toggleTargetSelected = (nmId: number) => {
    setSelectedIds((previous) => {
      const next = new Set(previous)
      if (next.has(nmId)) next.delete(nmId)
      else next.add(nmId)
      return next
    })
  }

  const selectedTargetIds = [...selectedIds]
  const hasTargets = targets.length > 0
  const visibleAnalysis = analysisState?.latest?.status === 'ready'
    ? analysisState.latest
    : analysisState?.latest_ready ?? null

  return (
    <div className={styles.page}>
      <PageHeader
        title="Анализ отзывов конкурентов"
        subtitle="Добавьте карточки WB, соберите текстовые отзывы вручную и изучайте обратную связь по каждому товару."
        marketplaceTag="wb"
      />

      <Card className={styles.addCard}>
        <div className={styles.addHeader}>
          <div>
            <h2>Добавить конкурентов</h2>
            <p>Введите до {MAX_NM_IDS} nmID через запятую, пробел или с новой строки.</p>
          </div>
          {parsed.ids.length > 0 ? <Badge tone="info">{parsed.ids.length} уникальных nmID</Badge> : null}
        </div>
        <label className={styles.inputLabel} htmlFor="competitor-nmids">nmID товаров конкурентов</label>
        <textarea
          id="competitor-nmids"
          className={styles.textarea}
          value={rawNmIds}
          onChange={(event) => setRawNmIds(event.target.value)}
          placeholder={'291945877, 123456789\n987654321'}
          rows={4}
          disabled={submitting}
        />
        <div className={styles.parserInfo} aria-live="polite">
          <span>Уникальных: {parsed.ids.length}</span>
          {parsed.duplicateCount > 0 ? <span>Дубликатов пропущено: {parsed.duplicateCount}</span> : null}
          {parsed.invalid.length > 0 ? <span className={styles.errorText}>Некорректные: {parsed.invalid.slice(0, 8).join(', ')}{parsed.invalid.length > 8 ? '…' : ''}</span> : null}
          {parsed.ids.length > MAX_NM_IDS ? <span className={styles.errorText}>За один запуск можно добавить не более {MAX_NM_IDS} nmID.</span> : null}
        </div>
        <div className={styles.addActions}>
          <Button type="button" variant="primary" onClick={() => void handleAddAndCollect()} disabled={!canSubmitNmIds || activeRunInProgress}>
            Добавить и собрать
          </Button>
          {activeRunInProgress ? <span className={styles.muted}>Идёт сбор по запуску #{activeRun.id}</span> : null}
        </div>
      </Card>

      {error ? <div className={styles.message} role="alert"><Badge tone="danger">Ошибка</Badge><span>{error}</span></div> : null}
      {notice ? <div className={styles.message} role="status"><Badge tone="success">Готово</Badge><span>{notice}</span></div> : null}

      <section aria-labelledby="competitor-targets-title">
        <div className={styles.sectionHeader}>
          <div>
            <h2 id="competitor-targets-title">Собранные товары</h2>
            <p>Текстовые отзывы можно открыть в строке товара.</p>
          </div>
          <div className={styles.tableActions}>
            <Button type="button" size="sm" variant="primary" onClick={() => void startSelectedAnalyses()} disabled={selectedTargetIds.length === 0 || startingAnalysis}>
              Проанализировать выбранные ({selectedTargetIds.length})
            </Button>
            <Button type="button" size="sm" onClick={() => handleRefresh(selectedTargetIds)} disabled={selectedTargetIds.length === 0 || selectedTargetIds.length > MAX_NM_IDS || activeRunInProgress || submitting}>
              Обновить выбранные ({selectedTargetIds.length})
            </Button>
            <Button type="button" size="sm" variant="danger" onClick={() => void deleteSelectedTargets()} disabled={selectedTargetIds.length === 0 || selectedTargetIds.length > MAX_NM_IDS || activeRunInProgress || deletingTargets}>
              {deletingTargets ? 'Удаляем…' : `Удалить выбранные (${selectedTargetIds.length})`}
            </Button>
            <Button type="button" size="sm" onClick={() => handleRefresh()} disabled={!hasTargets || targets.length > MAX_NM_IDS || activeRunInProgress || submitting}>
              {targets.length > MAX_NM_IDS ? 'Для всех: максимум 50' : 'Обновить все'}
            </Button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.selectCell}><span className="sr-only">Выбрать</span></th>
                <th>nmID</th>
                <th>Товар</th>
                <th>Категория</th>
                <th className={styles.numeric}>Текстовых</th>
                <th className={styles.numeric}>Оценка</th>
                <th>Статус</th>
                <th>Обновлено</th>
                <th className={styles.actionsCell}><span className="sr-only">Действия</span></th>
              </tr>
            </thead>
            <tbody>
              {loadingTargets ? (
                <tr><td colSpan={9} className={styles.tableState}>Загрузка списка конкурентов…</td></tr>
              ) : null}
              {!loadingTargets && targets.length === 0 ? (
                <tr><td colSpan={9} className={styles.tableState}>Добавьте nmID, чтобы начать сбор отзывов конкурентов.</td></tr>
              ) : null}
              {!loadingTargets && targets.map((target) => {
                const expanded = expandedNmId === target.nm_id
                const reviews = reviewsByNmId[target.nm_id]
                const status = statusMeta(target.status)
                return (
                  <Fragment key={target.nm_id}>
                    <tr key={target.nm_id} className={expanded ? styles.targetRowExpanded : undefined}>
                      <td className={styles.selectCell}>
                        <input type="checkbox" aria-label={`Выбрать ${target.nm_id}`} checked={selectedIds.has(target.nm_id)} onChange={() => toggleTargetSelected(target.nm_id)} />
                      </td>
                      <td className={styles.nmId}><a href={`https://www.wildberries.ru/catalog/${target.nm_id}/detail.aspx`} target="_blank" rel="noreferrer">{target.nm_id}</a></td>
                      <td>
                        <div className={styles.productTitle}>{target.title || 'Название ещё не получено'}</div>
                        {target.brand ? <div className={styles.brand}>{target.brand}</div> : null}
                      </td>
                      <td className={styles.category}>{target.category_name || '—'}</td>
                      <td className={`${styles.numeric} ${styles.mono}`}>{formatCount(target.text_reviews_count)}</td>
                      <td className={styles.rating}>
                        <span>WB {formatRating(target.wb_review_rating)}</span>
                        <span>текст {formatRating(target.calculated_avg_rating)}</span>
                      </td>
                      <td>
                        <Badge tone={status.tone}>{status.label}</Badge>
                        {target.last_error ? <span className={styles.rowError} title={target.last_error}>!</span> : null}
                        <span className={`${styles.analysisRowStatus} ${target.analysis_is_stale ? styles.analysisStale : ''}`}>
                          {analysisStatusLabel(target)}
                        </span>
                      </td>
                      <td className={styles.updatedAt}>{formatDate(target.last_collected_at)}</td>
                      <td className={styles.actionsCell}>
                        <Button type="button" variant="ghost" size="sm" onClick={() => handleRefresh([target.nm_id])} disabled={activeRunInProgress || submitting}>Обновить</Button>
                        <button type="button" className={styles.expandButton} onClick={() => void loadAnalysis(target)}>
                          Анализ
                        </button>
                        <button type="button" className={styles.expandButton} aria-expanded={expanded} aria-controls={`competitor-reviews-${target.nm_id}`} onClick={() => toggleReviews(target.nm_id)}>
                          {expanded ? 'Скрыть отзывы' : 'Отзывы'}
                        </button>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr key={`${target.nm_id}-reviews`} id={`competitor-reviews-${target.nm_id}`}>
                        <td colSpan={9} className={styles.reviewCell}>
                          {reviews?.loading ? <p className={styles.muted}>Загрузка отзывов…</p> : null}
                          {reviews?.error ? <div className={styles.reviewError}><span>{reviews.error}</span><Button type="button" size="sm" onClick={() => void loadReviews(target.nm_id)}>Повторить</Button></div> : null}
                          {reviews?.loaded && reviews.items.length === 0 ? <p className={styles.muted}>Текстовых отзывов пока нет.</p> : null}
                          {reviews?.items.map((review) => <ReviewContent key={String(review.id)} review={review} />)}
                          {reviews?.hasMore ? (
                            <div className={styles.loadMore}>
                              <Button type="button" size="sm" onClick={() => void loadReviews(target.nm_id, true)} disabled={reviews.loadingMore}>
                                {reviews.loadingMore ? 'Загружаем…' : `Показать ещё (${reviews.total - reviews.items.length})`}
                              </Button>
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {analysisTarget ? (
        <div className={styles.drawer} role="dialog" aria-modal="true" aria-label="Выводы по отзывам">
          <button type="button" className={styles.drawerOverlay} aria-label="Закрыть анализ" onClick={() => {
            setAnalysisTarget(null)
            setAnalysisState(null)
          }} />
          <aside className={styles.drawerPanel}>
            <header className={styles.drawerHeader}>
              <div>
                <span className={styles.drawerEyebrow}>Выводы по отзывам</span>
                <h2>{analysisTarget.title || `nmID ${analysisTarget.nm_id}`}</h2>
                <p>{formatCount(analysisState?.reviews_with_text ?? analysisTarget.text_reviews_count)} текстовых отзывов</p>
              </div>
              <button type="button" className={styles.drawerClose} aria-label="Закрыть" onClick={() => {
                setAnalysisTarget(null)
                setAnalysisState(null)
              }}>×</button>
            </header>

            <div className={styles.drawerBody}>
              {loadingAnalysis ? <p className={styles.muted}>Загружаем анализ…</p> : null}

              {!loadingAnalysis && analysisState?.latest?.status === 'queued' ? (
                <div className={styles.analysisProgress}>
                  <Badge tone="info">В очереди</Badge>
                  <div><strong>Анализ поставлен в очередь</strong><p>Запуск начнётся автоматически в worker.</p></div>
                </div>
              ) : null}
              {!loadingAnalysis && analysisState?.latest?.status === 'running' ? (
                <div className={styles.analysisProgress}>
                  <Badge tone="info">В работе</Badge>
                  <div><strong>Анализируем отзывы</strong><p>Nano обрабатывает пакеты, затем Terra формирует выводы.</p></div>
                </div>
              ) : null}
              {!loadingAnalysis && analysisState?.latest?.status === 'failed' ? (
                <div className={styles.analysisFailure} role="alert">
                  <strong>Не удалось сформировать анализ</strong>
                  <p>{analysisErrorMessage(analysisState.latest.error_code, analysisState.latest.error_message)}</p>
                </div>
              ) : null}

              {analysisState?.is_stale && visibleAnalysis ? (
                <div className={styles.analysisStaleNotice}>
                  <Badge tone="warning">Есть новые отзывы</Badge>
                  <span>Текущий анализ сохранён, но был сформирован до последнего сбора.</span>
                </div>
              ) : null}

              {visibleAnalysis?.result ? (
                <>
                  <section className={styles.analysisConclusion}>
                    <h3>Общий вывод</h3>
                    <p>{visibleAnalysis.result.overall_conclusion}</p>
                  </section>
                  <AnalysisFindingSection title="Что нравится покупателям" items={visibleAnalysis.result.strengths} tone="success" />
                  <AnalysisFindingSection title="Что не нравится" items={visibleAnalysis.result.weaknesses} tone="danger" />
                  <AnalysisFindingSection title="Что можно улучшить" items={visibleAnalysis.result.opportunities} tone="info" />
                  {visibleAnalysis.result.conflicts.length > 0 ? (
                    <section className={styles.analysisSection}>
                      <h3>Противоречивые мнения</h3>
                      <div className={styles.analysisList}>
                        {visibleAnalysis.result.conflicts.map((item) => (
                          <article className={styles.analysisFinding} key={`conflict-${item.label}`}>
                            <div className={styles.analysisFindingHeader}>
                              <strong>{item.label}</strong>
                              <span>{formatCount(item.support_count)} отзывов</span>
                            </div>
                            <p>{item.summary}</p>
                          </article>
                        ))}
                      </div>
                    </section>
                  ) : null}
                </>
              ) : null}

              {!loadingAnalysis && analysisState && !visibleAnalysis && analysisState.latest?.status !== 'queued' && analysisState.latest?.status !== 'running' ? (
                <div className={styles.analysisEmpty}>
                  <h3>Анализ ещё не сформирован</h3>
                  <p>Отзывы будут обработаны пакетами Nano, итоговые выводы сформирует Terra.</p>
                </div>
              ) : null}
            </div>

            {analysisState ? (
              <footer className={styles.drawerFooter}>
                <div className={styles.analysisCost}>
                  <span>Оценка стоимости</span>
                  <strong>{formatUsd(analysisState.estimated_cost_usd)}</strong>
                  {visibleAnalysis?.actual_cost_usd != null ? <small>Фактически: {formatUsd(visibleAnalysis.actual_cost_usd)}</small> : null}
                </div>
                <Button
                  type="button"
                  variant="primary"
                  onClick={() => void startAnalysis(analysisTarget, Boolean(visibleAnalysis))}
                  disabled={!analysisState.can_generate || startingAnalysis || analysisState.latest?.status === 'queued' || analysisState.latest?.status === 'running'}
                >
                  {startingAnalysis ? 'Запускаем…' : visibleAnalysis ? 'Сформировать заново' : 'Проанализировать'}
                </Button>
              </footer>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  )
}
