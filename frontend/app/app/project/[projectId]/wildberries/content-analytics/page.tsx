'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  getContentAnalyticsSummary,
  type WBProductLookupItem,
  type ContentAnalyticsSummaryItem,
  type ContentAnalyticsSummaryResponse,
} from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import PortalBackButton from '@/components/PortalBackButton'
import WBProductLookupInput from '@/components/WBProductLookupInput'

function formatRUB(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(2)}%`
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '0'
  return new Intl.NumberFormat('ru-RU', { useGrouping: true }).format(value)
}

function defaultPeriod(): { period_from: string; period_to: string } {
  const to = new Date()
  const from = new Date(to)
  from.setDate(from.getDate() - 30)
  return {
    period_from: from.toISOString().slice(0, 10),
    period_to: to.toISOString().slice(0, 10),
  }
}

export default function ContentAnalyticsPage() {
  const params = useParams()
  const projectId = typeof params?.projectId === 'string' ? params.projectId : ''
  const [periodFrom, setPeriodFrom] = useState('')
  const [periodTo, setPeriodTo] = useState('')
  const [productSearch, setProductSearch] = useState('')
  const [selectedProduct, setSelectedProduct] = useState<WBProductLookupItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ContentAnalyticsSummaryResponse | null>(null)

  usePageTitle('Аналитика карточек', projectId || null)

  const load = useCallback(() => {
    if (!projectId) return
    const pf = periodFrom || defaultPeriod().period_from
    const pt = periodTo || defaultPeriod().period_to
    if (!pf || !pt) {
      setError('Укажите период')
      return
    }
    setError(null)
    setLoading(true)
    const rawValue = productSearch.trim()
    const nmId = selectedProduct?.nm_id ?? (rawValue ? parseInt(rawValue, 10) : undefined)
    if (rawValue && selectedProduct == null && (Number.isNaN(nmId) || nmId == null)) {
      setError('Выберите товар из подсказки или введите числовой nm_id')
      setLoading(false)
      return
    }
    getContentAnalyticsSummary(projectId, {
      period_from: pf,
      period_to: pt,
      nm_id: nmId,
    })
      .then((res) => {
        setData(res)
      })
      .catch((err: any) => {
        setError(err?.detail || err?.message || 'Ошибка загрузки')
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [projectId, periodFrom, periodTo, productSearch, selectedProduct])

  useEffect(() => {
    const def = defaultPeriod()
    setPeriodFrom(def.period_from)
    setPeriodTo(def.period_to)
  }, [])

  const items = data?.items ?? []

  return (
    <div className="container">
      <div style={{ marginBottom: 12 }}>
        <PortalBackButton fallbackHref={`/app/project/${projectId}/dashboard`} />
      </div>
      <h1 style={{ marginTop: 0, marginBottom: 20 }}>Аналитика карточек</h1>

      <div className="card mb-5">
        <div className="p-4">
          <h3 className="m-0 mb-3 text-base font-semibold">Фильтры</h3>
          <div
            className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1fr_200px_160px] items-end"
            style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}
          >
            <div className="flex flex-col min-w-0">
              <label className="block text-sm font-medium mb-1">Дата с</label>
              <input
                type="date"
                value={periodFrom}
                onChange={(e) => setPeriodFrom(e.target.value)}
                className="h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex flex-col min-w-0">
              <label className="block text-sm font-medium mb-1">Дата по</label>
              <input
                type="date"
                value={periodTo}
                onChange={(e) => setPeriodTo(e.target.value)}
                className="h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex flex-col min-w-0">
              <label className="block text-sm font-medium mb-1">Товар</label>
              <WBProductLookupInput
                projectId={projectId}
                value={productSearch}
                onChange={(next) => {
                  setProductSearch(next)
                  setSelectedProduct(null)
                }}
                onSelect={(item) => {
                  setSelectedProduct(item)
                  setProductSearch(item.vendor_code ? `${item.vendor_code} · ${item.nm_id}` : String(item.nm_id))
                }}
                placeholder="nm_id или артикул"
              />
            </div>
            <div className="flex items-end">
              <button
                type="button"
                onClick={load}
                disabled={loading}
                className="h-10 px-6 w-full md:w-auto rounded border border-gray-300 bg-white text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {loading ? 'Загрузка…' : 'Обновить'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: 15,
            marginBottom: 20,
            backgroundColor: '#f8d7da',
            color: '#721c24',
            borderRadius: 4,
          }}
        >
          {error}
        </div>
      )}

      {loading && !data && <p style={{ color: '#6b7280' }}>Loading...</p>}

      {!loading && data && (
        <div className="card overflow-x-auto">
          <table className="w-full border-collapse" style={{ fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                <th style={{ textAlign: 'left', padding: '10px 12px' }}>nmId</th>
                <th style={{ textAlign: 'right', padding: '10px 12px' }}>Opens / Открытия</th>
                <th style={{ textAlign: 'right', padding: '10px 12px' }}>Add to cart / В корзину</th>
                <th style={{ textAlign: 'right', padding: '10px 12px' }}>Cart rate</th>
                <th style={{ textAlign: 'right', padding: '10px 12px' }}>Orders</th>
                <th style={{ textAlign: 'right', padding: '10px 12px' }}>Conversion</th>
                <th style={{ textAlign: 'right', padding: '10px 12px' }}>Revenue</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: 24, textAlign: 'center', color: '#6b7280' }}>
                    Нет данных за выбранный период
                  </td>
                </tr>
              ) : (
                items.map((row: ContentAnalyticsSummaryItem) => (
                  <tr key={row.nm_id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <td style={{ padding: '10px 12px' }}>{formatInt(row.nm_id)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatInt(row.opens)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatInt(row.add_to_cart)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatPct(row.cart_rate)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatInt(row.orders)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatPct(row.conversion)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatRUB(row.revenue)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
