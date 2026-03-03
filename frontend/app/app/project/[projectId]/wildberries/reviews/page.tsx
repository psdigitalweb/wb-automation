'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  getFunnelSignalsCategories,
  getReviewsSummary,
  type WBProductLookupItem,
  type ReviewsSummaryItem,
  type ReviewsSummaryResponse,
} from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import PortalBackButton from '@/components/PortalBackButton'
import WBProductLookupInput from '@/components/WBProductLookupInput'

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

  const hasPhotos = photos.length > 0
  const thumbnailSrc = hasPhotos ? photos[0] : null

  const updatePosition = () => {
    if (!anchorRef.current) return
    const rect = anchorRef.current.getBoundingClientRect()
    setPosition({
      top: rect.bottom + window.scrollY + 8,
      left: rect.left + window.scrollX,
    })
  }

  const handleOpen = () => {
    if (!hasPhotos) return
    updatePosition()
    setOpen(true)
  }

  const handleClose = () => setOpen(false)

  const toggleOpen = () => {
    if (!hasPhotos) return
    if (!open) updatePosition()
    setOpen((value) => !value)
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

function formatRating(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('ru-RU', { useGrouping: true }).format(value)
}

function formatNmId(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return String(value)
}

function truncate(value: string | null | undefined, maxLen: number): string {
  if (value == null) return '—'
  if (value.length <= maxLen) return value
  return value.slice(0, maxLen) + '…'
}

export default function ReviewsPage() {
  const params = useParams()
  const projectId = typeof params?.projectId === 'string' ? params.projectId : ''
  const initialLoadProjectRef = useRef<string | null>(null)
  const [periodFrom, setPeriodFrom] = useState('')
  const [periodTo, setPeriodTo] = useState('')
  const [productSearch, setProductSearch] = useState('')
  const [selectedProduct, setSelectedProduct] = useState<WBProductLookupItem | null>(null)
  const [wbCategory, setWbCategory] = useState('')
  const [ratingLte, setRatingLte] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ReviewsSummaryResponse | null>(null)

  usePageTitle('Отзывы WB', projectId || null)

  useEffect(() => {
    if (!projectId) return
    getFunnelSignalsCategories(projectId)
      .then(setCategories)
      .catch(() => setCategories([]))
  }, [projectId])

  const load = useCallback(() => {
    if (!projectId) return

    const hasAnyDate = periodFrom.trim() !== '' || periodTo.trim() !== ''
    if (hasAnyDate && (!periodFrom.trim() || !periodTo.trim())) {
      setError('Укажите обе даты или оставьте обе пустыми')
      return
    }

    const rawProductValue = productSearch.trim()
    const rawNumericNmId = rawProductValue ? parseInt(rawProductValue, 10) : undefined
    const nmId =
      selectedProduct?.nm_id ??
      (rawProductValue && !Number.isNaN(rawNumericNmId) ? rawNumericNmId : undefined)
    const vendorCode =
      selectedProduct?.vendor_code ??
      (rawProductValue && (Number.isNaN(rawNumericNmId) || rawNumericNmId == null) ? rawProductValue : undefined)

    const ratingValue = ratingLte.trim() ? parseFloat(ratingLte.trim().replace(',', '.')) : undefined
    if (ratingLte.trim() && (Number.isNaN(ratingValue) || ratingValue == null || ratingValue < 0 || ratingValue > 5)) {
      setError('Рейтинг должен быть числом от 0 до 5')
      setLoading(false)
      return
    }

    setError(null)
    setLoading(true)

    getReviewsSummary(projectId, {
      period_from: periodFrom.trim() || undefined,
      period_to: periodTo.trim() || undefined,
      nm_id: nmId,
      vendor_code: vendorCode,
      wb_category: wbCategory || undefined,
      rating_lte: ratingValue,
    })
      .then((res) => setData(res))
      .catch((err: any) => {
        setError(err?.detail || err?.message || 'Ошибка загрузки')
        setData(null)
      })
      .finally(() => setLoading(false))
  }, [projectId, periodFrom, periodTo, productSearch, selectedProduct, wbCategory, ratingLte])

  useEffect(() => {
    if (!projectId) return
    if (initialLoadProjectRef.current === projectId) return
    initialLoadProjectRef.current = projectId
    load()
  }, [projectId, load])

  const items = data?.items ?? []
  const showNewReviews = periodFrom.trim() !== '' && periodTo.trim() !== ''

  return (
    <div className="container">
      <div style={{ marginBottom: 12 }}>
        <PortalBackButton fallbackHref={`/app/project/${projectId}/dashboard`} />
      </div>
      <h1 style={{ marginTop: 0, marginBottom: 20 }}>Отзывы Wildberries</h1>

      <div className="card mb-5">
        <div className="p-4">
          <h3 className="m-0 mb-3 text-base font-semibold">Фильтры</h3>
          <div className="unitpnl-grid unitpnl-grid--reviews-row1 grid grid-cols-1 gap-6 items-end">
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
              <label className="unitpnl-label block text-sm font-medium mb-1">Товар</label>
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
                className="unitpnl-control"
              />
            </div>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Категория WB</label>
              <select
                value={wbCategory}
                onChange={(e) => setWbCategory(e.target.value)}
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Любая</option>
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {truncate(category, 50)}
                  </option>
                ))}
              </select>
            </div>
            <div className="unitpnl-col flex flex-col min-w-0">
              <label className="unitpnl-label block text-sm font-medium mb-1">Рейтинг до</label>
              <input
                type="text"
                value={ratingLte}
                onChange={(e) => setRatingLte(e.target.value)}
                placeholder="Например, 4.2"
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400"
              />
            </div>
            <div className="unitpnl-col unitpnl-actions flex items-end md:justify-end">
              <div className="unitpnl-actionsRow">
                <button
                  type="button"
                  onClick={() => {
                    setPeriodFrom('')
                    setPeriodTo('')
                  }}
                  disabled={loading || (!periodFrom && !periodTo)}
                  className="unitpnl-btn h-10 px-4 w-full md:w-auto rounded border border-gray-300 bg-white text-sm hover:bg-gray-50 disabled:opacity-50"
                >
                  Сбросить даты
                </button>
                <button
                  type="button"
                  onClick={load}
                  disabled={loading}
                  className="unitpnl-btn h-10 px-6 w-full md:w-auto rounded border border-gray-300 bg-white text-sm hover:bg-gray-50 disabled:opacity-50"
                >
                  {loading ? 'Загрузка…' : 'Обновить'}
                </button>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color: '#6b7280' }}>
            Если даты не заданы, показывается полная картина по SKU. Даты влияют только на колонку новых отзывов за период.
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
          <table className="w-full border-collapse" style={{ fontSize: 14, tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: 52 }} />
              <col style={{ width: 132 }} />
              <col style={{ width: 'auto' }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 140 }} />
              <col style={{ width: 130 }} />
            </colgroup>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600 }}>Фото</th>
                <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600 }}>Артикул / nmID</th>
                <th style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 600 }}>Товар</th>
                <th style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>Кол-во отзывов</th>
                <th style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>Средний рейтинг</th>
                <th style={{ padding: '10px 8px', textAlign: 'right', fontWeight: 600 }}>Новых за период</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 24, textAlign: 'center', color: '#6b7280' }}>
                    Нет данных по выбранным фильтрам
                  </td>
                </tr>
              ) : (
                items.map((row, idx) => (
                  <tr
                    key={row.nm_id}
                    style={{
                      borderBottom: '1px solid #eee',
                      backgroundColor: idx % 2 === 0 ? '#fff' : '#f8f9fa',
                    }}
                  >
                    <td style={{ padding: '8px 6px' }}>
                      <PhotoPopover photos={row.image_url ? [row.image_url] : []} size={36} />
                    </td>
                    <td style={{ padding: '8px 6px', overflow: 'hidden' }}>
                      <div style={{ fontSize: 13, minWidth: 0 }}>
                        <div
                          style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                          title={row.vendor_code ?? undefined}
                        >
                          {row.vendor_code || '—'}
                        </div>
                        <div style={{ fontSize: 11, color: '#666' }}>
                          <a
                            href={`https://www.wildberries.ru/catalog/${row.nm_id}/detail.aspx`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: '#2563eb', textDecoration: 'none' }}
                          >
                            {formatNmId(row.nm_id)}
                            <span style={{ marginLeft: 4, fontSize: 10 }}>↗</span>
                          </a>
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
                    <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatInt(row.reviews_count_total)}</td>
                    <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatRating(row.avg_rating)}</td>
                    <td style={{ padding: '8px 6px', textAlign: 'right' }}>
                      {showNewReviews ? formatInt(row.new_reviews) : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
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
          min-width: 0;
        }
        .unitpnl-actionsRow {
          display: flex;
          gap: 12px;
          width: 100%;
          flex-wrap: wrap;
          justify-content: flex-end;
        }
        @media (min-width: 768px) {
          .unitpnl-grid--reviews-row1 {
            grid-template-columns:
              minmax(120px, 140px)
              minmax(120px, 140px)
              minmax(220px, 1.3fr)
              minmax(180px, 1fr)
              minmax(140px, 160px);
          }
          .unitpnl-actions {
            grid-column: 1 / -1;
            justify-content: flex-end;
          }
          .unitpnl-actionsRow {
            width: auto;
            flex-wrap: nowrap;
          }
          .unitpnl-btn {
            width: auto;
          }
        }
      `}</style>
    </div>
  )
}
