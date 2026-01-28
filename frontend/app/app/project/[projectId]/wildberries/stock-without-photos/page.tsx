'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { apiGetData } from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'

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
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '0'
  return value.toString()
}

interface WarehouseDetailsProps {
  warehouses: StockWithoutPhotosItem['wb_stock_by_warehouse']
}

function WarehouseDetails({ warehouses }: WarehouseDetailsProps) {
  const [expanded, setExpanded] = useState(false)

  if (!warehouses || warehouses.length === 0) {
    return <span style={{ color: '#999' }}>—</span>
  }

  if (warehouses.length === 1) {
    return (
      <span style={{ fontSize: 13 }}>
        {warehouses[0].warehouse_name}: {formatInt(warehouses[0].qty)}
      </span>
    )
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        style={{
          background: 'none',
          border: 'none',
          color: '#2563eb',
          cursor: 'pointer',
          fontSize: 13,
          textDecoration: 'underline',
          padding: 0,
        }}
      >
        {expanded ? 'Скрыть' : `Показать (${warehouses.length} складов)`}
      </button>
      {expanded && (
        <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: '2px solid #e5e7eb' }}>
          {warehouses.map((wh, idx) => (
            <div key={idx} style={{ fontSize: 12, marginBottom: 4 }}>
              {wh.warehouse_name}: {formatInt(wh.qty)}
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
    <div className="card" style={{ marginTop: 16, marginBottom: 16 }}>
      <h2 style={{ margin: 0, marginBottom: 12 }}>Фильтры</h2>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'center',
        }}
      >
        <div style={{ flex: 1, minWidth: 220 }}>
          <input
            type="text"
            placeholder="Поиск по артикулу / nmID"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            style={{ width: '100%', padding: 8, fontSize: 14 }}
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>Мин. остаток:</span>
          <input
            type="number"
            min="0"
            value={filters.minStock}
            onChange={(e) => onChange({ minStock: Number(e.target.value) || 1 })}
            style={{ width: 80, padding: 8, fontSize: 14 }}
          />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>Склад ID:</span>
          <input
            type="number"
            placeholder="Все"
            value={filters.warehouseId}
            onChange={(e) => onChange({ warehouseId: e.target.value })}
            style={{ width: 120, padding: 8, fontSize: 14 }}
          />
        </label>
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
      <div className="card">
        <p>Нет товаров с остатком на WB и без фото.</p>
      </div>
    )
  }

  return (
    <div className="card">
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>nmID</th>
              <th>Артикул</th>
              <th>РРЦ</th>
              <th>Остаток WB (всего)</th>
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
                      style={{ color: '#2563eb', textDecoration: 'none' }}
                    >
                      {item.nm_id}
                      <span style={{ marginLeft: 4, fontSize: 10 }}>↗</span>
                    </a>
                  ) : (
                    '—'
                  )}
                </td>
                <td>{item.our_sku || '—'}</td>
                <td>{formatCurrency(item.rrc)}</td>
                <td>
                  <strong>{formatInt(item.wb_stock_total)}</strong>
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

  const updateQuery = (patch: Partial<FiltersState>) => {
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
  }

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
      } catch (e: any) {
        if (cancelled) return
        console.error('Failed to load stock without photos', e)
        setError(e?.detail || e?.message || 'Не удалось загрузить данные')
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
    <div className="container">
      <h1>Остаток WB без фото</h1>
      <Link href={`/app/project/${projectId}/dashboard`}>
        <button type="button">← Назад к дашборду</button>
      </Link>

      {meta && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <div>
              <strong>Всего товаров с остатком:</strong> {meta.total_in_stocks}
            </div>
            <div>
              <strong>После фильтров:</strong> {meta.total_candidates_after_filters}
            </div>
            <div>
              <strong>Без фото:</strong> {meta.total_without_photos}
            </div>
          </div>
        </div>
      )}

      <StockWithoutPhotosFilters filters={filters} onChange={updateQuery} />

      {loading && <p>Загрузка данных…</p>}
      {error && (
        <div className="card" style={{ background: '#f8d7da', border: '1px solid #f5c2c7' }}>
          <p style={{ margin: 0 }}>
            <strong>Ошибка:</strong> {error}
          </p>
        </div>
      )}
      {!loading && !error && <StockWithoutPhotosTable items={data} />}
    </div>
  )
}
