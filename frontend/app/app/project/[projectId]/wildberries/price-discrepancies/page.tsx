'use client'

import { useEffect, useMemo, useState, useRef } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { apiGetData, apiPost } from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import CategoryMultiSelectPopover from '@/components/CategoryMultiSelectPopover'
import PortalBackButton from '@/components/PortalBackButton'

interface PriceDiscrepancyItem {
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
    enterprise_stock_qty: number
  }
  computed: {
    is_below_rrp: boolean
    diff_rub: number | null
    diff_percent: number | null
    recommended_wb_admin_price: number | null
    delta_recommended: number | null
    expected_showcase_price: number | null
  }
}

interface DiagnosticInfo {
  data_availability: {
    brand_id_configured: boolean
    brand_id: number | null
    rrp_snapshots_count: number
    rrp_snapshots_latest_snapshot_at?: string | null
    price_snapshots_count: number
    products_count: number
    frontend_catalog_price_snapshots_count: number
    stock_snapshots_count: number
    products_with_both_rrp_and_showcase: number
    internal_data_latest_snapshot?: {
      id: number | null
      imported_at: string | null
      status: string | null
      rows_imported: number | null
      rows_failed: number | null
    } | null
    internal_data_rrp_rows_found?: number
    internal_data_rrp_rows_matched_products?: number
    internal_data_rrp_rows_inserted?: number
    internal_data_rrp_errors_preview?: Array<{
      row_index: number | null
      source_key: string | null
      error_code: string | null
      message: string | null
      created_at: string | null
    }>
  }
  issues: string[]
  recommendations: string[]
}

interface PriceDiscrepancyResponse {
  meta: {
    total_count: number
    page: number
    page_size: number
    updated_at: string
  }
  items: PriceDiscrepancyItem[]
  diagnostic?: DiagnosticInfo
}

type HasStockFilter = 'any' | 'true' | 'false'

interface CategoryOption {
  id: number
  name: string | null
}

interface FiltersState {
  q: string
  categoryIds: number[]
  hasWbStock: HasStockFilter
  hasEnterpriseStock: HasStockFilter
  onlyBelowRrp: boolean
  sort: string
  page: number
  pageSize: number
}

function parseCategoryIdsParam(value: string | null): number[] {
  if (!value) return []
  return value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => Number(v))
    .filter((n) => !Number.isNaN(n))
}

function buildCategoryIdsParam(ids: number[]): string | null {
  if (!ids.length) return null
  return ids.join(',')
}

function parseFiltersFromSearchParams(searchParams: URLSearchParams): FiltersState {
  const q = searchParams.get('q') || ''
  const categoryIds = parseCategoryIdsParam(searchParams.get('category_ids'))
  const hasWbStock = (searchParams.get('has_wb_stock') as HasStockFilter) || 'any'
  const hasEnterpriseStock = (searchParams.get('has_enterprise_stock') as HasStockFilter) || 'any'
  const onlyBelowRrpParam = searchParams.get('only_below_rrp')
  const onlyBelowRrp = onlyBelowRrpParam === null ? true : onlyBelowRrpParam === 'true'
  const sort = searchParams.get('sort') || 'diff_rub_desc'
  const page = Number(searchParams.get('page') || '1')
  const pageSize = Number(searchParams.get('page_size') || '25')

  return {
    q,
    categoryIds,
    hasWbStock,
    hasEnterpriseStock,
    onlyBelowRrp,
    sort,
    page: Number.isNaN(page) || page < 1 ? 1 : page,
    pageSize: Number.isNaN(pageSize) || pageSize <= 0 ? 25 : pageSize,
  }
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPercent(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '0'
  return value.toString()
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('ru-RU')
  } catch {
    return '—'
  }
}

interface PhotoPopoverProps {
  photos: string[]
  size?: number
}

function PhotoPopover({ photos, size = 40 }: PhotoPopoverProps) {
  const [open, setOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [position, setPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const anchorRef = useRef<HTMLDivElement | null>(null)
  const popoverRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (!open) return
      const target = event.target as Node
      if (
        popoverRef.current &&
        !popoverRef.current.contains(target) &&
        anchorRef.current &&
        !anchorRef.current.contains(target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const hasPhotos = photos && photos.length > 0
  const thumbnailSrc = hasPhotos ? photos[0] : null

  const handleOpen = () => {
    if (!hasPhotos) return
    if (!open && anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect()
      setPosition({
        top: rect.bottom + window.scrollY + 8,
        left: rect.left + window.scrollX,
      })
    }
    setOpen(true)
  }

  const handleClose = () => {
    setOpen(false)
  }

  const toggleOpen = () => {
    if (!hasPhotos) return
    if (open) {
      handleClose()
    } else {
      handleOpen()
    }
  }

  return (
    <div
      style={{ position: 'relative', display: 'inline-block' }}
      ref={anchorRef}
      onMouseEnter={handleOpen}
      onMouseLeave={(e) => {
        // Закрываем только если курсор не перешёл на поповер
        const relatedTarget = e.relatedTarget as Node | null
        if (
          !popoverRef.current ||
          !relatedTarget ||
          (!popoverRef.current.contains(relatedTarget) &&
            !anchorRef.current?.contains(relatedTarget))
        ) {
          handleClose()
        }
      }}
    >
      {thumbnailSrc ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={thumbnailSrc}
          alt="Фото товара"
          style={{
            width: size,
            height: size,
            objectFit: 'cover',
            borderRadius: 4,
            cursor: 'pointer',
            border: '1px solid #ddd',
          }}
          loading="lazy"
          onClick={toggleOpen}
        />
      ) : (
        <div
          onClick={toggleOpen}
          style={{
            width: size,
            height: size,
            borderRadius: 4,
            border: '1px dashed #ccc',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 10,
            color: '#999',
            cursor: 'default',
          }}
        >
          Нет фото
        </div>
      )}

      {open && hasPhotos && (
        <div
          ref={popoverRef}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={handleClose}
          style={{
            position: 'absolute',
            zIndex: 1000,
            top: position.top - (anchorRef.current?.getBoundingClientRect().bottom || 0) - window.scrollY,
            left: 0,
            background: '#fff',
            border: '1px solid #ddd',
            borderRadius: 6,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            padding: 8,
            minWidth: 260,
            maxWidth: 480,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <strong style={{ fontSize: 12 }}>Фото товара</strong>
            <button type="button" onClick={() => setOpen(false)} style={{ fontSize: 12 }}>
              ✕
            </button>
          </div>
          <div style={{ textAlign: 'center', marginBottom: 8 }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photos[selectedIndex]}
              alt="Фото товара крупно"
              style={{ maxWidth: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 4 }}
              loading="lazy"
            />
          </div>
          <div
            style={{
              display: 'flex',
              gap: 6,
              overflowX: 'auto',
              paddingBottom: 4,
            }}
          >
            {photos.map((url, idx) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={url + idx}
                src={url}
                alt={`Миниатюра ${idx + 1}`}
                style={{
                  width: 48,
                  height: 48,
                  objectFit: 'cover',
                  borderRadius: 3,
                  cursor: 'pointer',
                  border: idx === selectedIndex ? '2px solid #0070f3' : '1px solid #ddd',
                }}
                loading="lazy"
                onClick={() => setSelectedIndex(idx)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface FiltersBarProps {
  filters: FiltersState
  categories: CategoryOption[]
  onChange: (next: Partial<FiltersState>, resetPage?: boolean) => void
  onExportCsv: () => void
}

function PriceDiscrepancyFilters({ filters, categories, onChange, onExportCsv }: FiltersBarProps) {
  const [searchInput, setSearchInput] = useState(filters.q)

  useEffect(() => {
    setSearchInput(filters.q)
  }, [filters.q])

  useEffect(() => {
    // Simple debounce for search (400ms)
    const handle = window.setTimeout(() => {
      if (searchInput !== filters.q) {
        onChange({ q: searchInput }, true)
      }
    }, 400)
    return () => window.clearTimeout(handle)
  }, [searchInput, filters.q, onChange])

  return (
    <div className="card" style={{ marginTop: 16, marginBottom: 16 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
          marginBottom: 8,
        }}
      >
        <h2 style={{ margin: 0 }}>Фильтры</h2>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'center',
          marginBottom: 8,
        }}
      >
        <div style={{ flex: 1, minWidth: 220 }}>
          <input
            type="text"
            placeholder="Поиск по артикулу / nmID / названию"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            style={{ width: '100%', padding: 8, fontSize: 14 }}
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={filters.onlyBelowRrp}
            onChange={(e) => onChange({ onlyBelowRrp: e.target.checked }, true)}
          />
          Только ниже РРЦ
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>Наличие WB:</span>
          <select
            value={filters.hasWbStock}
            onChange={(e) => onChange({ hasWbStock: e.target.value as HasStockFilter }, true)}
          >
            <option value="any">Любое</option>
            <option value="true">Только есть</option>
            <option value="false">Только нет</option>
          </select>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>Наличие склад:</span>
          <select
            value={filters.hasEnterpriseStock}
            onChange={(e) =>
              onChange({ hasEnterpriseStock: e.target.value as HasStockFilter }, true)
            }
          >
            <option value="any">Любое</option>
            <option value="true">Только есть</option>
            <option value="false">Только нет</option>
          </select>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>Сортировка:</span>
          <select
            value={filters.sort}
            onChange={(e) => onChange({ sort: e.target.value }, true)}
          >
            <option value="diff_rub_desc">Δ ₽ (убывание)</option>
            <option value="diff_rub_asc">Δ ₽ (возрастание)</option>
            <option value="diff_percent_desc">Δ % (убывание)</option>
            <option value="diff_percent_asc">Δ % (возрастание)</option>
            <option value="rrp_price_desc">РРЦ (убывание)</option>
            <option value="rrp_price_asc">РРЦ (возрастание)</option>
            <option value="showcase_price_desc">Витрина (убывание)</option>
            <option value="showcase_price_asc">Витрина (возрастание)</option>
            <option value="nm_id_desc">nmID (убывание)</option>
            <option value="nm_id_asc">nmID (возрастание)</option>
          </select>
        </label>
        {categories.length > 0 && (
          <CategoryMultiSelectPopover
            categories={categories}
            selectedIds={filters.categoryIds}
            onChange={(ids) => onChange({ categoryIds: ids }, true)}
          />
        )}
      </div>
    </div>
  )
}

interface TableProps {
  items: PriceDiscrepancyItem[]
}

function PriceDiscrepancyTable({ items }: TableProps) {
  if (!items.length) {
    return (
      <div className="card">
        <p>Нет данных по расхождениям цен с текущими фильтрами.</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Фото</th>
              <th>Артикул / nmID</th>
              <th>Название</th>
              <th>Цена WB</th>
              <th>РРЦ</th>
              <th>Витрина</th>
              <th>Скидка WB</th>
              <th>СПП</th>
              <th>Δ (РРЦ - Витрина)</th>
              <th>Реком. цена</th>
              <th>Наличие</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const hasShowcase = item.prices.showcase_price !== null
              const isBelow = item.computed.is_below_rrp && hasShowcase
              const diffRub = item.computed.diff_rub
              const diffPercent = item.computed.diff_percent
              const absDiffRub = diffRub !== null ? Math.abs(diffRub) : null
              const absDiffPercent = diffPercent !== null ? Math.abs(diffPercent) : null
              const recommended = item.computed.recommended_wb_admin_price
              const deltaRecommended = item.computed.delta_recommended
              const expectedShowcase = item.computed.expected_showcase_price

              const deltaLabelRub =
                absDiffRub !== null ? `${diffRub && diffRub > 0 ? '-' : '+'}${absDiffRub.toFixed(0)} ₽` : '—'
              const deltaLabelPercent =
                absDiffPercent !== null
                  ? `${diffPercent && diffPercent > 0 ? '-' : '+'}${absDiffPercent.toFixed(1)}%`
                  : '—'

              return (
                <tr
                  key={`${item.nm_id}-${item.article}`}
                  style={{
                    opacity: hasShowcase ? 1 : 0.6,
                    backgroundColor: !hasShowcase ? '#f6f6f6' : undefined,
                  }}
                >
                  <td>
                    <PhotoPopover photos={item.photos} size={36} />
                  </td>
                  <td>
                    <div style={{ fontSize: 13 }}>
                      <div style={{ fontWeight: 500 }}>{item.article || '—'}</div>
                      <div style={{ fontSize: 11, color: '#666' }}>
                        {item.nm_id ? (
                          <a
                            href={`https://www.wildberries.ru/catalog/${item.nm_id}/detail.aspx`}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            style={{ color: '#2563eb', textDecoration: 'none' }}
                          >
                            {item.nm_id}
                            <span style={{ marginLeft: 4, fontSize: 10 }}>↗</span>
                          </a>
                        ) : (
                          '—'
                        )}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ maxWidth: 260 }}>
                      <div style={{ fontSize: 13 }}>{item.title || '—'}</div>
                      {item.category?.name && (
                        <div style={{ fontSize: 11, color: '#777', marginTop: 2 }}>
                          {item.category.name}
                        </div>
                      )}
                      {!hasShowcase && (
                        <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>Нет данных витрины</div>
                      )}
                    </div>
                  </td>
                  <td>{formatCurrency(item.prices.wb_admin_price)}</td>
                  <td>{formatCurrency(item.prices.rrp_price)}</td>
                  <td>{formatCurrency(item.prices.showcase_price)}</td>
                  <td>{item.discounts.wb_discount_percent ?? '—'}%</td>
                  <td>{item.discounts.spp_percent ?? '—'}%</td>
                  <td>
                    {hasShowcase && diffRub !== null ? (
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '2px 6px',
                          borderRadius: 999,
                          fontSize: 11,
                          fontWeight: 500,
                          backgroundColor: isBelow ? '#ffe6e6' : '#e8e8e8',
                          color: isBelow ? '#b00020' : '#555',
                        }}
                      >
                        <span>{deltaLabelRub}</span>
                        <span>({deltaLabelPercent})</span>
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    {recommended !== null ? (
                      <div style={{ fontSize: 12 }}>
                        <div style={{ fontWeight: 500 }}>{formatCurrency(recommended)}</div>
                        {deltaRecommended !== null && deltaRecommended !== 0 && (
                          <div style={{ fontSize: 11, color: '#4b5563', marginTop: 2 }}>
                            {deltaRecommended > 0
                              ? `+${deltaRecommended.toFixed(0)} ₽`
                              : `${deltaRecommended.toFixed(0)} ₽`}
                          </div>
                        )}
                        {expectedShowcase !== null && (
                          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                            Витрина ≈ {formatCurrency(expectedShowcase)}
                          </div>
                        )}
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <span style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                      WB: {formatInt(item.stocks.wb_stock_qty)} | Склад:{' '}
                      {formatInt(item.stocks.enterprise_stock_qty)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface PaginationProps {
  meta: PriceDiscrepancyResponse['meta']
  onPageChange: (page: number) => void
}

function Pagination({ meta, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(meta.total_count / meta.page_size))

  if (totalPages <= 1) {
    return null
  }

  return (
    <div className="pagination">
      <button
        type="button"
        onClick={() => onPageChange(Math.max(1, meta.page - 1))}
        disabled={meta.page <= 1}
      >
        Предыдущая
      </button>
      <span>
        Страница {meta.page} из {totalPages} (Всего: {meta.total_count})
      </span>
      <button
        type="button"
        onClick={() => onPageChange(Math.min(totalPages, meta.page + 1))}
        disabled={meta.page >= totalPages}
      >
        Следующая
      </button>
    </div>
  )
}

export default function WbPriceDiscrepanciesPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = params.projectId as string
  usePageTitle('Расхождения цен', projectId)

  const [data, setData] = useState<PriceDiscrepancyItem[]>([])
  const [meta, setMeta] = useState<PriceDiscrepancyResponse['meta'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [categories, setCategories] = useState<CategoryOption[]>([])
  const [diagnosing, setDiagnosing] = useState(false)
  const [diagnosticMessage, setDiagnosticMessage] = useState<string | null>(null)
  const [diagnosticInfo, setDiagnosticInfo] = useState<DiagnosticInfo | null>(null)
  const [buildingRrp, setBuildingRrp] = useState(false)
  const [rrpBuildMessage, setRrpBuildMessage] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [isReportsHost, setIsReportsHost] = useState(false)

  useEffect(() => {
    if (typeof window !== 'undefined' && window.location.hostname === 'reports.zakka.ru') {
      setIsReportsHost(true)
    }
  }, [])

  const filters = useMemo(
    () => parseFiltersFromSearchParams(searchParams),
    [searchParams],
  )

  const updateQuery = (patch: Partial<FiltersState>, resetPage: boolean = false) => {
    const current = new URLSearchParams(searchParams.toString())

    const next: FiltersState = {
      ...filters,
      ...patch,
      page: resetPage ? 1 : filters.page,
    }

    if (next.q) current.set('q', next.q)
    else current.delete('q')

    const catParam = buildCategoryIdsParam(next.categoryIds)
    if (catParam) current.set('category_ids', catParam)
    else current.delete('category_ids')

    current.set('has_wb_stock', next.hasWbStock)
    current.set('has_enterprise_stock', next.hasEnterpriseStock)
    current.set('only_below_rrp', String(next.onlyBelowRrp))
    current.set('sort', next.sort)
    current.set('page', String(next.page))
    current.set('page_size', String(next.pageSize))

    const qs = current.toString()
    const basePath = `/app/project/${projectId}/wildberries/price-discrepancies`
    router.push(qs ? `${basePath}?${qs}` : basePath)
  }

  useEffect(() => {
    let cancelled = false

    async function loadData() {
      setLoading(true)
      setError(null)
      try {
        const qs = new URLSearchParams()
        if (filters.q) qs.set('q', filters.q)
        const catsParam = buildCategoryIdsParam(filters.categoryIds)
        if (catsParam) qs.set('category_ids', catsParam)
        if (filters.hasWbStock !== 'any') qs.set('has_wb_stock', filters.hasWbStock)
        if (filters.hasEnterpriseStock !== 'any') {
          qs.set('has_enterprise_stock', filters.hasEnterpriseStock)
        }
        if (!filters.onlyBelowRrp) qs.set('only_below_rrp', 'false')
        else qs.set('only_below_rrp', 'true')
        qs.set('sort', filters.sort)
        qs.set('page', String(filters.page))
        qs.set('page_size', String(filters.pageSize))

        const url = `/api/v1/projects/${projectId}/wildberries/price-discrepancies?${qs.toString()}`
        const resp = await apiGetData<PriceDiscrepancyResponse>(url)
        if (cancelled) return
        setData(resp.items || [])
        setMeta(resp.meta)
        setDiagnosticInfo(resp.diagnostic || null)
        setError(null)
      } catch (e: any) {
        if (cancelled) return
        console.error('Failed to load price discrepancies', e)
        setError(e?.detail || e?.message || 'Не удалось загрузить данные')
        setData([])
        setMeta({
          total_count: 0,
          page: filters.page,
          page_size: filters.pageSize,
          updated_at: new Date().toISOString(),
        })
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadData()
    return () => {
      cancelled = true
    }
  }, [projectId, filters, reloadToken])

  useEffect(() => {
    let cancelled = false

    async function loadCategories() {
      try {
        const resp = await apiGetData<{ items: CategoryOption[] }>(
          `/api/v1/projects/${projectId}/wildberries/categories`,
        )
        if (cancelled) return
        setCategories(resp.items || [])
      } catch (e) {
        if (cancelled) return
        // Categories are optional; just log
        console.warn('Failed to load WB categories', e)
        setCategories([])
      }
    }

    loadCategories()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const handleExportCsv = () => {
    const current = new URLSearchParams(searchParams.toString())
    const base = `/api/v1/projects/${projectId}/wildberries/price-discrepancies/export.csv`
    const url = current.toString() ? `${base}?${current.toString()}` : base
    if (typeof window !== 'undefined') {
      window.location.href = url
    }
  }

  const handleDiagnose = async () => {
    setDiagnosing(true)
    setDiagnosticMessage(null)
    setError(null)
    try {
      const { data: resp } = await apiPost<{ task_id: string; status: string; message: string }>(
        `/api/v1/projects/${projectId}/wildberries/price-discrepancies/diagnose`
      )
      setDiagnosticMessage(
        `Диагностика запущена (task_id: ${resp.task_id}). Проверьте логи worker для деталей.`
      )
      // Clear message after 5 seconds
      setTimeout(() => setDiagnosticMessage(null), 5000)
    } catch (e: any) {
      console.error('Failed to trigger diagnostics', e)
      setError(e?.detail || e?.message || 'Не удалось запустить диагностику')
    } finally {
      setDiagnosing(false)
    }
  }

  const handleBuildRrpSnapshots = async () => {
    setBuildingRrp(true)
    setRrpBuildMessage(null)
    setError(null)
    try {
      const { data: resp } = await apiPost<{ task_id: string; run_id: number | null; domain: string; status: string }>(
        `/api/v1/projects/${projectId}/ingest/run`,
        { domain: 'build_rrp_snapshots' },
      )
      setRrpBuildMessage(
        `Построение RRP snapshots запущено (run_id: ${resp.run_id ?? '—'}, task_id: ${resp.task_id}). ` +
          `Обновление данных может занять 10–60 секунд.`,
      )
      // Trigger a couple of reload attempts (best-effort, without polling UI complexity)
      window.setTimeout(() => setReloadToken((x) => x + 1), 2500)
      window.setTimeout(() => setReloadToken((x) => x + 1), 8000)
      window.setTimeout(() => setReloadToken((x) => x + 1), 20000)
      window.setTimeout(() => setRrpBuildMessage(null), 15000)
    } catch (e: any) {
      console.error('Failed to trigger build_rrp_snapshots', e)
      setError(e?.detail || e?.message || 'Не удалось запустить построение RRP snapshots')
    } finally {
      setBuildingRrp(false)
    }
  }

  return (
    <div className="container">
      {isReportsHost && (
        <div style={{ marginBottom: 12 }}>
          <PortalBackButton fallbackHref="/client" />
        </div>
      )}
      <h1>Расхождения цен (РРЦ vs витрина WB)</h1>
      {!isReportsHost && (
        <Link href={`/app/project/${projectId}/dashboard`}>
          <button type="button">← Назад к дашборду</button>
        </Link>
      )}

      {meta && (
        <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <strong>Всего позиций:</strong> {meta.total_count}
          </div>
          <div style={{ fontSize: 12, color: '#666' }}>
            <strong>Данные обновлены:</strong> {formatDate(meta.updated_at)}
          </div>
        </div>
        {meta.total_count === 0 && diagnosticInfo && (
          <div
            style={{
              marginTop: 12,
              padding: 16,
              background: '#fef3c7',
              border: '1px solid #f59e0b',
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            <div style={{ marginBottom: 12 }}>
              <strong>⚠️ Отчёт пуст. Диагностика данных:</strong>
            </div>
            
            <div style={{ marginBottom: 12 }}>
              <strong>Доступность данных:</strong>
              <ul style={{ marginTop: 4, marginBottom: 0, paddingLeft: 20 }}>
                <li>Products: {diagnosticInfo.data_availability.products_count}</li>
                <li>Price snapshots: {diagnosticInfo.data_availability.price_snapshots_count}</li>
                <li>Frontend prices: {diagnosticInfo.data_availability.frontend_catalog_price_snapshots_count}</li>
                <li>Stock snapshots: {diagnosticInfo.data_availability.stock_snapshots_count}</li>
                <li>
                  <strong style={{ color: diagnosticInfo.data_availability.rrp_snapshots_count === 0 ? '#dc2626' : '#059669' }}>
                    RRP snapshots: {diagnosticInfo.data_availability.rrp_snapshots_count}
                  </strong>
                </li>
                {diagnosticInfo.data_availability.rrp_snapshots_latest_snapshot_at && (
                  <li>
                    Последний RRP snapshot:{' '}
                    {formatDate(diagnosticInfo.data_availability.rrp_snapshots_latest_snapshot_at)}
                  </li>
                )}
                <li>Products with both RRP and showcase: {diagnosticInfo.data_availability.products_with_both_rrp_and_showcase}</li>
              </ul>
            </div>

            {diagnosticInfo.data_availability.internal_data_latest_snapshot && (
              <div style={{ marginBottom: 12 }}>
                <strong>Internal Data (источник РРЦ):</strong>
                <ul style={{ marginTop: 4, marginBottom: 0, paddingLeft: 20 }}>
                  <li>
                    Последний snapshot: #{diagnosticInfo.data_availability.internal_data_latest_snapshot.id}{' '}
                    ({diagnosticInfo.data_availability.internal_data_latest_snapshot.status || '—'}) —{' '}
                    {formatDate(diagnosticInfo.data_availability.internal_data_latest_snapshot.imported_at || undefined)}
                  </li>
                  {typeof diagnosticInfo.data_availability.internal_data_rrp_rows_found === 'number' && (
                    <li>RRP строк (найдено): {diagnosticInfo.data_availability.internal_data_rrp_rows_found}</li>
                  )}
                  {typeof diagnosticInfo.data_availability.internal_data_rrp_rows_matched_products === 'number' && (
                    <li>
                      Матчится с products.vendor_code_norm:{' '}
                      {diagnosticInfo.data_availability.internal_data_rrp_rows_matched_products}
                    </li>
                  )}
                  {typeof diagnosticInfo.data_availability.internal_data_rrp_rows_inserted === 'number' && (
                    <li>
                      Уже вставлено в rrp_snapshots (для этого snapshot):{' '}
                      {diagnosticInfo.data_availability.internal_data_rrp_rows_inserted}
                    </li>
                  )}
                </ul>
              </div>
            )}

            {diagnosticInfo.data_availability.internal_data_rrp_errors_preview &&
              diagnosticInfo.data_availability.internal_data_rrp_errors_preview.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <strong>Ошибки парсинга/валидации RRP (превью):</strong>
                  <ul style={{ marginTop: 4, marginBottom: 0, paddingLeft: 20 }}>
                    {diagnosticInfo.data_availability.internal_data_rrp_errors_preview.slice(0, 5).map((e, idx) => (
                      <li key={idx}>
                        {e.message || '—'}
                        {e.row_index !== null && e.row_index !== undefined ? ` (row ${e.row_index})` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            
            {diagnosticInfo.issues.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <strong style={{ color: '#dc2626' }}>Проблемы:</strong>
                <ul style={{ marginTop: 4, marginBottom: 0, paddingLeft: 20 }}>
                  {diagnosticInfo.issues.map((issue, idx) => (
                    <li key={idx}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
            
            {diagnosticInfo.recommendations.length > 0 && (
              <div>
                <strong style={{ color: '#059669' }}>Рекомендации:</strong>
                <ul style={{ marginTop: 4, marginBottom: 0, paddingLeft: 20 }}>
                  {diagnosticInfo.recommendations.map((rec, idx) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        
        {meta.total_count === 0 && !diagnosticInfo && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: '#fef3c7',
              border: '1px solid #f59e0b',
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            <strong>Внимание:</strong> Отчёт пуст. Нажмите "Собрать отчёт" для диагностики данных или проверьте логи worker.
          </div>
        )}
        </div>
      )}

      <div className="card" style={{ marginTop: 16, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0 }}>Действия</h2>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              type="button"
              onClick={handleDiagnose}
              disabled={diagnosing}
              style={{ minWidth: 140 }}
            >
              {diagnosing ? 'Запуск...' : 'Собрать отчёт'}
            </button>
            {diagnosticInfo?.data_availability?.rrp_snapshots_count === 0 && (
              <button
                type="button"
                onClick={handleBuildRrpSnapshots}
                disabled={buildingRrp}
                style={{ minWidth: 190 }}
              >
                {buildingRrp ? 'Запуск...' : 'Построить RRP snapshots'}
              </button>
            )}
            <button type="button" onClick={handleExportCsv}>
              Экспорт CSV
            </button>
          </div>
        </div>
        {diagnosticMessage && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: '#d1fae5',
              border: '1px solid #10b981',
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            {diagnosticMessage}
          </div>
        )}
        {rrpBuildMessage && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: '#dbeafe',
              border: '1px solid #60a5fa',
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            {rrpBuildMessage}
          </div>
        )}
      </div>

      <PriceDiscrepancyFilters
        filters={filters}
        categories={categories}
        onChange={updateQuery}
        onExportCsv={handleExportCsv}
      />

      {loading && <p>Загрузка данных…</p>}
      {error && (
        <div className="card" style={{ background: '#f8d7da', border: '1px solid #f5c2c7' }}>
          <p style={{ margin: 0 }}>
            <strong>Ошибка:</strong> {error}
          </p>
        </div>
      )}
      {!loading && !error && <PriceDiscrepancyTable items={data} />}

      {meta && (
        <Pagination
          meta={meta}
          onPageChange={(page) => updateQuery({ page }, false)}
        />
      )}
    </div>
  )
}

