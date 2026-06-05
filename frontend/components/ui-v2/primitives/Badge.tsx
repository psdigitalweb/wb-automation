import type { HTMLAttributes, ReactNode } from 'react'

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode
  tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'wb'
}

export function Badge({ children, tone = 'neutral', className = '', ...props }: BadgeProps) {
  return (
    <span className={`ec-badge ec-badge-${tone} ${className}`.trim()} {...props}>
      {children}
    </span>
  )
}

