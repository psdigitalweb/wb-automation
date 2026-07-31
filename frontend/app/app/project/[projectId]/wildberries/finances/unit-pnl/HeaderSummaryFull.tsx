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
  commission_vv_signed?: number | null
  acquiring?: number | null
  wb_total_signed?: number | null
  wb_total_pct_of_revenue?: number | null
  total_to_pay?: number
  rrp_model?: RrpModel | null
  rrp_sales_model?: number | null
  wb_take_from_rrp?: number | null
  wb_take_pct_of_rrp?: number | null
  rrp_coverage_pct?: number | null
  rrp_net_units_covered?: number | null
  net_units_total?: number | null
  packaging_cost_total?: number | null
  cogs_cost_total?: number | null
  packaging_missing_count?: number | null
  additional_costs_total?: number | null
  warehouse_labor_costs_total?: number | null
  tax_model_code?: string | null
  tax_base?: number | null
  tax_vat_amount?: number | null
  tax_profit_amount?: number | null
  tax_expense_total?: number | null
  tax_rate?: number | null
  tax_vat_rate?: number | null
  full_profit_before_tax_total?: number | null
  full_profit_total?: number | null
  full_margin_pct_of_revenue?: number | null
}

interface HeaderSummaryProps {
  headerTotals: HeaderTotals
  items: WBUnitPnlRow[]
}

export function HeaderSummaryFull({ headerTotals }: HeaderSummaryProps) {

  const sale = headerTotals.sale ?? 0
  const transferForGoods = headerTotals.transfer_for_goods ?? 0
  const totalToPay = headerTotals.total_to_pay ?? 0
  const logisticsCost = headerTotals.logistics_cost ?? 0
  const storageCost = headerTotals.storage_cost ?? 0
  const acceptanceCost = headerTotals.acceptance_cost ?? 0
  const otherWithholdings = headerTotals.other_withholdings ?? 0
  const penalties = headerTotals.penalties ?? 0
  const loyaltyComp = headerTotals.loyalty_comp_display ?? 0
  const commissionVvSigned = headerTotals.commission_vv_signed ?? 0
  const acquiring = headerTotals.acquiring ?? 0

  const directWbCosts = logisticsCost + storageCost + acceptanceCost + otherWithholdings + penalties
  const wbTotalTake = headerTotals.wb_total_signed ?? (directWbCosts + commissionVvSigned + acquiring)
  const wbTotalTakePct =
    headerTotals.wb_total_pct_of_revenue ?? (sale > 0 ? (wbTotalTake / sale) * 100 : 0)
  const cogsTotal = headerTotals.cogs_cost_total ?? null
  const taxTotal = headerTotals.tax_expense_total ?? 0
  const warehouseLaborTotal = headerTotals.warehouse_labor_costs_total ?? 0
  const operationalExpensesTotal = headerTotals.additional_costs_total
  const fbsAndReturnsTotal =
    operationalExpensesTotal != null
      ? operationalExpensesTotal - warehouseLaborTotal
      : null

  return (
    <div className={styles.summaryGrid}>
      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>WB факт</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Выручка" value={`${fmtRub(sale)} ₽`} />
          <SummaryPair label="К перечислению за товар" value={`${fmtRub(transferForGoods)} ₽`} />
          <SummaryPair label="К оплате после затрат WB" value={`${fmtRub(totalToPay)} ₽`} accent />
          <SummaryPair label="WB забрал, ₽" value={`${fmtRub(wbTotalTake)} ₽`} />
          <SummaryPair label="WB забрал, % от выручки" value={`${formatPct(wbTotalTakePct)}%`} />
        </div>
      </div>

      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>Детализация расходов WB</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Комиссия WB" value={fmtRub(commissionVvSigned)} />
          <SummaryPair label="Эквайринг" value={fmtRub(acquiring)} />
          <SummaryPair label="Логистика" value={fmtRub(logisticsCost)} />
          <SummaryPair label="Хранение" value={fmtRub(storageCost)} />
          <SummaryPair label="Приёмка" value={fmtRub(acceptanceCost)} />
          <SummaryPair label="Удержания" value={fmtRub(otherWithholdings)} />
          <SummaryPair label="Штрафы" value={fmtRub(penalties)} />
          <SummaryPair label="Лояльность (справочно)" value={fmtRub(loyaltyComp)} />
        </div>
      </div>

      {(() => {
        const rrp = headerTotals.rrp_model
        const rrpSalesModel = rrp?.rrp_sales_model ?? headerTotals.rrp_sales_model
        const wbTookRub = rrp?.wb_took_from_rrp_rub ?? headerTotals.wb_take_from_rrp
        const wbTookPct = rrp?.wb_took_from_rrp_pct ?? headerTotals.wb_take_pct_of_rrp
        const coveragePct = rrp?.rrp_coverage_qty_pct ?? headerTotals.rrp_coverage_pct
        return (
          <div className={styles.summaryBlock} title={!(rrpSalesModel != null && rrpSalesModel > 0) ? 'Нет Internal Data / РРЦ не найдено' : undefined}>
            <div className={styles.summaryTitle}>Модель (РРЦ)</div>
            <div className={styles.summaryList}>
              <SummaryPair label="Продажи по РРЦ (модель)" value={rrpSalesModel != null && rrpSalesModel > 0 ? `${formatRUB(rrpSalesModel)} ₽` : '—'} />
              <SummaryPair label="Разница РРЦ к оплате" value={wbTookRub != null ? `${formatRUB(wbTookRub)} ₽` : '—'} />
              <SummaryPair label="Разница, % от РРЦ" value={wbTookPct != null ? `${formatPct(wbTookPct)}%` : '—'} />
              <SummaryPair label="Покрытие РРЦ" value={coveragePct != null ? `${formatPct(coveragePct)}%` : '—'} />
            </div>
          </div>
        )
      })()}

      <div className={styles.summaryBlock}>
        <div className={styles.summaryTitle}>P&L</div>
        <div className={styles.summaryList}>
          <SummaryPair label="Выручка" value={`${fmtRub(sale)} ₽`} />
          <SummaryPair label="Затраты WB" value={`${fmtRub(wbTotalTake)} ₽`} />
          <SummaryPair label="Себестоимость" value={`${fmtRub(cogsTotal)} ₽`} />
          <SummaryPair label="Упаковка" value={`${fmtRub(headerTotals.packaging_cost_total)} ₽`} />
          <SummaryPair label="Логистика" value={`${fmtRub(fbsAndReturnsTotal)} ₽`} />
          <SummaryPair label="ФОТ" value={`${fmtRub(warehouseLaborTotal)} ₽`} />
          <SummaryPair label="Налоги" value={`${fmtRub(taxTotal)} ₽`} />
          <SummaryPair label="Прибыль, руб" value={`${fmtRub(headerTotals.full_profit_total)} ₽`} accent />
          <SummaryPair
            label="Прибыль, %"
            value={
              headerTotals.full_margin_pct_of_revenue != null
                ? `${formatPct(headerTotals.full_margin_pct_of_revenue)}%`
                : '—'
            }
          />
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
