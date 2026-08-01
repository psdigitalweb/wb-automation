'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useReportFilterOptions } from '@/hooks/useReportFilterOptions'
import { normalizeReportPeriod } from '@/lib/reportFilterOptions'
import { ReportDataCoverage } from '@/components/ui-v2/ReportDataCoverage'
import {
  getWBCatalog,
  type WBCatalogParams,
  type WBCatalogResponse,
} from '@/lib/wbCatalogApi'
import {
  CatalogFilters,
  type CatalogFilterValues,
} from './_components/CatalogFilters'
import { CatalogTable } from './_components/CatalogTable'
import styles from './catalog.module.css'

function initialFilters(searchParams: URLSearchParams): CatalogFilterValues {
  const sortParam = searchParams.get('sort')
  const orderParam = searchParams.get('order')
  return {
    q: searchParams.get('q') ?? '',
    periodFrom: searchParams.get('period_from') ?? '',
    periodTo: searchParams.get('period_to') ?? '',
    activity: searchParams.get('activity') === 'active' ? 'active' : 'all',
    sort:
      sortParam === 'title' ||
      sortParam === 'vendor_code' ||
      sortParam === 'price' ||
      sortParam === 'rating' ||
      sortParam === 'impressions' ||
      sortParam === 'ctr' ||
      sortParam === 'opens' ||
      sortParam === 'carts' ||
      sortParam === 'orders' ||
      sortParam === 'buyouts'
        ? sortParam
        : 'order_sum',
    order: orderParam === 'asc' ? 'asc' : 'desc',
  }
}

function formatFreshness(value: string | null | undefined) {
  if (!value) return 'нет данных'
  const dateOnly = value.slice(0, 10)
  const parsed = new Date(`${dateOnly}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU').format(parsed)
}

export default function WBCatalogPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = typeof params?.projectId === 'string' ? params.projectId : ''
  usePageTitle('Каталог товаров WB', projectId || null)
  const { options: reportOptions } = useReportFilterOptions(projectId, 'catalog')

  const initial = useMemo(
    () => initialFilters(new URLSearchParams(searchParams.toString())),
    [searchParams],
  )
  const [draftFilters, setDraftFilters] = useState<CatalogFilterValues>(initial)
  const [appliedFilters, setAppliedFilters] =
    useState<CatalogFilterValues>(initial)
  const [page, setPage] = useState(
    Math.max(1, Number(searchParams.get('page') ?? 1) || 1),
  )
  const [pageSize, setPageSize] = useState(
    [25, 50, 100].includes(Number(searchParams.get('page_size')))
      ? Number(searchParams.get('page_size'))
      : 50,
  )
  const [data, setData] = useState<WBCatalogResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const replaceUrl = useCallback(
    (
      filters: CatalogFilterValues,
      nextPage: number,
      nextPageSize: number,
    ) => {
      const query = new URLSearchParams()
      if (filters.q.trim()) query.set('q', filters.q.trim())
      if (filters.periodFrom) query.set('period_from', filters.periodFrom)
      if (filters.periodTo) query.set('period_to', filters.periodTo)
      query.set('activity', filters.activity)
      query.set('sort', filters.sort)
      query.set('order', filters.order)
      query.set('page', String(nextPage))
      query.set('page_size', String(nextPageSize))
      router.replace(
        `/app/project/${projectId}/wildberries/catalog?${query.toString()}`,
        { scroll: false },
      )
    },
    [projectId, router],
  )

  useEffect(() => {
    if (!reportOptions) return
    const normalized = normalizeReportPeriod(
      reportOptions,
      appliedFilters.periodFrom,
      appliedFilters.periodTo,
    )
    if (
      normalized.from === appliedFilters.periodFrom &&
      normalized.to === appliedFilters.periodTo
    ) return
    const next = {
      ...appliedFilters,
      periodFrom: normalized.from,
      periodTo: normalized.to,
    }
    setAppliedFilters(next)
    setDraftFilters(next)
    setPage(1)
    replaceUrl(next, 1, pageSize)
  }, [appliedFilters, pageSize, replaceUrl, reportOptions])

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    const request: WBCatalogParams = {
      q: appliedFilters.q.trim() || undefined,
      period_from: appliedFilters.periodFrom || undefined,
      period_to: appliedFilters.periodTo || undefined,
      activity: appliedFilters.activity,
      sort: appliedFilters.sort,
      order: appliedFilters.order,
      page,
      page_size: pageSize,
    }

    setLoading(true)
    setError(null)
    getWBCatalog(projectId, request)
      .then((response) => {
        if (cancelled) return
        if (
          appliedFilters.activity === 'active' &&
          response.meta.total === 0 &&
          !response.data_freshness.showcase_at
        ) {
          const allProductsFilters = {
            ...appliedFilters,
            activity: 'all' as const,
          }
          setAppliedFilters(allProductsFilters)
          setDraftFilters(allProductsFilters)
          replaceUrl(allProductsFilters, 1, pageSize)
          return
        }
        setData(response)
        if (!appliedFilters.periodFrom && !appliedFilters.periodTo) {
          const withPeriod = {
            ...appliedFilters,
            periodFrom: response.meta.period_from,
            periodTo: response.meta.period_to,
          }
          setAppliedFilters(withPeriod)
          setDraftFilters(withPeriod)
          replaceUrl(withPeriod, page, pageSize)
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        const message =
          typeof caught === 'object' &&
          caught !== null &&
          'detail' in caught &&
          typeof caught.detail === 'string'
            ? caught.detail
            : 'Не удалось загрузить каталог'
        setError(message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [
    appliedFilters,
    page,
    pageSize,
    projectId,
    replaceUrl,
  ])

  const applyFilters = () => {
    if (
      (draftFilters.periodFrom && !draftFilters.periodTo) ||
      (!draftFilters.periodFrom && draftFilters.periodTo)
    ) {
      setError('Укажите обе даты периода')
      return
    }
    if (
      draftFilters.periodFrom &&
      draftFilters.periodTo &&
      draftFilters.periodFrom > draftFilters.periodTo
    ) {
      setError('Дата начала должна быть раньше даты окончания')
      return
    }
    setPage(1)
    setAppliedFilters(draftFilters)
    replaceUrl(draftFilters, 1, pageSize)
  }

  const changeActivity = (activity: CatalogFilterValues['activity']) => {
    const nextFilters = { ...draftFilters, activity }
    setDraftFilters(nextFilters)
    setAppliedFilters(nextFilters)
    setPage(1)
    replaceUrl(nextFilters, 1, pageSize)
  }

  const changePage = (nextPage: number) => {
    setPage(nextPage)
    replaceUrl(appliedFilters, nextPage, pageSize)
  }

  const changePageSize = (nextPageSize: number) => {
    setPage(1)
    setPageSize(nextPageSize)
    replaceUrl(appliedFilters, 1, nextPageSize)
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Wildberries · Данные</div>
          <h1>Каталог товаров WB</h1>
          <p>
            Текущие карточки и показатели за выбранный период без дублирования
            истории цен.
          </p>
        </div>
      </header>

      <CatalogFilters
        values={draftFilters}
        loading={loading}
        onChange={setDraftFilters}
        onActivityChange={changeActivity}
        onApply={applyFilters}
        minDate={reportOptions?.date_filter.min_date}
        maxDate={reportOptions?.date_filter.max_date}
      />
      <ReportDataCoverage
        options={reportOptions}
        periodFrom={appliedFilters.periodFrom}
        periodTo={appliedFilters.periodTo}
      />

      {loading && !data && (
        <div className={styles.statusCard}>Загружаем каталог…</div>
      )}
      {error && !data && (
        <div className={`${styles.statusCard} ${styles.error}`}>{error}</div>
      )}
      {!loading && !error && data?.items.length === 0 && (
        <div className={styles.statusCard}>
          По выбранным условиям товары не найдены.
        </div>
      )}

      {data && data.items.length > 0 && (
        <>
          {error && <div className={`${styles.statusCard} ${styles.error}`}>{error}</div>}
          {!error && <CatalogTable items={data.items} projectId={projectId} />}
          <footer className={styles.footer}>
            <div className={styles.freshness}>
              Найдено: {data.meta.total}. Аналитика по{' '}
              {formatFreshness(data.data_freshness.analytics_through)}, цены
              обновлены {formatFreshness(data.data_freshness.prices_at)}, отзывы —{' '}
              {formatFreshness(data.data_freshness.reviews_at)}.
            </div>
            <div className={styles.pagination}>
              <select
                aria-label="Строк на странице"
                value={pageSize}
                onChange={(event) => changePageSize(Number(event.target.value))}
              >
                <option value={25}>25 строк</option>
                <option value={50}>50 строк</option>
                <option value={100}>100 строк</option>
              </select>
              <button
                type="button"
                disabled={page <= 1 || loading}
                onClick={() => changePage(page - 1)}
              >
                Назад
              </button>
              <span>
                {data.meta.page} из {Math.max(data.meta.pages, 1)}
              </span>
              <button
                type="button"
                disabled={page >= data.meta.pages || loading}
                onClick={() => changePage(page + 1)}
              >
                Далее
              </button>
            </div>
          </footer>
        </>
      )}
    </main>
  )
}
