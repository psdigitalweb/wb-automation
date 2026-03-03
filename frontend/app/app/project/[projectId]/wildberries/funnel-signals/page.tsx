'use client'

import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import { useParams } from 'next/navigation'
import { getFunnelSignals, getFunnelSignalsCategories, type FunnelSignalsItem, type FunnelSignalsResponse } from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import PortalBackButton from '@/components/PortalBackButton'

/* ----- Photo popover: same as price-discrepancies (hover zoom, size 36) ----- */
function PhotoPopover({ photos, size = 36 }: { photos: string[]; size?: number }) {
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

  const handleClose = () => setOpen(false)

  const toggleOpen = () => {
    if (!hasPhotos) return
    setOpen((o) => !o)
    if (!open && anchorRef.current) {
      const rect = anchorRef.current.getBoundingClientRect()
      setPosition({
        top: rect.bottom + window.scrollY + 8,
        left: rect.left + window.scrollX,
      })
    }
  }

  return (
    <div
      style={{ position: 'relative', display: 'inline-block' }}
      ref={anchorRef}
      onMouseEnter={handleOpen}
      onMouseLeave={(e) => {
        const relatedTarget = e.relatedTarget as Node | null
        if (
          !popoverRef.current ||
          !relatedTarget ||
          (!popoverRef.current.contains(relatedTarget) && !anchorRef.current?.contains(relatedTarget))
        ) {
          handleClose()
        }
      }}
    >
      {thumbnailSrc ? (
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
            <img
              src={photos[selectedIndex]}
              alt="Фото товара крупно"
              style={{ maxWidth: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 4 }}
              loading="lazy"
            />
          </div>
          {photos.length > 1 && (
            <div style={{ display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 4 }}>
              {photos.map((url, idx) => (
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
          )}
        </div>
      )}
    </div>
  )
}

function formatRUB(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    useGrouping: true,
  }).format(value)
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', { useGrouping: true }).format(value)
}

function formatNmId(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return String(value)
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

const SIGNAL_CODES: { value: string; label: string }[] = [
  { value: '', label: 'Любой' },
  { value: 'insufficient_data', label: 'Недостаточно данных' },
  { value: 'low_traffic', label: 'Низкий трафик' },
  { value: 'low_add_to_cart', label: 'Низкий add-to-cart' },
  { value: 'loss_cart_to_order', label: 'Потеря cart→order' },
  { value: 'low_order_rate', label: 'Низкая конверсия в заказ' },
  { value: 'scale_up', label: 'Масштабировать' },
]

function SeverityBadge({ severity }: { severity: string | null }) {
  if (severity == null) return null
  const styles: Record<string, React.CSSProperties> = {
    high: { backgroundColor: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca' },
    med: { backgroundColor: '#fefce8', color: '#a16207', border: '1px solid #fef08a' },
    low: { backgroundColor: '#f3f4f6', color: '#374151', border: '1px solid #e5e7eb' },
  }
  const labels: Record<string, string> = { high: 'Высокий', med: 'Средний', low: 'Низкий' }
  return (
    <span
      style={{
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 500,
        ...styles[severity],
      }}
    >
      {labels[severity] ?? severity}
    </span>
  )
}

const PAGE_SIZE_OPTIONS = [50, 100, 200] as const

export default function FunnelSignalsPage() {
  const params = useParams()
  const projectId = typeof params?.projectId === 'string' ? params.projectId : ''
  const [periodFrom, setPeriodFrom] = useState('')
  const [periodTo, setPeriodTo] = useState('')
  const [minOpens, setMinOpens] = useState(200)
  const [signalFilter, setSignalFilter] = useState('')
  const [onlyCartGt0, setOnlyCartGt0] = useState(false)
  const [wbCategory, setWbCategory] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [sortBy, setSortBy] = useState<'potential_rub' | 'opens' | 'cart_rate' | 'order_rate' | 'revenue'>('potential_rub')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [meta, setMeta] = useState<Pick<FunnelSignalsResponse, 'page' | 'page_size' | 'total' | 'pages'> | null>(null)
  const [data, setData] = useState<FunnelSignalsItem[] | null>(null)
  const [drawerRow, setDrawerRow] = useState<FunnelSignalsItem | null>(null)

  usePageTitle('Воронка: Сигналы', projectId || null)

  useEffect(() => {
    if (!projectId) return
    getFunnelSignalsCategories(projectId)
      .then(setCategories)
      .catch(() => setCategories([]))
  }, [projectId])

  const load = useCallback(
    (pageNum: number = 1, pageSizeOverride?: number, sortOverride?: 'potential_rub' | 'opens' | 'cart_rate' | 'order_rate' | 'revenue', orderOverride?: 'asc' | 'desc') => {
      if (!projectId) return
      const pf = periodFrom || defaultPeriod().period_from
      const pt = periodTo || defaultPeriod().period_to
      if (!pf || !pt) {
        setError('Укажите период')
        return
      }
      const size = pageSizeOverride ?? pageSize
      const sortVal = sortOverride ?? sortBy
      const orderVal = orderOverride ?? sortOrder
      setError(null)
      setLoading(true)
      getFunnelSignals(projectId, {
        period_from: pf,
        period_to: pt,
        min_opens: minOpens,
        only_cart_gt0: onlyCartGt0,
        wb_category: wbCategory || undefined,
        signal_code: signalFilter || undefined,
        page: pageNum,
        page_size: size,
        sort: sortVal,
        order: orderVal,
      })
        .then((res) => {
          setData(res.items)
          setMeta({ page: res.page, page_size: res.page_size, total: res.total, pages: res.pages })
        })
        .catch((err: unknown) => {
          setError((err as { detail?: string; message?: string })?.detail || (err as Error)?.message || 'Ошибка загрузки')
          setData(null)
          setMeta(null)
        })
        .finally(() => setLoading(false))
    },
    [projectId, periodFrom, periodTo, minOpens, onlyCartGt0, wbCategory, signalFilter, pageSize, sortBy, sortOrder]
  )

  const handleApplyFilters = useCallback(() => {
    setPage(1)
    load(1)
  }, [load])

  useEffect(() => {
    const def = defaultPeriod()
    setPeriodFrom(def.period_from)
    setPeriodTo(def.period_to)
  }, [])

  const truncate = (s: string | null | undefined, maxLen: number) => {
    if (s == null) return '—'
    if (s.length <= maxLen) return s
    return s.slice(0, maxLen) + '…'
  }

  const totalPages = meta?.pages ?? 1
  const canGoPrev = (meta?.page ?? 1) > 1
  const canGoNext = (meta?.page ?? 1) < totalPages

  const handleSort = (field: 'opens' | 'cart_rate' | 'order_rate' | 'revenue') => {
    const nextOrder = sortBy === field ? (sortOrder === 'desc' ? 'asc' : 'desc') : 'desc'
    setSortBy(field)
    setSortOrder(nextOrder)
    setPage(1)
    load(1, undefined, field, nextOrder)
  }

  return (
    <div className="container">
      <div style={{ marginBottom: 12 }}>
        <PortalBackButton fallbackHref={`/app/project/${projectId}/dashboard`} />
      </div>
      <h1 style={{ marginTop: 0, marginBottom: 20 }}>Воронка: Сигналы</h1>

      {/* Form: row1 = даты, мин. открытий, сигнал, кнопка; row2 = Категория WB, чекбокс */}
      <div className="card mb-5">
        <div className="p-4">
          <h3 className="m-0 mb-3 text-base font-semibold">Фильтры</h3>
          <div className="unitpnl-grid unitpnl-grid--funnel-row1 grid grid-cols-1 gap-6 md:grid-cols-[140px_140px_100px_1fr_120px] items-end">
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Дата с</label>
              <input
                type="date"
                value={periodFrom}
                onChange={(e) => setPeriodFrom(e.target.value)}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Дата по</label>
              <input
                type="date"
                value={periodTo}
                onChange={(e) => setPeriodTo(e.target.value)}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Мин. открытий</label>
              <input
                type="number"
                min={1}
                value={minOpens}
                onChange={(e) => setMinOpens(parseInt(e.target.value, 10) || 200)}
                placeholder="200"
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Сигнал</label>
              <select
                value={signalFilter}
                onChange={(e) => setSignalFilter(e.target.value)}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {SIGNAL_CODES.map((opt) => (
                  <option key={opt.value || 'any'} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="unitpnl-col unitpnl-actions flex items-end md:justify-end">
              <button
                type="button"
                onClick={handleApplyFilters}
                disabled={loading || !periodFrom || !periodTo}
                className="unitpnl-btn h-10 px-6 w-full md:w-auto rounded border border-gray-300 bg-white text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {loading ? 'Загрузка…' : 'Обновить'}
              </button>
            </div>
          </div>
          <div className="unitpnl-grid unitpnl-grid--funnel-row2 grid grid-cols-1 gap-6 md:grid-cols-[140px_auto] items-end mt-4" style={{ marginTop: 15 }}>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Категория WB</label>
              <select
                value={wbCategory}
                onChange={(e) => setWbCategory(e.target.value)}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Любая</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {truncate(c, 50)}
                  </option>
                ))}
              </select>
            </div>
            <div className="unitpnl-col unitpnl-checkbox-wrap flex items-center h-10 md:justify-start">
              <label className="flex cursor-pointer select-none items-center text-sm leading-tight">
                <input
                  type="checkbox"
                  checked={onlyCartGt0}
                  onChange={(e) => setOnlyCartGt0(e.target.checked)}
                  className="mr-2 rounded border-gray-300"
                />
                Только товары с cart &gt; 0
              </label>
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

      {loading && !data && <p style={{ color: '#6b7280' }}>Загрузка…</p>}

      {/* Table: 1:1 price-discrepancies (card, table, thead/th, tbody tr, PhotoPopover, styles) */}
      {!loading && data !== null && (
        <div className="card">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: 48 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: '18%' }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 95 }} />
                <col style={{ width: 95 }} />
                <col style={{ width: 88 }} />
                <col style={{ width: '12%' }} />
                <col style={{ width: 80 }} />
                <col style={{ width: 88 }} />
              </colgroup>
              <thead>
                <tr style={{ borderBottom: '2px solid #dee2e6' }}>
                  <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600, lineHeight: 1.3 }}>Фото</th>
                  <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600, lineHeight: 1.3 }}>Артикул / nmID</th>
                  <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600, lineHeight: 1.3 }}>Название</th>
                  <th
                    style={{
                      padding: '10px 8px',
                      textAlign: 'right',
                      fontWeight: 600,
                      cursor: 'pointer',
                      userSelect: 'none',
                      whiteSpace: 'normal',
                      lineHeight: 1.3,
                      wordBreak: 'break-word',
                      overflowWrap: 'break-word',
                      color: sortBy === 'opens' ? '#0ea5e9' : 'inherit',
                    }}
                    onClick={() => handleSort('opens')}
                    title="Сортировать по просмотрам"
                  >
                    Просмотры карточки
                    {sortBy === 'opens' && <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  </th>
                  <th
                    style={{
                      padding: '10px 8px',
                      textAlign: 'right',
                      fontWeight: 600,
                      cursor: 'pointer',
                      userSelect: 'none',
                      whiteSpace: 'normal',
                      lineHeight: 1.3,
                      wordBreak: 'break-word',
                      overflowWrap: 'break-word',
                      color: sortBy === 'cart_rate' ? '#0ea5e9' : 'inherit',
                    }}
                    onClick={() => handleSort('cart_rate')}
                    title="Сортировать по добавлениям в корзину"
                  >
                    Добавления в корзину
                    {sortBy === 'cart_rate' && <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  </th>
                  <th
                    style={{
                      padding: '10px 8px',
                      textAlign: 'right',
                      fontWeight: 600,
                      cursor: 'pointer',
                      userSelect: 'none',
                      whiteSpace: 'normal',
                      lineHeight: 1.3,
                      wordBreak: 'break-word',
                      overflowWrap: 'break-word',
                      color: sortBy === 'order_rate' ? '#0ea5e9' : 'inherit',
                    }}
                    onClick={() => handleSort('order_rate')}
                    title="Сортировать по конверсии в заказ"
                  >
                    Конверсия в заказ
                    {sortBy === 'order_rate' && <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  </th>
                  <th
                    style={{
                      padding: '10px 8px',
                      textAlign: 'right',
                      fontWeight: 600,
                      cursor: 'pointer',
                      userSelect: 'none',
                      whiteSpace: 'normal',
                      lineHeight: 1.3,
                      wordBreak: 'break-word',
                      overflowWrap: 'break-word',
                      color: sortBy === 'revenue' ? '#0ea5e9' : 'inherit',
                    }}
                    onClick={() => handleSort('revenue')}
                    title="Сортировать по сумме заказов"
                  >
                    Сумма заказов
                    {sortBy === 'revenue' && <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  </th>
                  <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600, lineHeight: 1.3 }}>Сигнал</th>
                  <th style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600, lineHeight: 1.3 }}>Potential ₽</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center', fontWeight: 600, lineHeight: 1.3 }}>Критичность</th>
                </tr>
              </thead>
              <tbody>
                {data.length === 0 ? (
                  <tr>
                    <td colSpan={10} style={{ padding: 24, textAlign: 'center', color: '#6b7280' }}>
                      Нет данных за выбранный период
                    </td>
                  </tr>
                ) : (
                  data.map((row, idx) => (
                    <tr
                      key={row.nm_id}
                      onClick={() => setDrawerRow(row)}
                      style={{
                        borderBottom: '1px solid #eee',
                        backgroundColor: idx % 2 === 0 ? '#fff' : '#f8f9fa',
                        cursor: 'pointer',
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setDrawerRow(row)
                        }
                      }}
                      role="button"
                      tabIndex={0}
                    >
                      <td style={{ padding: '8px 6px' }}>
                        <PhotoPopover photos={row.image_url ? [row.image_url] : []} size={36} />
                      </td>
                      <td style={{ padding: '8px 6px', overflow: 'hidden' }}>
                        <div style={{ fontSize: 13, minWidth: 0 }}>
                          <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={row.vendor_code ?? undefined}>
                            {row.vendor_code || '—'}
                          </div>
                          <div style={{ fontSize: 11, color: '#666' }}>
                            {row.nm_id ? (
                              <a
                                href={`https://www.wildberries.ru/catalog/${row.nm_id}/detail.aspx`}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                style={{ color: '#2563eb', textDecoration: 'none' }}
                              >
                                {formatNmId(row.nm_id)}
                                <span style={{ marginLeft: 4, fontSize: 10 }}>↗</span>
                              </a>
                            ) : (
                              '—'
                            )}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '8px 6px', overflow: 'hidden' }}>
                        <div style={{ maxWidth: '100%', minWidth: 0 }}>
                          <div style={{ fontSize: 13 }} title={row.title ?? undefined}>
                            {row.title ? truncate(row.title, 60) : '—'}
                          </div>
                          {row.wb_category && (
                            <div style={{ fontSize: 11, color: '#777', marginTop: 2 }}>
                              {row.wb_category}
                            </div>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatInt(row.opens)}</td>
                      <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatPct(row.cart_rate)}</td>
                      <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatPct(row.order_rate)}</td>
                      <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatRUB(row.revenue)}</td>
                      <td style={{ padding: '8px 6px', overflow: 'hidden' }} title={row.signal_label}>
                        <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {row.signal_label}
                        </span>
                      </td>
                      <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatRUB(row.potential_rub)}</td>
                      <td style={{ padding: '8px 6px', textAlign: 'center' }}>
                        <SeverityBadge severity={row.severity} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination: like price-discrepancies + unit-pnl page_size */}
          {meta && (meta.total > 0 || meta.pages > 1) && (
            <div
              style={{
                padding: 12,
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                gap: 16,
                fontSize: 13,
                color: '#666',
                borderTop: '1px solid #eee',
              }}
            >
              <span>
                Показано {meta.total > 0 ? `${(meta.page - 1) * meta.page_size + 1}–${Math.min(meta.page * meta.page_size, meta.total)}` : '0'} из {meta.total}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  type="button"
                  onClick={() => { setPage(1); load(1) }}
                  disabled={!canGoPrev}
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  title="В начало"
                >
                  ««
                </button>
                <button
                  type="button"
                  onClick={() => { setPage((p) => Math.max(1, p - 1)); load(Math.max(1, (meta?.page ?? 1) - 1)) }}
                  disabled={!canGoPrev}
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  title="Назад"
                >
                  « Назад
                </button>
                <span style={{ whiteSpace: 'nowrap' }}>
                  Страница {meta.page} из {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => { setPage((p) => p + 1); load((meta?.page ?? 1) + 1) }}
                  disabled={!canGoNext}
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  title="Вперёд"
                >
                  Вперёд »
                </button>
                <button
                  type="button"
                  onClick={() => { setPage(totalPages); load(totalPages) }}
                  disabled={!canGoNext}
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  title="В конец"
                >
                  »»
                </button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span>На странице:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    const newSize = parseInt(e.target.value, 10)
                    setPageSize(newSize)
                    setPage(1)
                    load(1, newSize)
                  }}
                  style={{ padding: '4px 8px', fontSize: 12 }}
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
      )}

      {drawerRow && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Детали сигнала"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            display: 'flex',
            alignItems: 'stretch',
            justifyContent: 'flex-end',
          }}
        >
          <div
            style={{
              position: 'absolute',
              inset: 0,
              backgroundColor: 'rgba(0,0,0,0.3)',
            }}
            onClick={() => setDrawerRow(null)}
            onKeyDown={(e) => e.key === 'Escape' && setDrawerRow(null)}
          />
          <div
            style={{
              width: '100%',
              maxWidth: 400,
              backgroundColor: '#fff',
              boxShadow: '-4px 0 20px rgba(0,0,0,0.15)',
              padding: 24,
              overflowY: 'auto',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 18 }}>nm_id {formatNmId(drawerRow.nm_id)}</h2>
              <button
                type="button"
                onClick={() => setDrawerRow(null)}
                className="unitpnl-btn h-10 px-4 rounded border border-gray-300 bg-white text-sm hover:bg-gray-50"
              >
                Закрыть
              </button>
            </div>
            {drawerRow.image_url && (
              <div style={{ marginBottom: 12 }}>
                <img
                  src={drawerRow.image_url}
                  alt=""
                  style={{ maxWidth: '100%', maxHeight: 120, objectFit: 'contain', borderRadius: 6 }}
                />
              </div>
            )}
            <dl style={{ margin: 0, display: 'grid', gap: 8 }}>
              {(drawerRow.vendor_code != null && drawerRow.vendor_code !== '') && (
                <div>
                  <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Артикул</dt>
                  <dd style={{ margin: '2px 0 0' }}>{drawerRow.vendor_code}</dd>
                </div>
              )}
              {drawerRow.title != null && drawerRow.title !== '' && (
                <div>
                  <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Название</dt>
                  <dd style={{ margin: '2px 0 0', fontWeight: 500 }}>{drawerRow.title}</dd>
                </div>
              )}
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Категория</dt>
                <dd style={{ margin: '2px 0 0' }}>{drawerRow.wb_category ?? '—'}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Сигнал</dt>
                <dd style={{ margin: '2px 0 0', fontWeight: 500 }}>{drawerRow.signal_label}</dd>
              </div>
              {drawerRow.signal_details && (
                <div>
                  <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Детали</dt>
                  <dd style={{ margin: '2px 0 0', fontSize: 14 }}>{drawerRow.signal_details}</dd>
                </div>
              )}
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Просмотры карточки</dt>
                <dd style={{ margin: '2px 0 0' }}>{formatInt(drawerRow.opens)}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Добавления в корзину</dt>
                <dd style={{ margin: '2px 0 0' }}>{formatPct(drawerRow.cart_rate)}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Корзина→Заказ</dt>
                <dd style={{ margin: '2px 0 0' }}>{formatPct(drawerRow.cart_to_order)}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Конверсия в заказ</dt>
                <dd style={{ margin: '2px 0 0' }}>{formatPct(drawerRow.order_rate)}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Сумма заказов</dt>
                <dd style={{ margin: '2px 0 0' }}>{formatRUB(drawerRow.revenue)}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Potential ₽</dt>
                <dd style={{ margin: '2px 0 0' }}>{formatRUB(drawerRow.potential_rub)}</dd>
              </div>
              <div>
                <dt style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>Критичность</dt>
                <dd style={{ margin: '2px 0 0' }}>
                  <SeverityBadge severity={drawerRow.severity} />
                </dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      <style jsx global>{`
        .unitpnl-grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 24px;
          align-items: end;
        }
        .unitpnl-col {
          min-width: 0;
        }
        .unitpnl-label {
          display: block;
          margin-bottom: 4px;
          font-size: 14px;
          line-height: 1.25;
          font-weight: 500;
        }
        .unitpnl-control {
          width: 100%;
          height: 40px;
          padding: 8px 12px;
          line-height: 20px;
        }
        .unitpnl-control::placeholder {
          color: #9ca3af;
        }
        .unitpnl-btn {
          height: 40px;
          padding: 0 24px;
          width: 100%;
          margin-right: 0;
          margin-bottom: 0;
          white-space: nowrap;
        }
        .unitpnl-actions {
          align-items: end;
        }
        .unitpnl-checkbox-wrap {
          align-items: center;
          min-height: 40px;
        }
        @media (min-width: 768px) {
          .unitpnl-grid--funnel-row1 {
            grid-template-columns: minmax(120px, 140px) minmax(120px, 140px) minmax(80px, 100px) minmax(140px, 1fr) 120px;
          }
          .unitpnl-grid--funnel-row2 {
            grid-template-columns: minmax(120px, 140px) auto;
          }
          .unitpnl-actions {
            justify-content: flex-end;
          }
          .unitpnl-btn {
            width: auto;
          }
          .unitpnl-checkbox-wrap {
            justify-content: flex-start;
          }
        }
      `}</style>
    </div>
  )
}
