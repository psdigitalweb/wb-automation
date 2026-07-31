import type { ReactNode } from 'react'
import { Badge } from './Badge'

type PageHeaderProps = {
  title: string
  eyebrow?: string
  subtitle?: string
  marketplaceTag?: 'wb' | 'ozon' | 'ya'
  actions?: ReactNode
}

export function PageHeader({ title, eyebrow, subtitle, marketplaceTag, actions }: PageHeaderProps) {
  return (
    <div className="ec-page-header">
      <div>
        {eyebrow ? <div className="ec-page-eyebrow">{eyebrow}</div> : null}
        <div className="ec-page-title-row">
          <h1>{title}</h1>
          {marketplaceTag ? <Badge tone={marketplaceTag === 'wb' ? 'wb' : 'info'}>{marketplaceTag.toUpperCase()}</Badge> : null}
        </div>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {actions ? <div className="ec-page-actions">{actions}</div> : null}
    </div>
  )
}

