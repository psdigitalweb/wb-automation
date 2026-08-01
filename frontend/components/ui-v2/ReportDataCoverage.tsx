'use client'

import type { ReportFilterOptions } from '@/lib/reportFilterOptions'
import { periodHasData } from '@/lib/reportFilterOptions'
import styles from './ReportDataCoverage.module.css'

function formatDate(value: string | null) {
  if (!value) return 'нет данных'
  return new Date(`${value}T00:00:00`).toLocaleDateString('ru-RU')
}

export function ReportDataCoverage({
  options,
  periodFrom,
  periodTo,
}: {
  options: ReportFilterOptions | null
  periodFrom: string
  periodTo: string
}) {
  if (!options) return null
  const primary = options.datasets.find((dataset) => dataset.role === 'primary')
  if (!options.date_filter.enabled) {
    return <div className={`${styles.coverage} ${styles.empty}`}>Для отчёта пока нет фактических данных.</div>
  }

  const partial = options.datasets.filter(
    (dataset) =>
      dataset.role === 'supplementary' &&
      (!dataset.min_date ||
        !dataset.max_date ||
        dataset.min_date > periodFrom ||
        dataset.max_date < periodTo),
  )
  const selectedHasData = periodHasData(options, periodFrom, periodTo)

  return (
    <div className={`${styles.coverage} ${!selectedHasData ? styles.warning : ''}`}>
      <span>
        {primary?.title ?? 'Основные данные'}: {formatDate(options.date_filter.min_date)} —{' '}
        {formatDate(options.date_filter.max_date)}
      </span>
      {!selectedHasData ? <strong>В выбранном периоде нет данных.</strong> : null}
      {partial.length > 0 ? (
        <span>
          Частичное покрытие: {partial.map((dataset) => dataset.title).join(', ')}.
        </span>
      ) : null}
    </div>
  )
}
