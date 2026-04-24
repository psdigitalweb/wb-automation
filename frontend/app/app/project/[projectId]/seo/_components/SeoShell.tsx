'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'

export function normalizeError(error: unknown): string {
  const maybe = error as { detail?: string; message?: string }
  return maybe?.detail || maybe?.message || 'Произошла ошибка'
}

export function SeoShell({
  projectId,
  title,
  subtitle,
  children,
  extraTabs,
}: {
  projectId: string
  title: string
  subtitle?: string
  children: ReactNode
  extraTabs?: Array<[string, string]>
}) {
  const tabs: Array<[string, string]> = [
    ['Категории', `/app/project/${projectId}/seo/categories`],
    ['Товары', `/app/project/${projectId}/seo/products`],
    ['Eval 812', `/app/project/${projectId}/seo/categories/812/eval`],
    ...(extraTabs || []),
  ]
  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: 24 }}>
      <nav style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 18, color: '#64748b' }}>
        <Link href={`/app/project/${projectId}`}>Проект</Link>
        <span>/</span>
        <Link href={`/app/project/${projectId}/seo`}>SEO</Link>
      </nav>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 22 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 34, lineHeight: 1.15 }}>{title}</h1>
          {subtitle && <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: 16 }}>{subtitle}</p>}
        </div>
        <Link href={`/app/project/${projectId}`} style={buttonStyle('light')}>В проект</Link>
      </div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
        {tabs.map(([label, href]) => (
          <Link key={href} href={href} style={buttonStyle('light')}>{label}</Link>
        ))}
        <Link href={`/app/project/${projectId}/seo/sku-meaning`} style={buttonStyle('ghost')}>Техническая диагностика</Link>
      </div>
      {children}
    </main>
  )
}

export function Card({ children }: { children: ReactNode }) {
  return <section style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 18, background: '#fff' }}>{children}</section>
}

export function StatusPill({ label, tone = 'neutral' }: { label: string; tone?: 'good' | 'warn' | 'bad' | 'neutral' }) {
  const colors = {
    good: ['#ecfdf5', '#047857'],
    warn: ['#fffbeb', '#b45309'],
    bad: ['#fef2f2', '#b91c1c'],
    neutral: ['#f1f5f9', '#334155'],
  }[tone]
  return <span style={{ display: 'inline-flex', background: colors[0], color: colors[1], borderRadius: 999, padding: '5px 10px', fontSize: 13, fontWeight: 700 }}>{label}</span>
}

export function buttonStyle(kind: 'primary' | 'light' | 'ghost' | 'danger' = 'primary') {
  const styles = {
    primary: { background: '#111827', color: '#fff', border: '1px solid #111827' },
    light: { background: '#fff', color: '#111827', border: '1px solid #cbd5e1' },
    ghost: { background: '#f8fafc', color: '#334155', border: '1px solid #e2e8f0' },
    danger: { background: '#991b1b', color: '#fff', border: '1px solid #991b1b' },
  }[kind]
  return {
    ...styles,
    borderRadius: 8,
    padding: '10px 14px',
    fontWeight: 700,
    textDecoration: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 40,
    cursor: 'pointer',
  } as const
}
