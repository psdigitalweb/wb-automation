'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation'
import CategoryMultiSelectPopover from '@/components/CategoryMultiSelectPopover'
import PortalBackButton from '@/components/PortalBackButton'
import { usePageTitle } from '@/hooks/usePageTitle'
import { apiDownload, apiGetData, apiPost } from '@/lib/apiClient'
import styles from '../price-discrepancies/price-discrepancies.module.css'
import analyticsStyles from './price-analytics.module.css'

type TriState = 'any' | 'true' | 'false'

interface PriceAnalyticsItem {
  article: string | null
  nm_id: number | null
  title: string | null
  category: { id: number | null; name: string | null } | null
  photos: string[]
  prices: {
    wb_admin_price: number | null
    rrp_price: number | null
    showcase_price: number | null
  }
  discounts: {
    wb_discount_percent: number | null
    spp_percent: number | null
  }
  stocks: {
    wb_stock_qty: number
    fbo_stock_qty: number
    enterprise_stock_qty: number
  }
  computed: {
    is_below_rrp: boolean
    diff_rub: number | null
    diff_percent: number | null
  }
}

interface PriceAnalyticsResponse {
  meta: {
    total_count: number
    page: number
    page_size: number
    updated_at?: string
    front_snapshot_at?: string | null
    rrp_snapshot_count?: number
  }
  items: PriceAnalyticsItem[]
}

interface CategoryOption {
  id: number
  name: string | null
}

interface FrontSnapshotOption {
  snapshot_at: string | null
  items_count: number
}

interface BulkPriceApplyResult {
  status: 'accepted' | 'skipped'
  accepted_count: number
  skipped_count: number
  ready: Array<{ nm_id: number; article?: string | null }>
  skipped: Array<{ nm_id: number; article?: string | null; message?: string }>
}

interface FiltersState {
  q: string
  categoryIds: number[]
  showcase: TriState
  hasWbStock: TriState
  onlyBelowRrp: boolean
  frontSnapshotAt: string
  sort: string
  page: number
  pageSize: number
  showAll: boolean
}

function parseCategoryIds(value: string | null): number[] {
  return (value || '')
    .split(',')
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isFinite(value) && value > 0)
}

function parseFilters(searchParams: URLSearchParams): FiltersState {
  const page = Number(searchParams.get('page') || 1)
  const pageSize = Number(searchParams.get('page_size') || 25)
  const showcase = searchParams.get('has_showcase_price') as TriState | null
  const hasWbStock = searchParams.get('has_wb_stock') as TriState | null

  return {
    q: searchParams.get('q') || '',
    categoryIds: parseCategoryIds(searchParams.get('category_ids')),
    showcase: showcase === 'true' || showcase === 'false' ? showcase : 'any',
    hasWbStock: hasWbStock === 'true' || hasWbStock === 'false' ? hasWbStock : 'any',
    onlyBelowRrp: searchParams.get('only_below_rrp') === 'true',
    frontSnapshotAt: searchParams.get('front_snapshot_at') || '',
    sort: searchParams.get('sort') || 'showcase_price_desc',
    page: Number.isFinite(page) && page > 0 ? page : 1,
    pageSize: Number.isFinite(pageSize) && pageSize > 0 ? pageSize : 25,
    showAll: searchParams.get('show_all') === 'true',
  }
}

function formatCurrency(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '—'
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU')
}

function buildApiQuery(filters: FiltersState, page: number, pageSize: number): URLSearchParams {
  const query = new URLSearchParams()
  if (filters.q) query.set('q', filters.q)
  if (filters.categoryIds.length) query.set('category_ids', filters.categoryIds.join(','))
  if (filters.showcase !== 'any') query.set('has_showcase_price', filters.showcase)
  if (filters.hasWbStock !== 'any') query.set('has_wb_stock', filters.hasWbStock)
  if (filters.frontSnapshotAt) query.set('front_snapshot_at', filters.frontSnapshotAt)
  query.set('only_below_rrp', String(filters.onlyBelowRrp))
  query.set('sort', filters.sort)
  query.set('page', String(page))
  query.set('page_size', String(pageSize))
  return query
}

function getItemKey(item: PriceAnalyticsItem, index: number): string {
  return `${item.nm_id ?? 'nm'}-${item.article ?? 'article'}-${index}`
}

interface BulkPriceEditModalProps {
  projectId: string
  items: PriceAnalyticsItem[]
  onClose: () => void
  onApplied: () => void
}

function BulkPriceEditModal({ projectId, items, onClose, onApplied }: BulkPriceEditModalProps) {
  const [drafts, setDrafts] = useState<Record<number, { price: string; discount: string }>>({})
  const [status, setStatus] = useState<'ready' | 'sending' | 'success' | 'error'>('ready')
  const [message, setMessage] = useState<string | null>(null)
  const [result, setResult] = useState<BulkPriceApplyResult | null>(null)

  useEffect(() => {
    setDrafts(
      Object.fromEntries(
        items
          .filter((item): item is PriceAnalyticsItem & { nm_id: number } => item.nm_id !== null)
          .map((item) => [
            item.nm_id,
            {
              price: item.prices.wb_admin_price === null ? '' : String(Math.round(item.prices.wb_admin_price)),
              discount:
                item.discounts.wb_discount_percent === null
                  ? '0'
                  : String(Math.round(item.discounts.wb_discount_percent)),
            },
          ]),
      ),
    )
    setStatus('ready')
    setMessage(null)
    setResult(null)
  }, [items])

  if (!items.length) return null

  const editableItems = items.filter(
    (item): item is PriceAnalyticsItem & { nm_id: number } => item.nm_id !== null,
  )
  const invalidItems = editableItems.filter((item) => {
    const draft = drafts[item.nm_id]
    const price = Number(draft?.price)
    const discount = Number(draft?.discount)
    return (
      !draft ||
      !Number.isInteger(price) ||
      price <= 0 ||
      !Number.isInteger(discount) ||
      discount < 0 ||
      discount > 99
    )
  })
  const requestInProgress = status === 'sending'
  const submitDisabled = requestInProgress || status === 'success' || !editableItems.length || invalidItems.length > 0

  const updateDraft = (nmId: number, patch: Partial<{ price: string; discount: string }>) => {
    setDrafts((current) => ({
      ...current,
      [nmId]: { ...current[nmId], ...patch },
    }))
  }

  const handleSubmit = async () => {
    if (submitDisabled) return
    setStatus('sending')
    setMessage('Отправляем изменения цен на Wildberries…')
    setResult(null)
    try {
      const { data } = await apiPost<BulkPriceApplyResult>(
        `/api/v1/projects/${projectId}/wildberries/price-discrepancies/price-apply/bulk`,
        {
          items: editableItems.map((item) => ({
            nm_id: item.nm_id,
            price: Number(drafts[item.nm_id].price),
            discount: Number(drafts[item.nm_id].discount),
          })),
        },
      )
      setResult(data)
      if (data.accepted_count > 0) {
        setStatus('success')
        setMessage(
          data.skipped_count > 0
            ? `Отправлено: ${data.accepted_count}. Пропущено: ${data.skipped_count}.`
            : `Wildberries принял изменения для ${data.accepted_count} товаров.`,
        )
      } else {
        setStatus('error')
        setMessage(data.skipped[0]?.message || 'Нет товаров, доступных для массового изменения.')
      }
    } catch (caught: any) {
      setStatus('error')
      setMessage(caught?.detail || caught?.message || 'Не удалось отправить изменения на Wildberries')
    }
  }

  const handleClose = () => {
    if (requestInProgress) return
    if (status === 'success') onApplied()
    onClose()
  }

  return (
    <div className={styles.modalOverlay} role="presentation" onMouseDown={handleClose}>
      <div
        className={`${styles.modalDialog} ${styles.bulkModalDialog}`}
        role="dialog"
        aria-modal="true"
        aria-label="Массовое изменение цен WB"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.modalHeader}>
          <div>
            <h2>Изменить цены</h2>
            <span>Выбрано товаров: {items.length}</span>
          </div>
          <button type="button" className={styles.modalClose} onClick={handleClose} disabled={requestInProgress} aria-label="Закрыть">
            ×
          </button>
        </div>

        <p className={analyticsStyles.bulkWarning}>
          После подтверждения цены и скидки будут отправлены в кабинет Wildberries одним заданием.
        </p>

        {message && (
          <p className={`${styles.modalMessage} ${status === 'error' ? styles.modalError : ''}`}>{message}</p>
        )}

        <div className={analyticsStyles.priceEditList}>
          <div className={analyticsStyles.priceEditHeader}>
            <span>Товар</span>
            <span>Цена, ₽</span>
            <span>Скидка, %</span>
            <span>Результат</span>
          </div>
          {editableItems.map((item) => {
            const draft = drafts[item.nm_id]
            const skipped = result?.skipped.find((entry) => entry.nm_id === item.nm_id)
            const accepted = result?.ready.some((entry) => entry.nm_id === item.nm_id)
            return (
              <div key={item.nm_id} className={analyticsStyles.priceEditRow}>
                <div className={analyticsStyles.priceEditProduct}>
                  <strong>{item.article || `nmID ${item.nm_id}`}</strong>
                  <span>{item.title || `nmID ${item.nm_id}`}</span>
                </div>
                <input
                  aria-label={`Цена ${item.article || item.nm_id}`}
                  type="number"
                  min="1"
                  step="1"
                  value={draft?.price ?? ''}
                  disabled={requestInProgress || status === 'success'}
                  onChange={(event) => updateDraft(item.nm_id, { price: event.target.value })}
                />
                <input
                  aria-label={`Скидка ${item.article || item.nm_id}`}
                  type="number"
                  min="0"
                  max="99"
                  step="1"
                  value={draft?.discount ?? ''}
                  disabled={requestInProgress || status === 'success'}
                  onChange={(event) => updateDraft(item.nm_id, { discount: event.target.value })}
                />
                <span className={skipped ? analyticsStyles.resultError : accepted ? analyticsStyles.resultSuccess : ''}>
                  {skipped?.message || (accepted ? 'Отправлено' : 'Готово')}
                </span>
              </div>
            )
          })}
        </div>

        {invalidItems.length > 0 && (
          <p className={`${styles.modalMessage} ${styles.modalError}`}>
            Укажите целую цену больше нуля и скидку от 0 до 99% для каждого товара.
          </p>
        )}

        <div className={styles.modalActions}>
          <button type="button" className={styles.buttonSecondary} onClick={handleClose} disabled={requestInProgress}>
            Закрыть
          </button>
          <button type="button" className={styles.buttonPrimary} onClick={handleSubmit} disabled={submitDisabled}>
            {status === 'success' ? 'Изменения отправлены' : requestInProgress ? 'Отправляем…' : 'Отправить на WB'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function WbPriceAnalyticsPage() {
  const params = useParams()
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = params.projectId as string
  usePageTitle('Аналитика цен', projectId)

  const [items, setItems] = useState<PriceAnalyticsItem[]>([])
  const [meta, setMeta] = useState<PriceAnalyticsResponse['meta'] | null>(null)
  const [categories, setCategories] = useState<CategoryOption[]>([])
  const [frontSnapshots, setFrontSnapshots] = useState<FrontSnapshotOption[]>([])
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchValue, setSearchValue] = useState('')
  const [isReportsHost, setIsReportsHost] = useState(false)
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set())
  const [bulkEditOpen, setBulkEditOpen] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const requestSequence = useRef(0)

  const searchParamsKey = searchParams.toString()
  const filters = useMemo(
    () => parseFilters(new URLSearchParams(searchParamsKey)),
    [searchParamsKey],
  )
  const hasRrpCatalog = (meta?.rrp_snapshot_count ?? 0) > 0
  const allRowsSelected = items.length > 0 && items.every((item, index) => selectedRows.has(getItemKey(item, index)))
  const selectedItems = useMemo(
    () => items.filter((item, index) => selectedRows.has(getItemKey(item, index))),
    [items, selectedRows],
  )

  useEffect(() => setSearchValue(filters.q), [filters.q])

  useEffect(() => {
    setSelectedRows(new Set())
    setBulkEditOpen(false)
  }, [searchParamsKey])

  useEffect(() => {
    setIsReportsHost(window.location.hostname === 'reports.zakka.ru')
  }, [])

  const updateQuery = (patch: Partial<FiltersState>, resetPage = true) => {
    const next = { ...filters, ...patch, page: resetPage ? 1 : (patch.page ?? filters.page) }
    const query = new URLSearchParams()
    if (next.q) query.set('q', next.q)
    if (next.categoryIds.length) query.set('category_ids', next.categoryIds.join(','))
    if (next.showcase !== 'any') query.set('has_showcase_price', next.showcase)
    if (next.hasWbStock !== 'any') query.set('has_wb_stock', next.hasWbStock)
    if (next.onlyBelowRrp) query.set('only_below_rrp', 'true')
    if (next.frontSnapshotAt) query.set('front_snapshot_at', next.frontSnapshotAt)
    if (next.sort !== 'showcase_price_desc') query.set('sort', next.sort)
    if (next.page !== 1) query.set('page', String(next.page))
    if (next.pageSize !== 25) query.set('page_size', String(next.pageSize))
    if (next.showAll) query.set('show_all', 'true')
    const targetPath = pathname || `/app/project/${projectId}/wildberries/price-analytics`
    router.push(query.size ? `${targetPath}?${query}` : targetPath)
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (searchValue !== filters.q) updateQuery({ q: searchValue })
    }, 350)
    return () => window.clearTimeout(timer)
  }, [searchValue, filters.q])

  useEffect(() => {
    let cancelled = false
    const currentSequence = ++requestSequence.current

    async function load() {
      setLoading(true)
      setError(null)
      try {
        let response: PriceAnalyticsResponse
        if (filters.showAll) {
          const allItems: PriceAnalyticsItem[] = []
          let page = 1
          let firstResponse: PriceAnalyticsResponse | null = null
          while (true) {
            const query = buildApiQuery(filters, page, 200)
            const current = await apiGetData<PriceAnalyticsResponse>(
              `/api/v1/projects/${projectId}/wildberries/price-discrepancies?${query}`,
            )
            if (cancelled) return
            firstResponse ||= current
            allItems.push(...(current.items || []))
            if (!current.items?.length || allItems.length >= (current.meta?.total_count || 0)) break
            page += 1
          }
          response = {
            items: allItems,
            meta: {
              ...(firstResponse?.meta || { total_count: allItems.length, page: 1, page_size: allItems.length }),
              page: 1,
              page_size: Math.max(1, allItems.length),
            },
          }
        } else {
          const query = buildApiQuery(filters, filters.page, filters.pageSize)
          response = await apiGetData<PriceAnalyticsResponse>(
            `/api/v1/projects/${projectId}/wildberries/price-discrepancies?${query}`,
          )
        }
        if (cancelled || currentSequence !== requestSequence.current) return
        setItems(response.items || [])
        setMeta(response.meta)
      } catch (caught: any) {
        if (cancelled || currentSequence !== requestSequence.current) return
        setItems([])
        setError(caught?.detail || caught?.message || 'Не удалось загрузить аналитику цен')
      } finally {
        if (!cancelled && currentSequence === requestSequence.current) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [projectId, searchParamsKey, reloadToken])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      apiGetData<{ items: CategoryOption[] }>(`/api/v1/projects/${projectId}/wildberries/categories`),
      apiGetData<{ items: FrontSnapshotOption[] }>(
        `/api/v1/projects/${projectId}/wildberries/price-discrepancies/front-snapshots?limit=50`,
      ),
    ])
      .then(([categoryResponse, snapshotResponse]) => {
        if (cancelled) return
        setCategories(categoryResponse.items || [])
        setFrontSnapshots(snapshotResponse.items || [])
      })
      .catch(() => {
        if (cancelled) return
        setCategories([])
        setFrontSnapshots([])
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const exportCsv = async () => {
    setExporting(true)
    setError(null)
    try {
      const query = buildApiQuery(filters, 1, 200)
      query.delete('page')
      query.delete('page_size')
      const { blob, filename } = await apiDownload(
        `/api/v1/projects/${projectId}/wildberries/price-discrepancies/export.csv?${query}`,
      )
      const objectUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = filename || 'wb_price_analytics.csv'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000)
    } catch (caught: any) {
      setError(caught?.detail || caught?.message || 'Не удалось скачать CSV')
    } finally {
      setExporting(false)
    }
  }

  const totalPages = meta ? Math.max(1, Math.ceil(meta.total_count / meta.page_size)) : 1

  return (
    <div className={styles.page}>
      {isReportsHost && (
        <div className={styles.portalBack}>
          <PortalBackButton fallbackHref="/client" />
        </div>
      )}

      <div className={styles.reportHeader}>
        <div className={styles.reportTitleBlock}>
          <div className={styles.reportTitleRow}>
            <h1>Аналитика цен</h1>
            <span className={styles.marketplaceBadge}><span />Wildberries</span>
          </div>
        </div>
        <div className={styles.headerActions}>
          <button type="button" className={styles.buttonSecondary} onClick={exportCsv} disabled={exporting}>
            <span className={styles.headerActionIcon}>↓</span>
            {exporting ? 'Экспортируем CSV…' : 'Экспорт CSV'}
          </button>
        </div>
      </div>

      <div className={styles.savedViewsCard}>
        <div className={styles.savedViewsRow}>
          <button
            type="button"
            className={`${styles.savedView} ${filters.showcase === 'any' && !filters.onlyBelowRrp ? styles.savedViewActive : ''}`}
            onClick={() => updateQuery({ showcase: 'any', onlyBelowRrp: false })}
          >
            Все позиции
            {filters.showcase === 'any' && !filters.onlyBelowRrp && typeof meta?.total_count === 'number' && (
              <span className={styles.savedViewCount}>{meta.total_count}</span>
            )}
          </button>
          <button
            type="button"
            className={`${styles.savedView} ${filters.showcase === 'true' && !filters.onlyBelowRrp ? styles.savedViewActive : ''}`}
            onClick={() => updateQuery({ showcase: 'true', onlyBelowRrp: false })}
          >
            Есть цена на витрине
          </button>
          <button
            type="button"
            className={`${styles.savedView} ${filters.showcase === 'false' && !filters.onlyBelowRrp ? styles.savedViewActive : ''}`}
            onClick={() => updateQuery({ showcase: 'false', onlyBelowRrp: false })}
          >
            Нет цены на витрине
          </button>
          <span
            className={analyticsStyles.disabledFilterHint}
            data-tooltip={!hasRrpCatalog ? 'Для сравнения с РРЦ загрузите каталог с РРЦ' : undefined}
            tabIndex={!hasRrpCatalog ? 0 : undefined}
          >
            <button
              type="button"
              disabled={!hasRrpCatalog}
              className={`${styles.savedView} ${filters.onlyBelowRrp ? `${styles.savedViewActive} ${styles.savedViewSuccess}` : ''}`}
              onClick={() => updateQuery({ showcase: 'any', onlyBelowRrp: true })}
            >
              Ниже РРЦ
            </button>
          </span>
        </div>
      </div>

      <div className={styles.filterToolbar}>
        <div className={styles.filterRow}>
          <div className={styles.searchControl}>
            <span>⌕</span>
            <input
              aria-label="Поиск по артикулу, nmID или названию"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder="Артикул / nmID / название..."
            />
          </div>
          <div className={styles.categoryFilter}>
            {categories.length ? (
              <CategoryMultiSelectPopover
                categories={categories}
                selectedIds={filters.categoryIds}
                onChange={(categoryIds) => updateQuery({ categoryIds })}
                fullWidth
              />
            ) : (
              <button type="button" className={styles.toolbarButton} disabled>Категория</button>
            )}
          </div>
          <label className={styles.snapshotSelect}>
            <select
              aria-label="Снимок витрины"
              value={filters.frontSnapshotAt}
              onChange={(event) => updateQuery({ frontSnapshotAt: event.target.value })}
            >
              <option value="">Витрина: последняя</option>
              {frontSnapshots.filter((snapshot) => snapshot.snapshot_at).map((snapshot) => (
                <option key={snapshot.snapshot_at} value={snapshot.snapshot_at || ''}>
                  Витрина: {formatDate(snapshot.snapshot_at)} ({snapshot.items_count})
                </option>
              ))}
            </select>
          </label>
          <div className={styles.toolbarSpacer} />
          <label className={styles.sortControl}>
            <span>Сортировка:</span>
            <select value={filters.sort} onChange={(event) => updateQuery({ sort: event.target.value })}>
              <option value="showcase_price_desc">Витрина ↓</option>
              <option value="showcase_price_asc">Витрина ↑</option>
              <option value="wb_admin_price_desc">Цена WB ↓</option>
              <option value="wb_admin_price_asc">Цена WB ↑</option>
              <option value="wb_discount_desc">Скидка продавца ↓</option>
              <option value="spp_desc">СПП ↓</option>
              <option value="nm_id_asc">nmID ↑</option>
            </select>
          </label>
        </div>
      </div>

      {loading && <p className={styles.loadingText}>Загрузка данных…</p>}
      {error && <div className={styles.errorCard}><p><strong>Ошибка:</strong> {error}</p></div>}
      {!loading && !error && !items.length && (
        <div className={styles.emptyCard}><p>Нет товаров с текущими фильтрами.</p></div>
      )}
      {!loading && !error && items.length > 0 && (
        <div className={styles.tableCard}>
          {selectedRows.size > 0 && (
            <div className={styles.bulkBar}>
              <span>Выбрано товаров: {selectedRows.size}</span>
              <div className={styles.bulkActions}>
                <button type="button" className={styles.buttonPrimary} onClick={() => setBulkEditOpen(true)}>
                  Изменить цены
                </button>
                <button type="button" onClick={() => setSelectedRows(new Set())}>Снять выделение</button>
              </div>
            </div>
          )}
          <div className={styles.tableWrap}>
            <table className={`${styles.rrpTable} ${analyticsStyles.analyticsTable}`}>
              <colgroup>
                <col style={{ width: 34 }} />
                <col style={{ width: 48 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 280 }} />
                <col style={{ width: 92 }} />
                <col style={{ width: 116 }} />
                <col style={{ width: 64 }} />
                <col style={{ width: 118 }} />
                <col style={{ width: 72 }} />
                <col style={{ width: 92 }} />
                <col style={{ width: 92 }} />
              </colgroup>
              <thead>
                <tr>
                  <th className={`${styles.sticky} ${styles.stickySelect} ${styles.selectCol}`}>
                    <input
                      type="checkbox"
                      className={styles.rowCheck}
                      checked={allRowsSelected}
                      onChange={() => {
                        if (allRowsSelected) {
                          setSelectedRows(new Set())
                        } else {
                          setSelectedRows(new Set(items.map((item, index) => getItemKey(item, index))))
                        }
                      }}
                      aria-label="Выбрать все товары на странице"
                    />
                  </th>
                  <th className={`${styles.sticky} ${styles.stickyPhoto} ${analyticsStyles.stickyPhoto} ${styles.photoCol}`}>Фото</th>
                  <th className={`${styles.sticky} ${styles.stickySku} ${analyticsStyles.stickySku} ${styles.skuCol}`}>Артикул</th>
                  <th className={`${styles.sticky} ${styles.stickyTitle} ${analyticsStyles.stickyTitle} ${styles.titleCol}`}>Название</th>
                  <th className={styles.num}>Цена WB</th>
                  <th className={`${styles.num} ${analyticsStyles.sellerDiscountHeader}`}>Скидка продавца</th>
                  <th className={styles.num}>СПП</th>
                  <th className={styles.num}>Цена на витрине</th>
                  <th className={styles.num}>РРЦ</th>
                  <th className={styles.num}>Остаток FBS</th>
                  <th className={styles.num}>Остаток FBO</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => {
                  const itemKey = getItemKey(item, index)
                  return (
                  <tr key={itemKey} className={item.prices.showcase_price === null ? styles.mutedRow : undefined}>
                    <td className={`${styles.sticky} ${styles.stickySelect} ${styles.selectCol}`}>
                      <input
                        type="checkbox"
                        className={styles.rowCheck}
                        checked={selectedRows.has(itemKey)}
                        onChange={() => setSelectedRows((current) => {
                          const next = new Set(current)
                          if (next.has(itemKey)) next.delete(itemKey)
                          else next.add(itemKey)
                          return next
                        })}
                        aria-label={`Выбрать товар ${item.article || item.nm_id || index + 1}`}
                      />
                    </td>
                    <td className={`${styles.sticky} ${styles.stickyPhoto} ${analyticsStyles.stickyPhoto} ${styles.photoCol}`}>
                      {item.photos[0] ? (
                        <img src={item.photos[0]} alt="" width={28} height={36} style={{ display: 'block', objectFit: 'cover', borderRadius: 4 }} />
                      ) : '—'}
                    </td>
                    <td className={`${styles.sticky} ${styles.stickySku} ${analyticsStyles.stickySku} ${styles.skuCol}`}>
                      <div className={styles.skuText}>{item.article || '—'}</div>
                      {item.nm_id ? (
                        <a className={styles.nmLink} href={`https://www.wildberries.ru/catalog/${item.nm_id}/detail.aspx`} target="_blank" rel="noreferrer">
                          {item.nm_id}
                        </a>
                      ) : '—'}
                    </td>
                    <td className={`${styles.sticky} ${styles.stickyTitle} ${analyticsStyles.stickyTitle} ${styles.titleCol}`}>
                      <div className={styles.productTitle}>{item.title || '—'}</div>
                      <div className={styles.productMeta}>{item.category?.name || 'Без категории'}</div>
                    </td>
                    <td className={`${styles.num} ${styles.priceCell}`}>{formatCurrency(item.prices.wb_admin_price)}</td>
                    <td className={styles.num}>{formatPercent(item.discounts.wb_discount_percent)}</td>
                    <td className={styles.num}>{formatPercent(item.discounts.spp_percent)}</td>
                    <td className={`${styles.num} ${styles.priceCell}`}>{formatCurrency(item.prices.showcase_price)}</td>
                    <td className={`${styles.num} ${styles.priceCell}`}>{formatCurrency(item.prices.rrp_price)}</td>
                    <td className={`${styles.num} ${styles.stock}`}>{item.stocks.wb_stock_qty}</td>
                    <td className={`${styles.num} ${styles.stock}`}>{item.stocks.fbo_stock_qty ?? 0}</td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {meta && (
            <div className={styles.tableFooter}>
              <span>Показано <strong>{items.length}</strong> из <strong>{meta.total_count}</strong> позиций</span>
              <button type="button" onClick={() => updateQuery({ showAll: !filters.showAll })}>
                {filters.showAll ? 'Вернуть пагинацию' : 'Показать все'}
              </button>
              {!filters.showAll && (
                <>
                  <button type="button" disabled={filters.page <= 1} onClick={() => updateQuery({ page: filters.page - 1 }, false)}>Назад</button>
                  <span>Страница {filters.page} из {totalPages}</span>
                  <button type="button" disabled={filters.page >= totalPages} onClick={() => updateQuery({ page: filters.page + 1 }, false)}>Вперед</button>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {bulkEditOpen && (
        <BulkPriceEditModal
          projectId={projectId}
          items={selectedItems}
          onClose={() => setBulkEditOpen(false)}
          onApplied={() => {
            setSelectedRows(new Set())
            setReloadToken((value) => value + 1)
          }}
        />
      )}
    </div>
  )
}
