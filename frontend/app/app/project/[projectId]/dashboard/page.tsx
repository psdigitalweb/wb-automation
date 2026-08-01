'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { apiGet, getWBFinanceReportsLatest } from '../../../../../lib/apiClient'
import type { ApiError, WBFinanceReportLatest } from '../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../hooks/usePageTitle'
import styles from './dashboard.module.css'

interface Kpis {
  wb: {
    products_total: number
    warehouses_fbs_total: number
  }
  stock: {
    fbs_in_stock_products: number
    fbo_in_stock_products: number
  }
  prices: {
    wb_prices_products: number
  }
  storefront: {
    storefront_products: number
    expected_storefront_products: number
  }
  rrp_xml: {
    total: number
    with_price: number
    with_stock: number
    with_price_and_stock: number
  }
  internal_data?: {
    total: number
    with_stock: number
  }
  last_snapshots: {
    fbs_stock_at: string | null
    fbo_stock_at: string | null
    wb_prices_at: string | null
    storefront_at: string | null
    rrp_at: string | null
    internal_data_at?: string | null
  }
}

interface ProjectMarketplace {
  id: number
  marketplace_id: number
  is_enabled: boolean
  marketplace_code: string | null
  marketplace_name: string | null
}

interface Project {
  id: number
  name: string
  description: string | null
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Нет снимка'
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('ru-RU')
}

function formatNumber(value: number | null | undefined): string {
  return new Intl.NumberFormat('ru-RU').format(value ?? 0)
}

function formatCurrency(value: number, currency: string | null | undefined): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: currency || 'RUB',
    maximumFractionDigits: 0,
  }).format(value)
}

function marketplaceLabel(marketplace: ProjectMarketplace): string {
  if (marketplace.marketplace_code === 'wildberries') return 'WB'
  if (marketplace.marketplace_code === 'ozon') return 'Ozon'
  if (marketplace.marketplace_code === 'ym') return 'YM'
  return marketplace.marketplace_name || marketplace.marketplace_code || 'Marketplace'
}

export default function ProjectDashboard() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Обзор проекта', projectId)

  const [project, setProject] = useState<Project | null>(null)
  const [marketplaces, setMarketplaces] = useState<ProjectMarketplace[]>([])
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [latestWbReport, setLatestWbReport] = useState<WBFinanceReportLatest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | string | null>(null)

  const connectedMarketplaces = useMemo(
    () => marketplaces.filter((marketplace) => marketplace.is_enabled),
    [marketplaces],
  )
  const wbEnabled = connectedMarketplaces.some((marketplace) => marketplace.marketplace_code === 'wildberries')

  useEffect(() => {
    let alive = true

    async function loadDashboard() {
      setLoading(true)
      setError(null)
      setLatestWbReport(null)

      try {
        const [projectResult, marketplacesResult, kpisResult] = await Promise.all([
          apiGet<Project>(`/api/v1/projects/${projectId}`),
          apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`),
          apiGet<Kpis>(`/api/v1/dashboard/projects/${projectId}/kpis`),
        ])

        if (!alive) return

        setProject(projectResult.data)
        setMarketplaces(marketplacesResult.data)
        setKpis(kpisResult.data)

        const hasWb = marketplacesResult.data.some(
          (marketplace) => marketplace.is_enabled && marketplace.marketplace_code === 'wildberries',
        )

        if (hasWb) {
          const latestReport = await getWBFinanceReportsLatest(projectId)

          if (!alive) return
          setLatestWbReport(latestReport)
        }
      } catch (error) {
        if (!alive) return
        console.error('Failed to load dashboard:', error)
        setError(error as ApiError)
      } finally {
        if (alive) setLoading(false)
      }
    }

    loadDashboard()

    return () => {
      alive = false
    }
  }, [projectId])

  const coverage = kpis && kpis.storefront.expected_storefront_products > 0
    ? Math.round((kpis.storefront.storefront_products / kpis.storefront.expected_storefront_products) * 100)
    : null
  const latestWbReportTotal = latestWbReport?.total_amount

  return (
    <div className={styles.dashboardPage}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>Обзор проекта</div>
          <h1>{project?.name || 'Проект'}</h1>
          {project?.description ? <p>{project.description}</p> : null}
        </div>
        <div className={styles.marketplaceChips} aria-label="Подключенные маркетплейсы">
          {connectedMarketplaces.length > 0 ? (
            connectedMarketplaces.map((marketplace) => (
              <span
                key={`${marketplace.marketplace_id}-${marketplace.marketplace_code}`}
                className={`${styles.marketplaceChip} ${
                  marketplace.marketplace_code === 'wildberries' ? styles.wbChip : ''
                }`}
              >
                {marketplaceLabel(marketplace)}
              </span>
            ))
          ) : (
            <span className={styles.emptyChip}>Маркетплейсы не подключены</span>
          )}
        </div>
      </header>

      {error ? (
        <section className={styles.notice} role="alert">
          <strong>Не удалось загрузить обзор проекта.</strong>
          <span>{typeof error === 'string' ? error : error.detail || 'Проверьте API и повторите попытку.'}</span>
        </section>
      ) : null}

      {loading ? (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <div className={styles.eyebrow}>Пульс проекта</div>
              <h2>Загружаем данные</h2>
            </div>
          </div>
          <div className={styles.skeletonGrid} aria-label="Загрузка">
            <div />
            <div />
            <div />
            <div />
          </div>
        </section>
      ) : null}

      {!loading && !error && !wbEnabled ? (
        <section className={styles.notice}>
          <strong>WB не подключён.</strong>
          <span>Пульс проекта сейчас строится только по реальным данным Wildberries.</span>
          <Link href={`/app/project/${projectId}/marketplaces`}>Подключить маркетплейс</Link>
        </section>
      ) : null}

      {!loading && !error && wbEnabled && kpis ? (
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <div className={styles.eyebrow}>Пульс проекта</div>
              <h2>Wildberries</h2>
            </div>
            <Link className={styles.secondaryLink} href={`/app/project/${projectId}/wildberries`}>
              Открыть WB
            </Link>
          </div>

          <div className={styles.metricGrid}>
            <article className={styles.metricCard}>
              <div className={styles.metricLabel}>Каталог WB</div>
              <div className={styles.metricValue}>{formatNumber(kpis.storefront.storefront_products)}</div>
              <div className={styles.metricHint}>
                На витрине из {formatNumber(kpis.storefront.expected_storefront_products || kpis.wb.products_total)}
                {coverage !== null ? ` (${coverage}%)` : ''}
              </div>
              <div className={styles.metricSource}>Снимок витрины: {formatDateTime(kpis.last_snapshots.storefront_at)}</div>
            </article>

            <article className={styles.metricCard}>
              <div className={styles.metricLabel}>Остатки FBS / FBO</div>
              <div className={styles.splitMetric}>
                <div>
                  <span>FBS</span>
                  <strong>{formatNumber(kpis.stock.fbs_in_stock_products)}</strong>
                </div>
                <div>
                  <span>FBO</span>
                  <strong>{formatNumber(kpis.stock.fbo_in_stock_products)}</strong>
                </div>
              </div>
              <div className={styles.metricSource}>FBS: {formatDateTime(kpis.last_snapshots.fbs_stock_at)}</div>
              <div className={styles.metricSource}>FBO: {formatDateTime(kpis.last_snapshots.fbo_stock_at)}</div>
            </article>

            {kpis.internal_data && kpis.internal_data.total > 0 ? (
              <article className={styles.metricCard}>
                <div className={styles.metricLabel}>Внутренние данные</div>
                <div className={styles.metricValue}>{formatNumber(kpis.internal_data.with_stock)}</div>
                <div className={styles.metricHint}>С остатками из {formatNumber(kpis.internal_data.total)} товаров</div>
                <div className={styles.metricSource}>
                  Снимок: {formatDateTime(kpis.last_snapshots.internal_data_at)}
                </div>
              </article>
            ) : null}

            {latestWbReport && latestWbReportTotal !== null && latestWbReportTotal !== undefined ? (
              <article className={styles.metricCard}>
                <div className={styles.metricLabel}>Последний фин. отчёт WB</div>
                <div className={styles.metricValue}>{formatCurrency(latestWbReportTotal, latestWbReport.currency)}</div>
                <div className={styles.metricHint}>
                  {formatDate(latestWbReport.period_from)} — {formatDate(latestWbReport.period_to)}
                </div>
                <Link className={styles.cardLink} href={`/app/project/${projectId}/wildberries/finances/reports`}>
                  Список отчётов
                </Link>
              </article>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  )
}
