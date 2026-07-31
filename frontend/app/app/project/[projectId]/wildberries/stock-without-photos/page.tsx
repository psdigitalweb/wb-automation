'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { apiGetData } from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import styles from './stock-without-photos.module.css'

interface StockWithoutPhotosItem {
  nm_id: number
  our_sku: string | null
  rrc: number | null
  wb_stock_total: number
  wb_stock_by_warehouse: Array<{
    warehouse_name: string
    qty: number
  }>
}

interface StockWithoutPhotosResponse {
  items: StockWithoutPhotosItem[]
  meta: {
    total_in_stocks: number
    total_candidates_after_filters: number
    total_without_photos: number
  }
}

interface FiltersState {
  search: string
  minStock: number
  warehouseId: string
}

function parseFiltersFromSearchParams(searchParams: URLSearchParams): FiltersState {
  const search = searchParams.get('search') || ''
  const minStock = Number(searchParams.get('min_stock') || '1')
  const warehouseId = searchParams.get('warehouse_id') || ''

  return {
    search,
    minStock: Number.isNaN(minStock) || minStock < 0 ? 1 : minStock,
    warehouseId,
  }
}

function formatCurrency(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '0'
  return new Intl.NumberFormat('ru-RU').format(value)
}

interface WarehouseDetailsProps {
  warehouses: StockWithoutPhotosItem['wb_stock_by_warehouse']
}

function WarehouseDetails({ warehouses }: WarehouseDetailsProps) {
  const [expanded, setExpanded] = useState(false)

  if (!warehouses || warehouses.length === 0) {
    return <span className={styles.muted}>-</span>
  }

  if (warehouses.length === 1) {
    return (
      <span className={styles.warehouseSingle}>
        <span>{warehouses[0].warehouse_name}</span>
        <strong>{formatInt(warehouses[0].qty)}</strong>
      </span>
    )
  }

  return (
    <div className={styles.warehouseDetails}>
      <button type="button" onClick={() => setExpanded(!expanded)} className={styles.inlineButton}>
        {expanded ? 'Скрыть склады' : `Показать ${warehouses.length} складов`}
      </button>
      {expanded && (
        <div className={styles.warehouseList}>
          {warehouses.map((wh, idx) => (
            <div key={`${wh.warehouse_name}-${idx}`} className={styles.warehouseRow}>
              <span>{wh.warehouse_name}</span>
              <strong>{formatInt(wh.qty)}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface FiltersBarProps {
  filters: FiltersState
  onChange: (next: Partial<FiltersState>) => void
}

function StockWithoutPhotosFilters({ filters, onChange }: FiltersBarProps) {
  const [searchInput, setSearchInput] = useState(filters.search)

  useEffect(() => {
    setSearchInput(filters.search)
  }, [filters.search])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (searchInput !== filters.search) {
        onChange({ search: searchInput })
      }
    }, 400)
    return () => window.clearTimeout(handle)
  }, [searchInput, filters.search, onChange])

  return (
    <div className={styles.filterToolbar}>
      <div className={styles.searchControl}>
        <span aria-hidden="true">⌕</span>
        <div className={styles.searchInputWrap}>
          <input
            type="text"
            placeholder="Поиск по артикулу / nmID"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
      </div>
    </div>
  )
}

interface TableProps {
  items: StockWithoutPhotosItem[]
}

function StockWithoutPhotosTable({ items }: TableProps) {
  if (!items.length) {
    return (
      <div className={styles.emptyCard}>
        <p>Нет товаров с остатком на WB и без фото.</p>
      </div>
    )
  }

  return (
    <div className={styles.tableCard}>
      <div className={styles.tableWrap}>
        <table className={styles.stockTable}>
          <thead>
            <tr>
              <th>nmID</th>
              <th>Артикул</th>
              <th>РРЦ</th>
              <th>Остаток WB</th>
              <th>Остаток по складам</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.nm_id}>
                <td>
                  {item.nm_id ? (
                    <a
                      href={`https://www.wildberries.ru/catalog/${item.nm_id}/detail.aspx`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.nmLink}
                    >
                      {item.nm_id}
                    </a>
                  ) : (
                    '-'
                  )}
                </td>
                <td className={styles.skuCell}>{item.our_sku || '-'}</td>
                <td className={styles.numericCell}>{formatCurrency(item.rrc)}</td>
                <td className={styles.numericCell}>
                  <strong className={styles.stockValue}>{formatInt(item.wb_stock_total)}</strong>
                </td>
                <td>
                  <WarehouseDetails warehouses={item.wb_stock_by_warehouse} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function StockWithoutPhotosPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectId = params.projectId as string
  usePageTitle('Товары без фото', projectId)

  const [data, setData] = useState<StockWithoutPhotosItem[]>([])
  const [meta, setMeta] = useState<StockWithoutPhotosResponse['meta'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const filters = useMemo(() => parseFiltersFromSearchParams(searchParams), [searchParams])

  const updateQuery = useCallback((patch: Partial<FiltersState>) => {
    const current = new URLSearchParams(searchParams.toString())
    const next: FiltersState = { ...filters, ...patch }

    if (next.search) current.set('search', next.search)
    else current.delete('search')

    if (next.minStock !== 1) current.set('min_stock', String(next.minStock))
    else current.delete('min_stock')

    if (next.warehouseId) current.set('warehouse_id', next.warehouseId)
    else current.delete('warehouse_id')

    const qs = current.toString()
    const basePath = `/app/project/${projectId}/wildberries/stock-without-photos`
    router.push(qs ? `${basePath}?${qs}` : basePath)
  }, [filters, projectId, router, searchParams])

  useEffect(() => {
    let cancelled = false

    async function loadData() {
      setLoading(true)
      setError(null)
      try {
        const qs = new URLSearchParams()
        if (filters.search) qs.set('search', filters.search)
        if (filters.minStock !== 1) qs.set('min_stock', String(filters.minStock))
        if (filters.warehouseId) qs.set('warehouse_id', filters.warehouseId)

        const url = `/api/v1/projects/${projectId}/wildberries/stock-without-photos${qs.toString() ? `?${qs.toString()}` : ''}`
        const resp = await apiGetData<StockWithoutPhotosResponse>(url)
        if (cancelled) return
        setData(resp.items || [])
        setMeta(resp.meta)
      } catch (e: unknown) {
        if (cancelled) return
        console.error('Failed to load stock without photos', e)
        setError(e instanceof Error ? e.message : 'Не удалось загрузить данные')
        setData([])
        setMeta({
          total_in_stocks: 0,
          total_candidates_after_filters: 0,
          total_without_photos: 0,
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
  }, [projectId, filters])

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div className={styles.titleBlock}>
          <div className={styles.titleRow}>
            <h1>Остаток WB без фото</h1>
            <span className={styles.marketplaceBadge}>
              <span aria-hidden="true" />
              WB
            </span>
          </div>
          <p>Товары с наличием на Wildberries, для которых не найдены фотографии.</p>
        </div>
      </header>

      {meta && (
        <section className={styles.metricGrid} aria-label="Сводка">
          <div className={styles.metricCard}>
            <span>Всего с остатком</span>
            <strong>{formatInt(meta.total_in_stocks)}</strong>
          </div>
          <div className={styles.metricCard}>
            <span>Без фото</span>
            <strong>{formatInt(meta.total_without_photos)}</strong>
          </div>
        </section>
      )}

      {!meta && loading && (
        <section className={styles.metricGrid} aria-label="Загрузка сводки">
          {['Всего с остатком', 'Без фото'].map((label) => (
            <div key={label} className={styles.metricCard}>
              <span>{label}</span>
              <strong>-</strong>
            </div>
          ))}
        </section>
      )}

      <StockWithoutPhotosFilters filters={filters} onChange={updateQuery} />

      {loading && <p className={styles.loadingText}>Загрузка данных...</p>}
      {error && (
        <div className={styles.errorCard}>
          <p>
            <strong>Ошибка:</strong> {error}
          </p>
        </div>
      )}
      {!loading && !error && <StockWithoutPhotosTable items={data} />}
    </div>
  )
}
