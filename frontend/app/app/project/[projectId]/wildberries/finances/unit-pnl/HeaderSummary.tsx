'use client'

import React from 'react'
import type { WBUnitPnlRow } from '@/lib/apiClient'

function formatRUB(value: number, fractionDigits: number = 2): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    useGrouping: true,
  }).format(value)
}

function formatPct(value: number): string {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
}

function formatQty(value: number): string {
  return new Intl.NumberFormat('ru-RU', { useGrouping: true }).format(Math.round(value))
}

function fmtRub(value: number | null | undefined): string {
  if (value == null) return '—'
  return formatRUB(value)
}

interface RrpModel {
  rrp_sales_model?: number | null
  wb_took_from_rrp_rub?: number | null
  wb_took_from_rrp_pct?: number | null
  rrp_coverage_qty_pct?: number | null
}

interface HeaderTotals {
  lines_total?: number
  skus_total?: number
  rows_total?: number
  sale?: number
  transfer_for_goods?: number
  logistics_cost?: number
  storage_cost?: number
  acceptance_cost?: number
  other_withholdings?: number
  penalties?: number
  loyalty_comp_display?: number
  total_to_pay?: number
  rrp_model?: RrpModel | null
  rrp_sales_model?: number | null
  wb_take_from_rrp?: number | null
  wb_take_pct_of_rrp?: number | null
  rrp_coverage_pct?: number | null
  rrp_net_units_covered?: number | null
  net_units_total?: number | null
}

interface HeaderSummaryProps {
  headerTotals: HeaderTotals
  items: WBUnitPnlRow[]
}

export function HeaderSummary({ headerTotals, items }: HeaderSummaryProps) {

  const sale = headerTotals.sale ?? 0
  const transferForGoods = headerTotals.transfer_for_goods ?? 0
  const totalToPay = headerTotals.total_to_pay ?? 0
  const logisticsCost = headerTotals.logistics_cost ?? 0
  const storageCost = headerTotals.storage_cost ?? 0
  const acceptanceCost = headerTotals.acceptance_cost ?? 0
  const otherWithholdings = headerTotals.other_withholdings ?? 0
  const penalties = headerTotals.penalties ?? 0
  const loyaltyComp = headerTotals.loyalty_comp_display ?? 0

  const wbTotalCost = logisticsCost + storageCost + acceptanceCost + otherWithholdings + penalties
  const wbTotalCostPct = sale > 0 ? (wbTotalCost / sale) * 100 : 0

  const deliveriesTotal = items.reduce((sum, r) => sum + (r.deliveries_qty ?? 0), 0)
  const returnsTotal = items.reduce((sum, r) => sum + (r.returns_log_qty ?? 0), 0)
  const buyoutRateTotal =
    deliveriesTotal > 0 ? ((deliveriesTotal - returnsTotal) / deliveriesTotal) * 100 : 0

  const blockStyle: React.CSSProperties = {
    padding: 12,
    borderRadius: 6,
    backgroundColor: '#f8f9fa',
    minWidth: 0,
  }

  const labelStyle: React.CSSProperties = { fontSize: 12, color: '#666', marginBottom: 2 }
  const valueStyle: React.CSSProperties = { fontWeight: 600, fontSize: 15 }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: 16,
        fontSize: 13,
      }}
    >
      {/* A) Продажи и выплаты */}
      <div style={{ ...blockStyle }}>
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Продажи и выплаты</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div>
            <div style={labelStyle}>Выручка (WB реализовал)</div>
            <div style={valueStyle}>{fmtRub(sale)} ₽</div>
          </div>
          <div>
            <div style={labelStyle}>К перечислению за товар</div>
            <div style={valueStyle}>{fmtRub(transferForGoods)} ₽</div>
          </div>
          <div>
            <div style={labelStyle}>Итого к оплате</div>
            <div style={{ ...valueStyle, color: '#0d6efd' }}>{fmtRub(totalToPay)} ₽</div>
          </div>
        </div>
      </div>

      {/* B) Затраты WB */}
      <div style={{ ...blockStyle }}>
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Затраты WB</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div>
            <div style={labelStyle}>Затраты WB, ₽</div>
            <div style={valueStyle}>{fmtRub(wbTotalCost)}</div>
          </div>
          <div>
            <div style={labelStyle}>Затраты WB, % от выручки</div>
            <div style={valueStyle}>{formatPct(wbTotalCostPct)}%</div>
          </div>
        </div>
      </div>

      {/* C) Детализация затрат */}
      <div style={{ ...blockStyle }}>
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Детализация затрат</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={labelStyle}>Логистика</span>
              <span>{fmtRub(logisticsCost)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={labelStyle}>Хранение</span>
              <span>{fmtRub(storageCost)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={labelStyle}>Приёмка</span>
              <span>{fmtRub(acceptanceCost)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={labelStyle}>Удержания</span>
              <span>{fmtRub(otherWithholdings)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={labelStyle}>Штрафы</span>
              <span>{fmtRub(penalties)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ ...labelStyle, fontStyle: 'italic' }}>Лояльность (справочно)</span>
              <span>{fmtRub(loyaltyComp)}</span>
            </div>
        </div>
      </div>

      {/* D) Модель (РРЦ) — из backend header_totals.rrp_model */}
      {(() => {
        const rrp = headerTotals.rrp_model
        const rrpSalesModel = rrp?.rrp_sales_model ?? headerTotals.rrp_sales_model
        const wbTookRub = rrp?.wb_took_from_rrp_rub ?? headerTotals.wb_take_from_rrp
        const wbTookPct = rrp?.wb_took_from_rrp_pct ?? headerTotals.wb_take_pct_of_rrp
        const coveragePct = rrp?.rrp_coverage_qty_pct ?? headerTotals.rrp_coverage_pct
        return (
          <div style={{ ...blockStyle }} title={!(rrpSalesModel != null && rrpSalesModel > 0) ? 'Нет Internal Data / РРЦ не найдено' : undefined}>
            <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Модель (РРЦ)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div>
                <div style={labelStyle}>Продажи по РРЦ (модель)</div>
                <div style={valueStyle}>
                  {rrpSalesModel != null && rrpSalesModel > 0 ? `${formatRUB(rrpSalesModel)} ₽` : '—'}
                </div>
              </div>
              <div>
                <div style={labelStyle}>WB забрал от РРЦ, ₽</div>
                <div style={valueStyle}>{wbTookRub != null ? `${formatRUB(wbTookRub)} ₽` : '—'}</div>
              </div>
              <div>
                <div style={labelStyle}>WB забрал от РРЦ, %</div>
                <div style={valueStyle}>{wbTookPct != null ? `${formatPct(wbTookPct)}%` : '—'}</div>
              </div>
              <div>
                <div style={labelStyle}>Покрытие РРЦ</div>
                <div style={valueStyle}>{coveragePct != null ? `${formatPct(coveragePct)}%` : '—'}</div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* E) Операции */}
      <div style={{ ...blockStyle }}>
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#333' }}>Операции</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div>
            <div style={labelStyle}>Доставки, шт</div>
            <div style={valueStyle}>{formatQty(deliveriesTotal)}</div>
          </div>
          <div>
            <div style={labelStyle}>Возвраты, шт</div>
            <div style={valueStyle}>{formatQty(returnsTotal)}</div>
          </div>
          <div>
            <div style={labelStyle}>Выкуп, %</div>
            <div style={valueStyle}>{formatPct(buyoutRateTotal)}%</div>
          </div>
        </div>
      </div>
    </div>
  )
}
