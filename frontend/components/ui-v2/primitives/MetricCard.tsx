import type { ReactNode } from 'react'
import { Card } from './Card'

type MetricCardProps = {
  label: string
  value: string | number
  hint?: string
  delta?: number
  deltaTone?: 'success' | 'danger' | 'neutral'
  marketplace?: 'wb' | 'ozon' | 'ya'
  children?: ReactNode
}

export function MetricCard({ label, value, hint, delta, deltaTone = 'neutral', marketplace, children }: MetricCardProps) {
  return (
    <Card className={`ec-metric-card ${marketplace ? `is-${marketplace}` : ''}`.trim()}>
      <div className="ec-metric-label">{label}</div>
      <div className="ec-metric-value">{value}</div>
      {hint || delta !== undefined ? (
        <div className={`ec-metric-hint is-${deltaTone}`}>
          {delta !== undefined ? `${delta > 0 ? '+' : ''}${delta}%` : hint}
        </div>
      ) : null}
      {children}
    </Card>
  )
}

