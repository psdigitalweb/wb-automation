'use client'

import React from 'react'
import type { WBUnitPnlRow } from '@/lib/apiClient'
import styles from './unit-pnl.module.css'

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
  packaging_cost_total?: number | null
  packaging_missing_count?: number | null
  additional_costs_total?: number | null
  warehouse_labor_costs_total?: number | null
  full_profit_total?: number | null
  full_margin_pct_of_revenue?: number | null
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

  return (
    <div className={styles.summaryGrid}>
      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>Продажи и выплаты</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Выручка (WB реализовал)" value={`${fmtRub(sale)} ₽`} />
          <SummaryPair label="К перечислению за товар" value={`${fmtRub(transferForGoods)} ₽`} />
          <SummaryPair label="Итого к оплате" value={`${fmtRub(totalToPay)} ₽`} accent />
        </div>
      </div>

      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>Затраты WB</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Затраты WB, ₽" value={fmtRub(wbTotalCost)} />
          <SummaryPair label="Затраты WB, % от выручки" value={`${formatPct(wbTotalCostPct)}%`} />
        </div>
      </div>

      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>Детализация затрат</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Логистика" value={fmtRub(logisticsCost)} />
          <SummaryPair label="Хранение" value={fmtRub(storageCost)} />
          <SummaryPair label="Приёмка" value={fmtRub(acceptanceCost)} />
          <SummaryPair label="Удержания" value={fmtRub(otherWithholdings)} />
          <SummaryPair label="Штрафы" value={fmtRub(penalties)} />
          <SummaryPair label="Лояльность (справочно)" value={fmtRub(loyaltyComp)} />
        </div>
      </div>

      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>Операции</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Доставки, шт" value={formatQty(deliveriesTotal)} />
          <SummaryPair label="Возвраты, шт" value={formatQty(returnsTotal)} />
          <SummaryPair label="Выкуп, %" value={`${formatPct(buyoutRateTotal)}%`} />
        </div>
      </div>

    </div>
  )
}

function SummaryPair({ label, value, accent = false }: { label: string; value: React.ReactNode; accent?: boolean }) {
  return (
    <div className={styles.summaryPair}>
      <span className={styles.summaryLabel}>{label}</span>
      <span className={`${styles.summaryValue} ${accent ? styles.summaryValueAccent : ''}`.trim()}>{value}</span>
    </div>
  )
}
