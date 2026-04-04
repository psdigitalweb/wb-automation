'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import {
  getFunnelSignalsCategories,
  getReviewsList,
  getReviewsSummary,
  type ReviewDetailItem,
  type WBProductLookupItem,
  type ReviewsSummaryResponse,
} from '@/lib/apiClient'
import { usePageTitle } from '@/hooks/usePageTitle'
import PortalBackButton from '@/components/PortalBackButton'
import WBProductLookupInput from '@/components/WBProductLookupInput'

const REVIEWS_PAGE_SIZE = 20

type ReviewsListState = {
  items: ReviewDetailItem[]
  total: number
  hasMore: boolean
  loaded: boolean
  loading: boolean
  loadingMore: boolean
  error: string | null
}

function PhotoPopover({
  photos,
  size = 36,
  title = 'Фото',
  emptyLabel = 'Нет фото',
}: {
  photos: string[]
  size?: number
  title?: string
  emptyLabel?: string
}) {
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
          {emptyLabel}
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
            <strong style={{ fontSize: 12 }}>{title}</strong>
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

function formatReviewDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

function renderReviewRating(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) {
    return <span style={{ color: '#6b7280' }}>Без оценки</span>
  }
  const normalized = Math.max(0, Math.min(5, Math.round(value)))
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ color: '#f59e0b', letterSpacing: 1 }}>{`${'★'.repeat(normalized)}${'☆'.repeat(5 - normalized)}`}</span>
      <span style={{ color: '#4b5563', fontSize: 12 }}>{value.toFixed(1)}</span>
    </span>
  )
}

function mergeReviewItems(existing: ReviewDetailItem[], incoming: ReviewDetailItem[]): ReviewDetailItem[] {
  const seen = new Set(existing.map((item) => item.external_id))
  const next = [...existing]
  incoming.forEach((item) => {
    if (!seen.has(item.external_id)) {
      seen.add(item.external_id)
      next.push(item)
    }
  })
  return next
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
  const [onlyEnterpriseGt0, setOnlyEnterpriseGt0] = useState(false)
  const [onlyFboGt0, setOnlyFboGt0] = useState(false)
  const [onlyWithReviewsInPeriod, setOnlyWithReviewsInPeriod] = useState(false)
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ReviewsSummaryResponse | null>(null)
  const [expandedNmId, setExpandedNmId] = useState<number | null>(null)
  const [reviewsByNmId, setReviewsByNmId] = useState<Record<number, ReviewsListState>>({})
  const [appliedPeriod, setAppliedPeriod] = useState<{ periodFrom?: string; periodTo?: string }>({})

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
      only_enterprise_gt0: onlyEnterpriseGt0,
      only_fbo_gt0: onlyFboGt0,
      only_with_reviews_in_period: onlyWithReviewsInPeriod,
    })
      .then((res) => {
        setData(res)
        setExpandedNmId(null)
        setReviewsByNmId({})
        setAppliedPeriod({
          periodFrom: periodFrom.trim() || undefined,
          periodTo: periodTo.trim() || undefined,
        })
      })
      .catch((err: any) => {
        setError(err?.detail || err?.message || 'Ошибка загрузки')
        setData(null)
        setExpandedNmId(null)
        setReviewsByNmId({})
      })
      .finally(() => setLoading(false))
  }, [projectId, periodFrom, periodTo, productSearch, selectedProduct, wbCategory, ratingLte, onlyEnterpriseGt0, onlyFboGt0, onlyWithReviewsInPeriod])

  const loadReviews = useCallback(
    (nmId: number, options?: { offset?: number; append?: boolean }) => {
      if (!projectId) return
      const offset = options?.offset ?? 0
      const append = options?.append ?? false

      setReviewsByNmId((prev) => {
        const current = prev[nmId]
        return {
          ...prev,
          [nmId]: {
            items: append ? current?.items ?? [] : current?.items ?? [],
            total: current?.total ?? 0,
            hasMore: current?.hasMore ?? false,
            loaded: current?.loaded ?? false,
            loading: !append,
            loadingMore: append,
            error: null,
          },
        }
      })

      getReviewsList(projectId, {
        nm_id: nmId,
        period_from: appliedPeriod.periodFrom,
        period_to: appliedPeriod.periodTo,
        limit: REVIEWS_PAGE_SIZE,
        offset,
      })
        .then((res) => {
          setReviewsByNmId((prev) => {
            const current = prev[nmId]
            return {
              ...prev,
              [nmId]: {
                items: append ? mergeReviewItems(current?.items ?? [], res.items) : res.items,
                total: res.total,
                hasMore: res.has_more,
                loaded: true,
                loading: false,
                loadingMore: false,
                error: null,
              },
            }
          })
        })
        .catch((err: any) => {
          setReviewsByNmId((prev) => {
            const current = prev[nmId]
            return {
              ...prev,
              [nmId]: {
                items: current?.items ?? [],
                total: current?.total ?? 0,
                hasMore: current?.hasMore ?? false,
                loaded: current?.loaded ?? false,
                loading: false,
                loadingMore: false,
                error: err?.detail || err?.message || 'Не удалось загрузить отзывы',
              },
            }
          })
        })
    },
    [appliedPeriod.periodFrom, appliedPeriod.periodTo, projectId]
  )

  const toggleReviews = useCallback(
    (nmId: number) => {
      if (expandedNmId === nmId) {
        setExpandedNmId(null)
        return
      }
      setExpandedNmId(nmId)
      const state = reviewsByNmId[nmId]
      if (!state || (!state.loaded && !state.loading)) {
        loadReviews(nmId)
      }
    },
    [expandedNmId, loadReviews, reviewsByNmId]
  )

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
              <label className="unitpnl-label block text-sm font-medium mb-1">Рейтинг до</label>
              <input
                type="text"
                value={ratingLte}
                onChange={(e) => setRatingLte(e.target.value)}
                placeholder="Например, 4.2"
                className="unitpnl-control h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm leading-5 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder:text-gray-400"
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
            <div className="unitpnl-col unitpnl-actions flex items-end md:justify-end">
              <button
                type="button"
                onClick={load}
                disabled={loading}
                className="unitpnl-btn reviews-side-button h-10 px-6 w-full rounded border border-gray-300 bg-white text-sm hover:bg-gray-50 disabled:opacity-50"
                style={{ margin: 0 }}
              >
                {loading ? 'Загрузка…' : 'Обновить'}
              </button>
            </div>
          </div>
          <div
            className="unitpnl-grid unitpnl-grid--reviews-row2 grid grid-cols-1 gap-6 items-end"
            style={{ marginTop: 15 }}
          >
            <div className="unitpnl-col flex flex-col min-w-0 reviews-row2-category">
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
            <div className="unitpnl-col reviews-row2-checks">
              <label className="unitpnl-label block text-sm font-medium mb-1" style={{ visibility: 'hidden' }}>
                ·
              </label>
              <div className="reviews-checkbox-row" style={{ width: '100%' }}>
                <label className="reviews-checkbox">
                  <input
                    type="checkbox"
                    checked={onlyWithReviewsInPeriod}
                    onChange={(e) => setOnlyWithReviewsInPeriod(e.target.checked)}
                    style={{ marginRight: 8 }}
                  />
                  Только с отзывами за период
                </label>
                <label className="reviews-checkbox">
                  <input
                    type="checkbox"
                    checked={onlyEnterpriseGt0}
                    onChange={(e) => setOnlyEnterpriseGt0(e.target.checked)}
                    style={{ marginRight: 8 }}
                  />
                  Наличие склад &gt; 0
                </label>
                <label className="reviews-checkbox">
                  <input
                    type="checkbox"
                    checked={onlyFboGt0}
                    onChange={(e) => setOnlyFboGt0(e.target.checked)}
                    style={{ marginRight: 8 }}
                  />
                  Наличие FBO &gt; 0
                </label>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color: '#6b7280' }}>
            Если даты не заданы, показывается полная картина по SKU. Даты влияют на колонку новых отзывов и на раскрытый список отзывов по товару.
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
                items.map((row, idx) => {
                  const isExpanded = expandedNmId === row.nm_id
                  const reviewsState = reviewsByNmId[row.nm_id]
                  const reviewItems = reviewsState?.items ?? []
                  const reviewsTotal = reviewsState?.total ?? 0
                  const reviewsHasMore = reviewsState?.hasMore ?? false

                  return (
                    <React.Fragment key={row.nm_id}>
                      <tr
                        style={{
                          borderBottom: isExpanded ? 'none' : '1px solid #eee',
                          backgroundColor: idx % 2 === 0 ? '#fff' : '#f8f9fa',
                        }}
                      >
                        <td style={{ padding: '8px 6px' }}>
                          <PhotoPopover photos={row.image_url ? [row.image_url] : []} size={36} title="Фото товара" />
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
                              <div style={{ fontSize: 11, color: '#777', marginTop: 2 }}>{row.wb_category}</div>
                            )}
                            <div style={{ marginTop: 8 }}>
                              <button
                                type="button"
                                onClick={() => toggleReviews(row.nm_id)}
                                disabled={reviewsState?.loadingMore}
                                style={{
                                  border: '1px solid #d1d5db',
                                  background: '#fff',
                                  borderRadius: 6,
                                  padding: '6px 10px',
                                  fontSize: 12,
                                  color: '#1f2937',
                                  cursor: 'pointer',
                                }}
                              >
                                {isExpanded ? 'Скрыть отзывы' : 'Показать отзывы'}
                              </button>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatInt(row.reviews_count_total)}</td>
                        <td style={{ padding: '8px 6px', textAlign: 'right' }}>{formatRating(row.avg_rating)}</td>
                        <td style={{ padding: '8px 6px', textAlign: 'right' }}>
                          {showNewReviews ? formatInt(row.new_reviews) : '—'}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr style={{ borderBottom: '1px solid #eee', backgroundColor: '#f9fafb' }}>
                          <td colSpan={6} style={{ padding: '0 12px 12px' }}>
                            <div
                              style={{
                                border: '1px solid #e5e7eb',
                                borderRadius: 10,
                                background: '#fff',
                                padding: 16,
                              }}
                            >
                              <div
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  gap: 12,
                                  flexWrap: 'wrap',
                                  marginBottom: 12,
                                }}
                              >
                                <div style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>
                                  Отзывы по товару
                                </div>
                                <div style={{ fontSize: 12, color: '#6b7280' }}>
                                  Загружено {formatInt(reviewItems.length)} из {formatInt(reviewsTotal)}
                                </div>
                              </div>

                              {reviewsState?.loading && !reviewsState.loaded && (
                                <div style={{ color: '#6b7280', fontSize: 14 }}>Загружаем отзывы…</div>
                              )}

                              {reviewsState?.error && (
                                <div
                                  style={{
                                    background: '#fef2f2',
                                    color: '#991b1b',
                                    border: '1px solid #fecaca',
                                    borderRadius: 8,
                                    padding: 12,
                                    marginBottom: 12,
                                  }}
                                >
                                  {reviewsState.error}
                                </div>
                              )}

                              {reviewsState?.loaded &&
                                !reviewsState.loading &&
                                !reviewsState.error &&
                                reviewItems.length === 0 && (
                                  <div style={{ color: '#6b7280', fontSize: 14 }}>По этому товару отзывов пока нет.</div>
                                )}

                              {reviewItems.length ? (
                                <div style={{ display: 'grid', gap: 12 }}>
                                  {reviewItems.map((review) => (
                                    <div
                                      key={review.external_id}
                                      style={{
                                        border: '1px solid #e5e7eb',
                                        borderRadius: 10,
                                        padding: 14,
                                        background: review.is_archived ? '#fafafa' : '#ffffff',
                                      }}
                                    >
                                      <div
                                        style={{
                                          display: 'flex',
                                          justifyContent: 'space-between',
                                          gap: 12,
                                          flexWrap: 'wrap',
                                          marginBottom: 10,
                                        }}
                                      >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                                          <strong style={{ fontSize: 14, color: '#111827' }}>
                                            {review.user_name || 'Покупатель'}
                                          </strong>
                                          <span style={{ fontSize: 12, color: '#6b7280' }}>
                                            {formatReviewDate(review.created_date)}
                                          </span>
                                          {review.is_archived && (
                                            <span
                                              style={{
                                                fontSize: 11,
                                                padding: '2px 8px',
                                                borderRadius: 999,
                                                background: '#f3f4f6',
                                                color: '#4b5563',
                                              }}
                                            >
                                              Архив
                                            </span>
                                          )}
                                          {review.is_answered && (
                                            <span
                                              style={{
                                                fontSize: 11,
                                                padding: '2px 8px',
                                                borderRadius: 999,
                                                background: '#dcfce7',
                                                color: '#166534',
                                              }}
                                            >
                                              Есть ответ
                                            </span>
                                          )}
                                          {review.has_media && (
                                            <span
                                              style={{
                                                fontSize: 11,
                                                padding: '2px 8px',
                                                borderRadius: 999,
                                                background: '#dbeafe',
                                                color: '#1d4ed8',
                                              }}
                                            >
                                              Медиа
                                            </span>
                                          )}
                                        </div>
                                        <div>{renderReviewRating(review.rating)}</div>
                                      </div>

                                      {review.text && (
                                        <div style={{ marginBottom: 10, whiteSpace: 'pre-wrap', color: '#111827', lineHeight: 1.5 }}>
                                          {review.text}
                                        </div>
                                      )}

                                      {review.pros && (
                                        <div style={{ marginBottom: 8, color: '#166534', lineHeight: 1.5 }}>
                                          <strong>Плюсы:</strong> {review.pros}
                                        </div>
                                      )}

                                      {review.cons && (
                                        <div style={{ marginBottom: 8, color: '#991b1b', lineHeight: 1.5 }}>
                                          <strong>Минусы:</strong> {review.cons}
                                        </div>
                                      )}

                                      {!review.text && !review.pros && !review.cons && (
                                        <div style={{ marginBottom: 10, color: '#6b7280' }}>Без текстового комментария</div>
                                      )}

                                      {(review.photo_urls.length > 0 || review.video_url) && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                                          {review.photo_urls.length > 0 && (
                                            <PhotoPopover
                                              photos={review.photo_urls}
                                              size={44}
                                              title="Фото отзыва"
                                              emptyLabel="Нет медиа"
                                            />
                                          )}
                                          {review.video_url && (
                                            <a
                                              href={review.video_url}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              style={{ color: '#2563eb', fontSize: 13, textDecoration: 'none' }}
                                            >
                                              Видео отзыва ↗
                                            </a>
                                          )}
                                        </div>
                                      )}

                                      {review.answer_text && (
                                        <div
                                          style={{
                                            borderRadius: 8,
                                            background: '#eff6ff',
                                            border: '1px solid #bfdbfe',
                                            padding: 12,
                                            color: '#1e3a8a',
                                            lineHeight: 1.5,
                                          }}
                                        >
                                          <strong style={{ display: 'block', marginBottom: 4 }}>Ответ продавца</strong>
                                          {review.answer_text}
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              ) : null}

                              {reviewsHasMore && (
                                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'center' }}>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      loadReviews(row.nm_id, {
                                        offset: reviewItems.length,
                                        append: true,
                                      })
                                    }
                                    disabled={reviewsState.loadingMore}
                                    style={{
                                      border: '1px solid #d1d5db',
                                      background: '#fff',
                                      color: '#1f2937',
                                      borderRadius: 8,
                                      padding: '8px 14px',
                                      fontSize: 13,
                                      lineHeight: 1.2,
                                      cursor: reviewsState.loadingMore ? 'not-allowed' : 'pointer',
                                      opacity: reviewsState.loadingMore ? 0.7 : 1,
                                    }}
                                  >
                                    {reviewsState.loadingMore ? 'Загружаем…' : 'Показать ещё отзывы'}
                                  </button>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })
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
        .reviews-checkbox-row {
          display: flex;
          align-items: center;
          gap: 20px;
          height: 40px;
          width: 100%;
          flex-wrap: nowrap;
          overflow: visible;
        }
        .reviews-checkbox {
          display: flex;
          align-items: center;
          white-space: nowrap;
          font-size: 14px;
          line-height: 20px;
          cursor: pointer;
          user-select: none;
          min-width: 0;
        }
        .reviews-side-button {
          height: 40px !important;
          box-sizing: border-box;
        }
        @media (min-width: 768px) {
          .unitpnl-grid--reviews-row1 {
            grid-template-columns:
              minmax(120px, 140px)
              minmax(120px, 140px)
              minmax(160px, 180px)
              minmax(220px, 1fr)
              minmax(150px, 160px);
          }
          .unitpnl-grid--reviews-row2 {
            grid-template-columns:
              minmax(120px, 140px)
              minmax(120px, 140px)
              minmax(160px, 180px)
              minmax(220px, 1fr)
              minmax(150px, 160px);
          }
          .reviews-row2-category {
            grid-column: 1 / span 3;
          }
          .reviews-row2-checks {
            grid-column: 4 / span 2;
          }
          .reviews-side-button {
            width: 160px !important;
            min-width: 160px !important;
            max-width: 160px !important;
          }
          .unitpnl-actions {
            justify-content: flex-end;
          }
          .unitpnl-btn {
            width: auto;
          }
        }
      `}</style>
    </div>
  )
}
