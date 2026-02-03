'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  getWBSkuPnl,
  getWBProductSubjects,
  buildWBSkuPnl,
  type WBSkuPnlItem,
  type WBProductSubjectItem,
  type ApiError,
} from '@/lib/apiClient'
import s from '../../../cogs/cogs.module.css'

function formatRUB(value: number, fractionDigits: number = 2): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    useGrouping: true,
  }).format(value)
}

function formatQty(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    useGrouping: true,
  }).format(value)
}

function formatInt(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)
}

function getDefaultPeriod(): { from: string; to: string } {
  const today = new Date()
  const first = new Date(today.getFullYear(), today.getMonth(), 1)
  return {
    from: first.toISOString().slice(0, 10),
    to: today.toISOString().slice(0, 10),
  }
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

function formatPct(value: number): string {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}

function logisticsTotal(row: WBSkuPnlItem) {
  return (row.delivery_fee ?? 0) + (row.rebill_logistics_cost ?? 0) + (row.pvz_fee ?? 0)
}

function wbTotalTotal(row: WBSkuPnlItem) {
  // Backend provides normalized WB total (ABS-sum). No recompute here.
  return row.wb_total_total ?? 0
}

function safeDiv(n: number, d: number): number | null {
  if (!d || d === 0) return null
  return n / d
}

interface DetailsSectionProps {
  title: string
  items: Array<{ label: string; value: number }>
}

function DetailsSection({ title, items }: DetailsSectionProps) {
  const nonZero = items.filter((it) => Math.abs(it.value) > 0.001)
  if (nonZero.length === 0) return null
  return (
    <div style={{ marginBottom: '12px' }}>
      <h4 style={{ margin: '0 0 8px 0', fontSize: '13px', fontWeight: 600, color: '#555' }}>
        {title}
      </h4>
      <div style={{ display: 'grid', gap: '4px', fontSize: '13px' }}>
        {nonZero.map((it) => (
          <div
            key={it.label}
            style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}
          >
            <span style={{ color: '#666' }}>{it.label}</span>
            <span style={{ fontFamily: 'ui-monospace, monospace', textAlign: 'right' }}>
              {formatRUB(it.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function WBSkuPnlPage() {
  const params = useParams()
  const projectId = params.projectId as string

  const defaultPeriod = useMemo(getDefaultPeriod, [])
  const [periodFrom, setPeriodFrom] = useState(defaultPeriod.from)
  const [periodTo, setPeriodTo] = useState(defaultPeriod.to)
  const [search, setSearch] = useState('')
  const [version, setVersion] = useState(1)
  const [sort, setSort] = useState<
    'net_before_cogs' | 'net_before_cogs_pct' | 'wb_total_pct' | 'internal_sku'
  >('net_before_cogs')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<WBSkuPnlItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [buildLoading, setBuildLoading] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [hoverSku, setHoverSku] = useState<string | null>(null)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [subjects, setSubjects] = useState<WBProductSubjectItem[]>([])
  const [subjectsLoading, setSubjectsLoading] = useState(false)
  const [subjectId, setSubjectId] = useState<number | null>(null)

  const searchDebounced = useDebounce(search.trim(), 350)

  const loadSubjects = useCallback(async () => {
    try {
      setSubjectsLoading(true)
      const list = await getWBProductSubjects(projectId)
      setSubjects(list)
    } catch (e) {
      setSubjects([])
    } finally {
      setSubjectsLoading(false)
    }
  }, [projectId])

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getWBSkuPnl(projectId, {
        period_from: periodFrom,
        period_to: periodTo,
        version,
        q: searchDebounced || undefined,
        subject_id: subjectId ?? undefined,
        sort,
        order,
        limit,
        offset,
      })
      setItems(data.items)
      setTotalCount(data.total_count)
    } catch (e) {
      const err = e as ApiError
      setError(err?.detail || 'Не удалось загрузить данные')
      setItems([])
      setTotalCount(0)
    } finally {
      setLoading(false)
    }
  }, [
    projectId,
    periodFrom,
    periodTo,
    version,
    searchDebounced,
    subjectId,
    sort,
    order,
    limit,
    offset,
  ])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    // default collapsed sources for each row expansion
    setSourcesOpen(false)
  }, [expandedRow])

  useEffect(() => {
    loadSubjects()
  }, [loadSubjects])

  const handlePeriodChange = () => {
    setOffset(0)
  }

  const handleSearchChange = (v: string) => {
    setSearch(v)
    setOffset(0)
  }

  const handleBuild = async () => {
    setBuildLoading(true)
    setError(null)
    try {
      await buildWBSkuPnl(projectId, {
        period_from: periodFrom,
        period_to: periodTo,
        version,
        rebuild: true,
        ensure_events: true,
      })
      setToast('Сбор запущен. Обновите через минуту.')
      setTimeout(() => setToast(null), 5000)
    } catch (e) {
      const err = e as ApiError
      setError(err?.detail || 'Не удалось запустить сбор')
    } finally {
      setBuildLoading(false)
    }
  }

  // logisticsTotal/wbTotal helpers are defined above

  return (
    <div className={[s.root, 'container'].join(' ')}>
      <h1>PnL по SKU (Wildberries)</h1>
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <Link href={`/app/project/${projectId}/wildberries/finances/reports`} className={s.linkAsButton}>
          ← Финансовые отчёты
        </Link>
        <Link href={`/app/project/${projectId}/settings`} className={s.linkAsButton}>
          Настройки
        </Link>
      </div>

      {toast && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '16px',
            backgroundColor: '#d4edda',
            color: '#155724',
            borderRadius: 6,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{toast}</span>
          <button
            type="button"
            onClick={() => {
              setToast(null)
              fetchData()
            }}
            className={s.button}
          >
            Обновить
          </button>
        </div>
      )}

      {error && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '16px',
            backgroundColor: '#f8d7da',
            color: '#721c24',
            borderRadius: 6,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <span>{error}</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" onClick={fetchData} className={s.button}>
              Повторить
            </button>
            <button type="button" onClick={() => setError(null)} className={s.buttonSecondary}>
              Скрыть
            </button>
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ padding: '16px 20px' }}>
          <h2 style={{ marginTop: 0, marginBottom: '16px' }}>Фильтры</h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              gap: '12px',
              alignItems: 'end',
              flexWrap: 'wrap',
            }}
          >
            <div className={s.field}>
              <span className={s.fieldLabel}>Период с</span>
              <input
                type="date"
                value={periodFrom}
                onChange={(e) => {
                  setPeriodFrom(e.target.value)
                  handlePeriodChange()
                }}
                className={s.inputDate}
              />
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Период по</span>
              <input
                type="date"
                value={periodTo}
                onChange={(e) => {
                  setPeriodTo(e.target.value)
                  handlePeriodChange()
                }}
                className={s.inputDate}
              />
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Поиск SKU</span>
              <input
                type="text"
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Артикул"
                className={s.inputText}
              />
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Категория WB</span>
              <select
                value={subjectId ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  setSubjectId(v ? Number(v) : null)
                  setOffset(0)
                }}
                className={s.select}
                disabled={subjectsLoading}
              >
                <option value="">{subjectsLoading ? 'Загрузка…' : 'Все'}</option>
                {subjects.map((x) => (
                  <option key={x.subject_id} value={x.subject_id}>
                    {x.subject_name}
                  </option>
                ))}
              </select>
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Версия</span>
              <select
                value={version}
                onChange={(e) => {
                  setVersion(Number(e.target.value))
                  setOffset(0)
                }}
                className={s.select}
              >
                <option value={1}>1</option>
              </select>
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Сортировка</span>
              <select
                value={sort}
                onChange={(e) =>
                  setSort(
                    e.target.value as 'net_before_cogs' | 'net_before_cogs_pct' | 'wb_total_pct' | 'internal_sku'
                  )
                }
                className={s.select}
              >
                <option value="net_before_cogs">Доход до себест.</option>
                <option value="net_before_cogs_pct">% Доход до себест.</option>
                <option value="wb_total_pct">% WB итого</option>
                <option value="internal_sku">SKU</option>
              </select>
            </div>
            <div className={s.field}>
              <span className={s.fieldLabel}>Порядок</span>
              <select value={order} onChange={(e) => setOrder(e.target.value as 'asc' | 'desc')} className={s.select}>
                <option value="desc">По убыванию</option>
                <option value="asc">По возрастанию</option>
              </select>
            </div>
            <div>
              <button onClick={fetchData} disabled={loading} className={s.button}>
                {loading ? 'Загрузка…' : 'Применить'}
              </button>
            </div>
            <div>
              <button
                onClick={handleBuild}
                disabled={buildLoading}
                className={s.buttonSecondary}
              >
                {buildLoading ? 'Запуск…' : 'Собрать срез'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
            <p>Загрузка…</p>
            <div
              style={{
                marginTop: 16,
                height: 4,
                background: '#eee',
                borderRadius: 2,
              }}
            />
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
            <p>Нет данных за период. Нажмите «Собрать срез» или измените фильтр.</p>
            <button onClick={handleBuild} disabled={buildLoading} className={s.button} style={{ marginTop: 16 }}>
              Собрать срез
            </button>
          </div>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #dee2e6' }}>
                    <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>SKU</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Продано, шт</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>РРЦ</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Цена WB</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Ср. цена</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Выручка</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Доход до себест.</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>COGS</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Profit</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>Margin %</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>% Доход до себест.</th>
                    <th style={{ padding: '12px', textAlign: 'right', fontWeight: 600 }}>% WB итого</th>
                    <th style={{ padding: '12px', width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row, idx) => {
                    const revenue = row.gmv ?? 0
                    const soldQty = row.quantity_sold ?? 0
                    const avgSalePrice = row.avg_price_realization_unit ?? (soldQty > 0 ? safeDiv(revenue, soldQty) : null)
                    const avgSalePriceRounded = avgSalePrice == null ? null : Math.round(avgSalePrice)
                    const wbPriceRounded = row.wb_price_admin == null ? null : Math.round(row.wb_price_admin)
                    const netPct = row.net_before_cogs_pct
                    const wbPct = row.wb_total_pct
                    const cogsMissing = row.cogs_missing ?? row.cogs_total == null
                    const marginPct = row.product_margin_pct
                    const marginPctUnit = row.margin_pct_unit
                    const profitPctOfRrpUnit = row.profit_pct_rrp ?? row.profit_pct_of_rrp_unit
                    const productImageUrl = row.product_image_url || row.product_image || null
                    return (
                      <React.Fragment key={row.internal_sku}>
                        <tr
                          style={{
                            borderBottom: '1px solid #eee',
                            backgroundColor: idx % 2 === 0 ? '#fff' : '#f8f9fa',
                          }}
                        >
                          <td
                            style={{
                              padding: '12px',
                              fontFamily: 'ui-monospace, monospace',
                              fontSize: '13px',
                            }}
                          >
                            {row.internal_sku}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {formatQty(row.quantity_sold)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {row.rrp_price == null ? '—' : formatRUB(row.rrp_price)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {row.wb_price_admin == null ? '—' : formatRUB(row.wb_price_admin)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {avgSalePrice == null ? '—' : formatRUB(Math.round(avgSalePrice), 0)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>{formatRUB(revenue)}</td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                            {formatRUB(row.net_before_cogs)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {cogsMissing ? (
                              <span title="COGS missing" style={{ color: '#6b7280' }}>
                                — <span style={{ fontSize: 12, borderBottom: '1px dotted #6b7280' }}>i</span>
                              </span>
                            ) : (
                              formatRUB(row.cogs_total ?? 0)
                            )}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right', fontWeight: 700 }}>
                            {cogsMissing ? '—' : formatRUB(row.product_profit ?? 0)}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            {cogsMissing || marginPct == null ? (
                              '—'
                            ) : (
                              <span style={{ fontWeight: 700, color: marginPct < 0 ? '#b91c1c' : '#1f2937' }}>
                                {`${formatPct(marginPct)}%`}
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            <span style={{ fontWeight: 700, color: '#1f2937' }}>
                              {netPct == null ? '—' : `${formatPct(netPct)}%`}
                            </span>
                          </td>
                          <td style={{ padding: '12px', textAlign: 'right' }}>
                            <span style={{ color: '#4b5563' }}>
                              {wbPct == null ? '—' : `${formatPct(wbPct)}%`}
                            </span>
                          </td>
                          <td style={{ padding: '12px', textAlign: 'center' }}>
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedRow(expandedRow === row.internal_sku ? null : row.internal_sku)
                              }
                              style={{
                                border: 'none',
                                background: 'transparent',
                                cursor: 'pointer',
                                padding: '4px',
                                fontSize: '16px',
                                color: '#666',
                              }}
                              title={expandedRow === row.internal_sku ? 'Свернуть' : 'Развернуть детали'}
                            >
                              {expandedRow === row.internal_sku ? '▲' : '▼'}
                            </button>
                          </td>
                        </tr>
                        {expandedRow === row.internal_sku && (
                          <tr style={{ borderBottom: '1px solid #eee', backgroundColor: '#f8fafc' }}>
                            <td colSpan={13} style={{ padding: '16px 20px' }}>
                              <div
                                style={{
                                  display: 'grid',
                                  gridTemplateColumns: 'repeat(2, minmax(300px, 1fr))',
                                  gap: '24px',
                                }}
                              >
                                {/* HEADER: идентификация товара */}
                                <div style={{ gridColumn: '1 / -1' }}>
                                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                                    <div
                                      style={{ position: 'relative', width: 72, height: 72, flex: '0 0 auto' }}
                                      onMouseEnter={() => setHoverSku(row.internal_sku)}
                                      onMouseLeave={() => setHoverSku((cur) => (cur === row.internal_sku ? null : cur))}
                                    >
                                      <div
                                        style={{
                                          width: 72,
                                          height: 72,
                                          borderRadius: 8,
                                          background: '#eee',
                                        }}
                                      />
                                      {productImageUrl ? (
                                        <img
                                          src={productImageUrl}
                                          alt={row.product_name || row.internal_sku}
                                          width={72}
                                          height={72}
                                          loading="lazy"
                                          style={{
                                            position: 'absolute',
                                            inset: 0,
                                            width: 72,
                                            height: 72,
                                            objectFit: 'cover',
                                            borderRadius: 8,
                                            display: 'block',
                                          }}
                                          onError={(e) => {
                                            ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                                          }}
                                        />
                                      ) : null}
                                      {productImageUrl && hoverSku === row.internal_sku ? (
                                        <div
                                          style={{
                                            position: 'absolute',
                                            zIndex: 50,
                                            top: 0,
                                            left: 84,
                                            width: 280,
                                            height: 280,
                                            background: '#fff',
                                            border: '1px solid #e5e7eb',
                                            borderRadius: 10,
                                            boxShadow: '0 12px 28px rgba(0,0,0,0.18)',
                                            overflow: 'hidden',
                                            pointerEvents: 'none',
                                          }}
                                        >
                                          <img
                                            src={productImageUrl}
                                            alt={row.product_name || row.internal_sku}
                                            width={280}
                                            height={280}
                                            style={{ width: 280, height: 280, objectFit: 'cover', display: 'block' }}
                                          />
                                        </div>
                                      ) : null}
                                    </div>
                                    <div style={{ minWidth: 0 }}>
                                      <div
                                        style={{
                                          fontWeight: 700,
                                          color: '#111827',
                                          fontSize: '14px',
                                          lineHeight: 1.3,
                                          wordBreak: 'break-word',
                                        }}
                                      >
                                        {row.product_name || '—'}
                                      </div>
                                      <div
                                        style={{
                                          marginTop: 2,
                                          fontSize: '12px',
                                          color: '#6b7280',
                                          fontFamily: 'ui-monospace, monospace',
                                        }}
                                      >
                                        {row.internal_sku}
                                      </div>
                                      {row.wb_category ? (
                                        <div style={{ marginTop: 2, fontSize: '12px', color: '#9ca3af' }}>
                                          {row.wb_category}
                                        </div>
                                      ) : null}
                                    </div>
                                  </div>
                                </div>

                                {/* Блок: Цены и база расчётов */}
                                <div>
                                  <h3
                                    style={{
                                      margin: '0 0 12px 0',
                                      fontSize: '14px',
                                      fontWeight: 600,
                                      color: '#333',
                                    }}
                                  >
                                    Цены и база расчётов
                                  </h3>
                                  <div style={{ display: 'grid', gap: '6px', fontSize: '13px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>РРЦ</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {row.rrp_price == null ? '—' : formatRUB(row.rrp_price)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Цена WB</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {wbPriceRounded == null ? '—' : formatRUB(wbPriceRounded, 0)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Средняя цена реализации</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {avgSalePriceRounded == null ? '—' : formatRUB(avgSalePriceRounded, 0)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Средний СПП, %</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {(() => {
                                          if (wbPriceRounded == null) return '—'
                                          if (avgSalePriceRounded == null) return '—'
                                          const v = safeDiv(wbPriceRounded - avgSalePriceRounded, wbPriceRounded)
                                          return v == null ? '—' : `${formatPct(v * 100)}%`
                                        })()}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Δ ср.цены к РРЦ, %</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {(() => {
                                          if (avgSalePriceRounded == null) return '—'
                                          if (row.rrp_price == null) return '—'
                                          const v = safeDiv(avgSalePriceRounded - row.rrp_price, row.rrp_price)
                                          return v == null ? '—' : `${formatPct(v * 100)}%`
                                        })()}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                <div>
                                  <h3
                                    style={{
                                      margin: '0 0 12px 0',
                                      fontSize: '14px',
                                      fontWeight: 600,
                                      color: '#333',
                                    }}
                                  >
                                    Расходы WB — абсолюты
                                  </h3>
                                  <DetailsSection
                                    title="WB"
                                    items={[
                                      { label: 'Комиссия WB', value: row.wb_commission_total ?? 0 },
                                      { label: 'Логистика', value: logisticsTotal(row) },
                                      { label: 'Эквайринг', value: row.acquiring_fee ?? 0 },
                                      { label: 'WB итого', value: wbTotalTotal(row) },
                                    ]}
                                  />
                                </div>

                                <div>
                                  <h3
                                    style={{
                                      margin: '0 0 12px 0',
                                      fontSize: '14px',
                                      fontWeight: 600,
                                      color: '#333',
                                    }}
                                  >
                                    Расходы WB — на единицу
                                  </h3>
                                  {soldQty > 0 ? (
                                    <DetailsSection
                                      title="WB"
                                      items={[
                                        { label: 'Комиссия WB / шт', value: (row.wb_commission_total ?? 0) / soldQty },
                                        { label: 'Логистика / шт', value: logisticsTotal(row) / soldQty },
                                        { label: 'Эквайринг / шт', value: (row.acquiring_fee ?? 0) / soldQty },
                                        { label: 'WB итого / шт', value: row.wb_total_unit ?? wbTotalTotal(row) / soldQty },
                                      ]}
                                    />
                                  ) : (
                                    <div style={{ color: '#666', fontSize: '13px' }}>Нет продаж (sold_qty = 0)</div>
                                  )}
                                </div>

                                <div>
                                  <h3
                                    style={{
                                      margin: '0 0 12px 0',
                                      fontSize: '14px',
                                      fontWeight: 600,
                                      color: '#333',
                                    }}
                                  >
                                    COGS / прибыль — на единицу
                                  </h3>
                                  <div style={{ display: 'grid', gap: '6px', fontSize: '13px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>COGS / шт</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {row.cogs_per_unit == null ? '—' : formatRUB(row.cogs_per_unit)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Profit / шт</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {row.profit_unit == null && row.profit_per_unit == null
                                          ? '—'
                                          : formatRUB((row.profit_unit ?? row.profit_per_unit) as number)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Margin % (от выручки, unit)</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {marginPctUnit == null ? '—' : `${formatPct(marginPctUnit)}%`}
                                      </span>
                                    </div>
                                    {profitPctOfRrpUnit != null ? (
                                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                        <span style={{ color: '#666' }}>Profit / шт, % от РРЦ</span>
                                        <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                          {`${formatPct(profitPctOfRrpUnit)}%`}
                                        </span>
                                      </div>
                                    ) : null}
                                  </div>
                                </div>

                                <div>
                                  <h3
                                    style={{
                                      margin: '0 0 12px 0',
                                      fontSize: '14px',
                                      fontWeight: 600,
                                      color: '#333',
                                    }}
                                  >
                                    % от РРЦ (не от выручки)
                                  </h3>
                                  {row.rrp_price != null && soldQty > 0 ? (
                                    <div style={{ fontSize: '13px', color: '#444' }}>
                                      <div style={{ display: 'grid', gap: '6px' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                          <span style={{ color: '#666' }}>Доход до себест., % от РРЦ</span>
                                          <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                            {row.income_before_cogs_pct_rrp == null
                                              ? '—'
                                              : `${formatPct(row.income_before_cogs_pct_rrp)}%`}
                                          </span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                          <span style={{ color: '#666' }}>WB итого, % от РРЦ</span>
                                          <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                            {row.wb_total_pct_rrp == null ? '—' : `${formatPct(row.wb_total_pct_rrp)}%`}
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                  ) : (
                                    <div style={{ color: '#666', fontSize: '13px' }}>Нет РРЦ или продаж для расчёта</div>
                                  )}
                                </div>

                                <div>
                                  <h3
                                    style={{
                                      margin: '0 0 12px 0',
                                      fontSize: '14px',
                                      fontWeight: 600,
                                      color: '#333',
                                    }}
                                  >
                                    Доставка / возвраты
                                  </h3>
                                  <div style={{ display: 'grid', gap: '6px', fontSize: '13px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Поездок до покупателя (delivery_rub)</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {formatInt(row.trips_cnt ?? 0)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>Возвраты (строки)</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {formatInt(row.returns_cnt ?? 0)}
                                      </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                                      <span style={{ color: '#666' }}>% выкупа (от поездок)</span>
                                      <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                                        {row.buyout_pct == null ? '—' : `${formatPct(row.buyout_pct)}%`}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                {/* Секция: Источники данных (WB) */}
                                {(row.sources?.length ?? 0) > 0 && (
                                  <div style={{ gridColumn: '1 / -1', marginTop: '8px' }}>
                                    <button
                                      type="button"
                                      onClick={() => setSourcesOpen((v) => !v)}
                                      style={{
                                        border: 'none',
                                        background: 'transparent',
                                        padding: 0,
                                        cursor: 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 8,
                                        margin: '0 0 12px 0',
                                      }}
                                      title={sourcesOpen ? 'Свернуть' : 'Развернуть'}
                                    >
                                      <span
                                        style={{
                                          fontSize: '14px',
                                          fontWeight: 600,
                                          color: '#333',
                                        }}
                                      >
                                        Источники данных (WB)
                                      </span>
                                      <span style={{ color: '#6b7280', fontSize: '13px' }}>
                                        ({row.sources!.length})
                                      </span>
                                      <span style={{ color: '#6b7280', fontSize: '14px' }}>
                                        {sourcesOpen ? '▲' : '▼'}
                                      </span>
                                    </button>

                                    {sourcesOpen ? (
                                      <>
                                        <table
                                          style={{
                                            width: '100%',
                                            borderCollapse: 'collapse',
                                            fontSize: '13px',
                                          }}
                                        >
                                          <thead>
                                            <tr style={{ borderBottom: '1px solid #dee2e6' }}>
                                              <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>
                                                ID / номер отчёта
                                              </th>
                                              <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>
                                                Тип отчёта
                                              </th>
                                              <th style={{ padding: '8px', textAlign: 'left', fontWeight: 600 }}>
                                                Период отчёта
                                              </th>
                                              <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>
                                                Строк
                                              </th>
                                              <th style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>
                                                Сумма
                                              </th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {row.sources!.map((src) => (
                                              <tr key={src.report_id} style={{ borderBottom: '1px solid #eee' }}>
                                                <td style={{ padding: '8px', fontFamily: 'ui-monospace, monospace' }}>
                                                  {src.report_id}
                                                </td>
                                                <td style={{ padding: '8px' }}>{src.report_type}</td>
                                                <td style={{ padding: '8px' }}>
                                                  {src.report_period_from && src.report_period_to
                                                    ? `${new Date(src.report_period_from).toLocaleDateString('ru-RU')} — ${new Date(src.report_period_to).toLocaleDateString('ru-RU')}`
                                                    : '—'}
                                                </td>
                                                <td style={{ padding: '8px', textAlign: 'right' }}>
                                                  {formatQty(src.rows_count)}
                                                </td>
                                                <td
                                                  style={{
                                                    padding: '8px',
                                                    textAlign: 'right',
                                                    fontFamily: 'ui-monospace, monospace',
                                                  }}
                                                >
                                                  {formatRUB(src.amount_total)}
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                        <div
                                          style={{
                                            marginTop: '8px',
                                            padding: '8px 0',
                                            borderTop: '1px solid #dee2e6',
                                            display: 'flex',
                                            justifyContent: 'flex-end',
                                            fontWeight: 600,
                                            fontSize: '13px',
                                          }}
                                        >
                                          Итого по SKU:{' '}
                                          {formatRUB(row.sources!.reduce((sum, s) => sum + s.amount_total, 0))}
                                        </div>
                                      </>
                                    ) : null}
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div
              style={{
                marginTop: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span className={s.fieldLabel}>Строк на странице:</span>
                <select
                  value={limit}
                  onChange={(e) => {
                    setLimit(Number(e.target.value))
                    setOffset(0)
                  }}
                  className={s.select}
                >
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
              </div>
              <div className={s.paginationWrap}>
                <span style={{ marginRight: '12px' }}>
                  {offset + 1}–{Math.min(offset + limit, totalCount)} из {totalCount}
                </span>
                <button
                  type="button"
                  className={s.paginationBtn}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                >
                  Назад
                </button>
                <button
                  type="button"
                  className={s.paginationBtn}
                  onClick={() => setOffset(offset + limit)}
                  disabled={offset + limit >= totalCount}
                >
                  Вперёд
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
