'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import PortalBackButton from '@/components/PortalBackButton'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getWBSearchReportProducts,
  getWBSearchReportKeywordsMulti,
  getWBSearchReportSnapshots,
  getWBSearchReportSubjects,
  runWBIngest,
  type WBSearchReportProduct,
  type WBSearchReportSnapshot,
  type WBSearchReportSubjectItem,
} from '@/lib/apiClient'

function PhotoPopover({ photos, size = 36 }: { photos: string[]; size?: number }) {
  const [open, setOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const hasPhotos = Array.isArray(photos) && photos.length > 0
  const thumbnailSrc = hasPhotos ? photos[0] : null

  return (
    <div
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => hasPhotos && setOpen(true)}
      onMouseLeave={() => setOpen(false)}
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
            border: '1px solid #ddd',
            cursor: 'pointer',
          }}
          loading="lazy"
          onClick={() => setOpen((o) => !o)}
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
          Фото
        </div>
      )}
      {open && hasPhotos ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 1000,
            top: size + 8,
            left: 0,
            background: '#fff',
            border: '1px solid #ddd',
            borderRadius: 6,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            padding: 8,
            minWidth: 260,
            maxWidth: 420,
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: 8 }}>
            <img
              src={photos[selectedIndex]}
              alt="Фото товара крупно"
              style={{ maxWidth: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 4 }}
              loading="lazy"
            />
          </div>
          {photos.length > 1 ? (
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
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function formatDateInput(d: Date) {
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

export default function WBSearchReportTabularPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle(`WB • Отчёт по поиску`)

  const defaultDates = useMemo(() => {
    const today = new Date()
    const to = new Date(today)
    to.setDate(to.getDate() - 1)
    const from = new Date(to)
    from.setDate(from.getDate() - 6)
    return { from: formatDateInput(from), to: formatDateInput(to) }
  }, [])

  const [dateFrom, setDateFrom] = useState(defaultDates.from)
  const [dateTo, setDateTo] = useState(defaultDates.to)
  const [q, setQ] = useState('')

  const [snapshots, setSnapshots] = useState<WBSearchReportSnapshot[]>([])
  const [snapshotId, setSnapshotId] = useState<number | null>(null)

  const [products, setProducts] = useState<WBSearchReportProduct[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 50
  const [sortBy, setSortBy] = useState<string>('vendor_code')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [subjectId, setSubjectId] = useState<number | null>(null)
  const [subjects, setSubjects] = useState<WBSearchReportSubjectItem[]>([])
  const [loadingSubjects, setLoadingSubjects] = useState(false)

  const [keywordsOpen, setKeywordsOpen] = useState(false)
  const [keywordsLoading, setKeywordsLoading] = useState(false)
  const [keywordsNmId, setKeywordsNmId] = useState<number | null>(null)
  const [keywordsOrders, setKeywordsOrders] = useState<any[]>([])
  const [keywordsOpenCard, setKeywordsOpenCard] = useState<any[]>([])
  const [keywordsAddToCart, setKeywordsAddToCart] = useState<any[]>([])
  const [keywordsErrors, setKeywordsErrors] = useState<Record<string, any>>({})
  const [keywordsRequestError, setKeywordsRequestError] = useState<string | null>(null)

  const [loadingSnapshots, setLoadingSnapshots] = useState(false)
  const [loadingProducts, setLoadingProducts] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const pages = Math.max(1, Math.ceil(total / pageSize))
  const selectedSnapshot = useMemo(() => snapshots.find((s) => s.id === snapshotId) ?? null, [snapshots, snapshotId])
  const snapshotPeriodLabel = selectedSnapshot ? `${selectedSnapshot.period_from}…${selectedSnapshot.period_to}` : null
  const inputsPeriodLabel = `${dateFrom}…${dateTo}`
  const snapshotProductsTotal = useMemo(() => {
    const v = (selectedSnapshot as any)?.stats?.products_upserted
    if (typeof v === 'number') return v
    const parsed = Number(v)
    return Number.isFinite(parsed) ? parsed : null
  }, [selectedSnapshot])

  const loadSnapshots = useCallback(async () => {
    setLoadingSnapshots(true)
    setMessage(null)
    try {
      const data = await getWBSearchReportSnapshots(projectId, 50)
      setSnapshots(data.items || [])
      if (!snapshotId && data.items && data.items.length > 0) {
        setSnapshotId(data.items[0].id)
      }
    } catch (e: any) {
      setMessage(`Не удалось загрузить snapshots: ${e?.message || String(e)}`)
    } finally {
      setLoadingSnapshots(false)
    }
  }, [projectId, snapshotId])

  const loadProducts = useCallback(async () => {
    if (!snapshotId) return
    setLoadingProducts(true)
    setMessage(null)
    try {
      const data = await getWBSearchReportProducts(projectId, {
        snapshot_id: snapshotId,
        q: q || undefined,
        subject_id: subjectId ?? undefined,
        date_from: dateFrom,
        date_to: dateTo,
        sort: sortBy,
        order: sortOrder,
        page,
        page_size: pageSize,
      })
      setProducts(data.items || [])
      setTotal(data.total || 0)
    } catch (e: any) {
      setMessage(`Не удалось загрузить товары: ${e?.message || String(e)}`)
    } finally {
      setLoadingProducts(false)
    }
  }, [projectId, snapshotId, q, subjectId, dateFrom, dateTo, sortBy, sortOrder, page])

  const loadSubjects = useCallback(
    async (snapshot_id: number, qValue: string) => {
      setLoadingSubjects(true)
      try {
        const data = await getWBSearchReportSubjects(projectId, {
          snapshot_id,
          q: qValue || undefined,
        })
        setSubjects(data.items || [])
      } catch (_e: any) {
        setSubjects([])
      } finally {
        setLoadingSubjects(false)
      }
    },
    [projectId]
  )

  const openKeywords = useCallback(
    async (nmId: number, forceRefresh = false) => {
      if (!snapshotId) return
      setKeywordsOpen(true)
      setKeywordsLoading(true)
      setKeywordsNmId(nmId)
      setKeywordsOrders([])
      setKeywordsOpenCard([])
      setKeywordsAddToCart([])
      setKeywordsErrors({})
      setKeywordsRequestError(null)
      try {
        const cacheTtlHours =
          forceRefresh || (snapshotPeriodLabel && snapshotPeriodLabel !== inputsPeriodLabel) ? 0 : 24
        const data = await getWBSearchReportKeywordsMulti(projectId, {
          snapshot_id: snapshotId,
          nm_id: nmId,
          date_from: dateFrom,
          date_to: dateTo,
          limit: 30,
          cache_ttl_hours: cacheTtlHours,
        })
        setKeywordsOrders(data.orders || [])
        setKeywordsOpenCard(data.openCard || [])
        setKeywordsAddToCart(data.addToCart || [])
        setKeywordsErrors(data.errors || {})
      } catch (e: any) {
        const msg = e?.detail ? JSON.stringify(e.detail) : e?.message || String(e)
        setKeywordsRequestError(msg)
        setMessage(`Не удалось загрузить ключевые слова: ${msg}`)
      } finally {
        setKeywordsLoading(false)
      }
    },
    [projectId, snapshotId, dateFrom, dateTo, snapshotPeriodLabel, inputsPeriodLabel]
  )

  useEffect(() => {
    loadSnapshots()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  useEffect(() => {
    setPage(1)
  }, [snapshotId, q, subjectId, dateFrom, dateTo, sortBy, sortOrder])

  useEffect(() => {
    setSubjectId(null)
  }, [snapshotId])

  useEffect(() => {
    loadProducts()
  }, [loadProducts])

  useEffect(() => {
    if (!snapshotId) {
      setSubjects([])
      return
    }
    const t = setTimeout(() => loadSubjects(snapshotId, q), 250)
    return () => clearTimeout(t)
  }, [snapshotId, q, loadSubjects])

  const runBackfill = useCallback(async () => {
    setActionBusy(true)
    setMessage(null)
    try {
      const res = await runWBIngest(projectId, 'wb_search_report_tabular', {
        date_from: dateFrom,
        date_to: dateTo,
        include_search_texts: true,
        include_substituted_skus: true,
        position_cluster: 'all',
        order_by: { field: 'avgPosition', mode: 'asc' },
      })
      setMessage(`Запущено. run_id=${res.id}, status=${res.status}`)
      await loadSnapshots()
    } catch (e: any) {
      setMessage(`Не удалось запустить ingest: ${e?.message || String(e)}`)
    } finally {
      setActionBusy(false)
    }
  }, [projectId, dateFrom, dateTo, loadSnapshots])

  function formatInt(value: number | null | undefined): string {
    if (value == null || Number.isNaN(value)) return '—'
    return new Intl.NumberFormat('ru-RU', { useGrouping: true }).format(value)
  }

  function formatPct(value: number | null | undefined): string {
    if (value == null || Number.isNaN(value)) return '—'
    return `${(value * 100).toFixed(1)}%`
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

  const handleSort = (field: string) => {
    const nextOrder: 'asc' | 'desc' = sortBy === field ? (sortOrder === 'asc' ? 'desc' : 'asc') : 'desc'
    setSortBy(field)
    setSortOrder(nextOrder)
    setPage(1)
  }

  return (
    <div className="container">
      <div style={{ marginBottom: 12 }}>
        <PortalBackButton href={`/app/project/${projectId}/wildberries`} />
      </div>
      <h1 style={{ marginTop: 0, marginBottom: 20 }}>WB • Отчёт по поиску (табличный)</h1>

      <div className="card mb-5">
        <div className="p-4">
          <div className="unitpnl-grid unitpnl-grid--searchreport-row1">
            <div className="unitpnl-col">
              <label className="unitpnl-label">Дата с</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="unitpnl-control"
              />
            </div>
            <div className="unitpnl-col">
              <label className="unitpnl-label">Дата по</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="unitpnl-control"
              />
            </div>
            <div className="unitpnl-col">
              <label className="unitpnl-label">Категория WB</label>
              <select
                value={subjectId ?? ''}
                onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)}
                className="unitpnl-control"
                disabled={!snapshotId || loadingSubjects}
                title={!snapshotId ? 'Сначала выберите snapshot' : ''}
              >
                <option value="">Все категории</option>
                {subjects
                  .filter((s) => (s?.products_cnt ?? 0) > 0)
                  .map((s) => (
                    <option key={s.subject_id} value={s.subject_id}>
                      {(s.subject_name || `subject ${s.subject_id}`) + ` (${s.products_cnt})`}
                    </option>
                  ))}
              </select>
            </div>
            <div className="unitpnl-col">
              <label className="unitpnl-label">Поиск</label>
              <input
                type="text"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="name / vendor_code / nm_id"
                className="unitpnl-control"
              />
            </div>
            <div className="unitpnl-col unitpnl-actions unitpnl-actions--searchreport">
              <button type="button" disabled={actionBusy} onClick={runBackfill} className="unitpnl-btn">
                Собрать отчёт
              </button>
            </div>
          </div>
          {message && <div style={{ marginTop: 10, color: '#555', whiteSpace: 'pre-wrap' }}>{message}</div>}
        </div>
      </div>

      <div className="card mb-5">
        <div className="p-4">
          <h3 className="m-0 mb-3 text-base font-semibold">Загруженные отчеты</h3>
          {loadingSnapshots ? (
            <div>Загрузка…</div>
          ) : (
            <>
              <div className="unitpnl-grid unitpnl-grid--searchreport-snap">
                <div className="unitpnl-col">
                  <select
                    value={snapshotId ?? ''}
                    onChange={(e) => setSnapshotId(e.target.value ? Number(e.target.value) : null)}
                    className="unitpnl-control"
                  >
                    <option value="">— выбрать —</option>
                    {snapshots.map((s) => (
                      <option key={s.id} value={s.id}>
                        #{s.id} • {s.period_from}…{s.period_to} • {new Date(s.created_at).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="unitpnl-col unitpnl-snapmeta">
                  <div style={{ fontSize: 12, opacity: 0.8 }}>
                    {snapshotId ? (
                      <>
                        <div>
                          Отфильтровано: {total}
                          {snapshotProductsTotal != null ? ` • В отчете: ${snapshotProductsTotal}` : ''}
                        </div>
                        {snapshotPeriodLabel ? <div>Отчет по ключевым словам: {snapshotPeriodLabel}</div> : null}
                        <div>Данные воронки продаж: {inputsPeriodLabel}</div>
                      </>
                    ) : (
                      'Выберите snapshot'
                    )}
                  </div>
                </div>
                <div className="unitpnl-col unitpnl-actions unitpnl-actions--searchreport-snap">
                  <button type="button" disabled={loadingSnapshots} onClick={loadSnapshots} className="unitpnl-btn">
                    Обновить snapshots
                  </button>
                </div>
              </div>
              {selectedSnapshot?.stats?.ok === false ? (
                <div
                  style={{
                    marginTop: 10,
                    padding: 10,
                    borderRadius: 8,
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#b91c1c',
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  Snapshot #{selectedSnapshot.id} завершился с ошибкой: {String(selectedSnapshot?.stats?.reason || 'error')}
                  {selectedSnapshot?.stats?.error ? `\n${String(selectedSnapshot.stats.error)}` : ''}
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h2 style={{ marginTop: 0 }}>Товары</h2>
        {!snapshotId ? (
          <div>Выберите snapshot</div>
        ) : loadingProducts ? (
          <div>Загрузка…</div>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <div style={{ fontSize: 12, opacity: 0.8 }}>
                Страница {page} / {pages} • всего {total}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  Назад
                </button>
                <button type="button" disabled={page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))}>
                  Вперёд
                </button>
              </div>
            </div>

            <div style={{ overflowX: 'auto', marginTop: 10 }}>
              <table className="sr-table">
                <colgroup>
                  <col style={{ width: 44 }} />
                  <col style={{ width: 140 }} />
                  <col style={{ width: 260 }} />
                  <col style={{ width: 92 }} />
                  <col style={{ width: 58 }} />
                  <col style={{ width: 62 }} />
                  <col style={{ width: 76 }} />
                  <col style={{ width: 76 }} />
                  <col style={{ width: 76 }} />
                  <col style={{ width: 92 }} />
                  <col style={{ width: 60 }} />
                  <col style={{ width: 70 }} />
                  <col style={{ width: 60 }} />
                </colgroup>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left' }}>Фото</th>
                    <th
                      className={`sr-sortable${sortBy === 'vendor_code' ? ' sr-active' : ''}`}
                      style={{ textAlign: 'left' }}
                      onClick={() => handleSort('vendor_code')}
                      title="Сортировать по артикулу"
                    >
                      Артикул / nmID
                      {sortBy === 'vendor_code' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable${sortBy === 'name' ? ' sr-active' : ''}`}
                      style={{ textAlign: 'left' }}
                      onClick={() => handleSort('name')}
                      title="Сортировать по названию"
                    >
                      Название
                      {sortBy === 'name' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable${sortBy === 'keywords' ? ' sr-active' : ''}`}
                      style={{ textAlign: 'left' }}
                      onClick={() => handleSort('keywords')}
                      title="Сортировать по наличию кэша ключевиков"
                    >
                      Ключевые слова
                      {sortBy === 'keywords' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'fbo_stock_qty' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('fbo_stock_qty')}
                      title="Сортировать по FBO остатку"
                    >
                      FBO
                      {sortBy === 'fbo_stock_qty' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'enterprise_stock_qty' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('enterprise_stock_qty')}
                      title="Сортировать по остатку склада предприятия"
                    >
                      Склад
                      {sortBy === 'enterprise_stock_qty' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'opens' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('opens')}
                      title="Сортировать по просмотрам"
                    >
                      Просмотры
                      {sortBy === 'opens' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'add_to_cart' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('add_to_cart')}
                      title="Сортировать по добавлениям в корзину"
                    >
                      В корзину
                      {sortBy === 'add_to_cart' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'conversion_to_order' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('conversion_to_order')}
                      title="Сортировать по конверсии в заказ"
                    >
                      Конв. в заказ
                      {sortBy === 'conversion_to_order' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'orders_sum' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('orders_sum')}
                      title="Сортировать по сумме заказов"
                    >
                      Сумма заказов
                      {sortBy === 'orders_sum' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'avgPos' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('avgPos')}
                      title="Сортировать по позиции"
                    >
                      avgPos
                      {sortBy === 'avgPos' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'visibility' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('visibility')}
                      title="Сортировать по visibility"
                    >
                      visibility
                      {sortBy === 'visibility' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                    <th
                      className={`sr-sortable sr-num${sortBy === 'orders' ? ' sr-active' : ''}`}
                      onClick={() => handleSort('orders')}
                      title="Сортировать по orders (search-report)"
                    >
                      orders
                      {sortBy === 'orders' && (
                        <span style={{ marginLeft: 4, fontSize: 10 }}>{sortOrder === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((p) => {
                    const avgPos = p.metrics?.avgPosition?.current ?? p.metrics?.avgPosition ?? null
                    const visibility = p.metrics?.visibility?.current ?? p.metrics?.visibility ?? null
                    const orders = p.metrics?.orders?.current ?? p.metrics?.orders ?? null
                    const wbUrl = `https://www.wildberries.ru/catalog/${p.nm_id}/detail.aspx`
                    return (
                      <tr key={p.nm_id}>
                        <td>
                          <PhotoPopover photos={p.photos || []} size={36} />
                        </td>
                        <td style={{ overflow: 'hidden' }}>
                          <div className="sr-article" title={p.vendor_code || undefined}>
                            {p.vendor_code || '—'}
                          </div>
                          <a
                            href={wbUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="sr-nm-link"
                            title="Открыть на WB"
                          >
                            {p.nm_id} <span style={{ fontSize: 10, marginLeft: 3 }}>↗</span>
                          </a>
                        </td>
                        <td style={{ overflow: 'hidden' }}>
                          <div className="sr-name" title={p.name || undefined}>
                            {p.name || '—'}
                          </div>
                          <div className="sr-subject" title={p.subject_name || undefined}>
                            {p.subject_name || '—'}
                          </div>
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={() => openKeywords(p.nm_id)}
                            style={{ margin: 0, padding: '6px 12px', fontSize: 12, borderRadius: 6 }}
                          >
                            Показать
                          </button>
                        </td>
                        <td className="sr-num">
                          {formatInt(p.fbo_stock_qty ?? null)}
                        </td>
                        <td className="sr-num">
                          {formatInt(p.enterprise_stock_qty ?? null)}
                        </td>
                        <td className="sr-num">
                          {formatInt(p.opens ?? null)}
                        </td>
                        <td className="sr-num">
                          {formatInt(p.add_to_cart ?? null)}
                        </td>
                        <td className="sr-num">
                          {formatPct(p.conversion_to_order ?? null)}
                        </td>
                        <td className="sr-num">
                          {formatRUB(p.orders_sum ?? null)}
                        </td>
                        <td className="sr-num">
                          {avgPos ?? ''}
                        </td>
                        <td className="sr-num">
                          {visibility ?? ''}
                        </td>
                        <td className="sr-num">
                          {orders ?? ''}
                        </td>
                      </tr>
                    )
                  })}
                  {products.length === 0 && (
                    <tr>
                      <td colSpan={13} style={{ padding: '12px 6px', color: '#777' }}>
                        Нет данных
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {keywordsOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            zIndex: 1000,
          }}
          onClick={() => setKeywordsOpen(false)}
        >
          <div
            className="card"
            style={{ width: 'min(900px, 95vw)', maxHeight: '85vh', overflow: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <h2 style={{ marginTop: 0, marginBottom: 0 }}>
                <span style={{ display: 'block' }}>Ключевые слова • nm_id {keywordsNmId ?? ''}</span>
                {selectedSnapshot ? (
                  <span style={{ display: 'block', fontSize: 12, opacity: 0.75, marginTop: 4 }}>
                    Отчет по ключевым словам #{selectedSnapshot.id} • {selectedSnapshot.period_from}…
                    {selectedSnapshot.period_to}
                  </span>
                ) : null}
                <span style={{ display: 'block', fontSize: 12, opacity: 0.75, marginTop: 2 }}>
                  Выбранный период: {dateFrom}…{dateTo}
                </span>
              </h2>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  disabled={keywordsLoading || !keywordsNmId}
                  onClick={() => keywordsNmId && openKeywords(keywordsNmId, true)}
                  title="Обновить и игнорировать кэш"
                >
                  Обновить
                </button>
                <button type="button" onClick={() => setKeywordsOpen(false)}>
                  Закрыть
                </button>
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, opacity: 0.8 }}>
                Важно: WB жёстко лимитирует Analytics API, поэтому загрузка может занимать 20+ секунд.
              </div>
              {keywordsRequestError ? (
                <div
                  style={{
                    marginTop: 10,
                    padding: 10,
                    borderRadius: 8,
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#b91c1c',
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  Ошибка запроса: {keywordsRequestError}
                </div>
              ) : null}
              {keywordsLoading ? (
                <div style={{ marginTop: 12 }}>Загрузка…</div>
              ) : (
                <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
                  {([
                    { key: 'orders', title: 'Top by orders', items: keywordsOrders, metric: 'orders' },
                    { key: 'openCard', title: 'Top by openCard', items: keywordsOpenCard, metric: 'openCard' },
                    { key: 'addToCart', title: 'Top by addToCart', items: keywordsAddToCart, metric: 'addToCart' },
                  ] as const).map((col) => (
                    <div key={col.key} style={{ border: '1px solid #eee', borderRadius: 8, overflow: 'hidden' }}>
                      <div style={{ padding: '10px 10px', background: '#f9fafb', borderBottom: '1px solid #eee' }}>
                        <div style={{ fontWeight: 600 }}>{col.title}</div>
                        {keywordsErrors[col.key] ? (
                          <div style={{ marginTop: 4, fontSize: 12, color: '#b91c1c' }}>
                            Ошибка: {String(keywordsErrors[col.key]?.error || '')}
                          </div>
                        ) : (
                          <div style={{ marginTop: 4, fontSize: 12, opacity: 0.75 }}>items: {col.items.length}</div>
                        )}
                      </div>
                      {col.items.length === 0 && !keywordsErrors[col.key] ? (
                        <div style={{ padding: 10, color: '#777' }}>Нет ключевых слов</div>
                      ) : (
                        <div style={{ maxHeight: 420, overflow: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                              <tr>
                                <th style={{ textAlign: 'left', borderBottom: '1px solid #eee', padding: '8px 6px' }}>
                                  keyword
                                </th>
                                <th style={{ textAlign: 'right', borderBottom: '1px solid #eee', padding: '8px 6px' }}>
                                  {col.metric}
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {col.items.map((it: any, idx: number) => {
                                const kw =
                                  it?.searchText ?? it?.text ?? it?.query ?? it?.keyword ?? it?.phrase ?? it?.name ?? ''
                                const metricVal = it?.[col.metric]?.current ?? it?.[col.metric] ?? ''
                                return (
                                  <tr key={`${col.key}-${kw}-${idx}`}>
                                    <td style={{ padding: '8px 6px', borderBottom: '1px solid #f3f3f3' }}>{kw}</td>
                                    <td
                                      style={{
                                        padding: '8px 6px',
                                        borderBottom: '1px solid #f3f3f3',
                                        textAlign: 'right',
                                      }}
                                    >
                                      {metricVal}
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
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
          display: flex;
          flex-direction: column;
        }
        .unitpnl-label {
          display: block;
          margin-bottom: 4px;
          font-size: 14px;
          line-height: 1.25;
          font-weight: 500;
          color: #374151;
        }
        .unitpnl-control {
          width: 100%;
          height: 40px;
          padding: 8px 12px;
          line-height: 20px;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          background: #fff;
          font-size: 14px;
        }
        .unitpnl-control::placeholder {
          color: #9ca3af;
        }
        .unitpnl-control:focus {
          outline: none;
          border-color: #3b82f6;
          box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
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
          display: flex;
          gap: 12px;
          align-items: end;
        }
        .unitpnl-actions--searchreport {
          flex-direction: column;
        }
        .unitpnl-actions--searchreport-snap {
          justify-content: flex-end;
        }
        .unitpnl-snapmeta {
          justify-content: flex-end;
        }
        @media (min-width: 768px) {
          .unitpnl-grid--searchreport-row1 {
            grid-template-columns: minmax(120px, 140px) minmax(120px, 140px) minmax(220px, 280px) minmax(
                220px,
                320px
              ) auto;
          }
          .unitpnl-actions--searchreport {
            flex-direction: row;
            justify-content: flex-end;
          }
          .unitpnl-btn {
            width: auto;
          }
          .unitpnl-grid--searchreport-snap {
            grid-template-columns: minmax(320px, 520px) 1fr auto;
          }
          .unitpnl-snapmeta {
            align-items: flex-start;
          }
        }
      `}</style>
    </div>
  )
}
