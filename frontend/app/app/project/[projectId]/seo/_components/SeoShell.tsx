'use client'

import Link from 'next/link'
import type { CSSProperties, ReactNode } from 'react'
import styles from './SeoShell.module.css'

export function normalizeError(error: unknown): string {
  const maybe = error as { detail?: string; message?: string }
  return maybe?.detail || maybe?.message || 'Произошла ошибка'
}

export function SeoShell({
  projectId,
  title,
  subtitle,
  children,
}: {
  projectId: string
  title: string
  subtitle?: string
  children: ReactNode
  extraTabs?: Array<[string, string]>
}) {
  return (
    <div className={styles.shell}>
      <div className={styles.content}>
        <div className={styles.pageTop}>
          <div>
            <div className={styles.eyebrow}>SEO · WILDBERRIES</div>
            <h1 className={styles.title}>{title}</h1>
            {subtitle ? <div className={styles.lead}>{subtitle}</div> : null}
          </div>
          <div className={styles.pageActions}>
            <Link className={`${styles.button} ${styles.buttonGhost}`} href={`/app/project/${projectId}`}>
              К проекту
            </Link>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Card({ children, className = '', style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return <section className={`${styles.card} ${className}`.trim()} style={style}>{children}</section>
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
}: {
  title?: string
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className={styles.panel}>
      {(title || actions) && (
        <div className={styles.panelHead}>
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <div className={styles.subtext}>{subtitle}</div> : null}
          </div>
          {actions ? <div>{actions}</div> : null}
        </div>
      )}
      <div className={styles.panelBody}>{children}</div>
    </section>
  )
}

export function StatusPill({ label, tone = 'neutral' }: { label: string; tone?: 'good' | 'warn' | 'bad' | 'neutral' | 'info' }) {
  const toneClass = tone === 'good' ? styles.good : tone === 'warn' ? styles.warn : tone === 'bad' ? styles.bad : tone === 'info' ? styles.info : ''
  return <span className={`${styles.badge} ${toneClass}`.trim()}>{label}</span>
}

export function buttonClass(kind: 'primary' | 'light' | 'ghost' | 'danger' = 'primary') {
  const kindClass = {
    primary: styles.buttonPrimary,
    light: styles.buttonLight,
    ghost: styles.buttonGhost,
    danger: styles.buttonDanger,
  }[kind]
  return `${styles.button} ${kindClass}`
}

export function buttonStyle(kind: 'primary' | 'light' | 'ghost' | 'danger' = 'primary') {
  const base: CSSProperties = {
    borderRadius: 6,
    padding: '0 10px',
    minHeight: 32,
    fontWeight: 600,
    textDecoration: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  }
  const stylesByKind: Record<typeof kind, CSSProperties> = {
    primary: { background: 'oklch(38% 0.10 155)', color: '#fff', border: '0.5px solid oklch(38% 0.10 155)' },
    light: { background: '#fff', color: 'oklch(22% 0.03 260)', border: '0.5px solid oklch(22% 0.03 260 / 0.15)' },
    ghost: { background: 'transparent', color: 'oklch(42% 0.02 260)', border: '0.5px solid transparent' },
    danger: { background: 'oklch(56% 0.20 22)', color: '#fff', border: '0.5px solid oklch(56% 0.20 22)' },
  }
  return { ...base, ...stylesByKind[kind] } as const
}

export { styles as seoStyles }
