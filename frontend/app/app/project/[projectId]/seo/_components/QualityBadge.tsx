'use client'

import type { ReactNode } from 'react'

export type QualityMode = 'full' | 'preview' | 'degraded' | 'fallback'

export interface QualityBadgeReason {
  code: string
  details?: Record<string, unknown>
}

const QUALITY_THEME: Record<QualityMode, { bg: string; fg: string; label: string }> = {
  full: { bg: '#ecfdf5', fg: '#047857', label: 'Full quality' },
  preview: { bg: '#eff6ff', fg: '#1d4ed8', label: 'Preview' },
  degraded: { bg: '#fffbeb', fg: '#b45309', label: 'Degraded' },
  fallback: { bg: '#fef2f2', fg: '#b91c1c', label: 'Fallback' },
}

/**
 * Small inline badge that surfaces the `quality_mode` of a decision or
 * surfaced result. When `mode` is missing (e.g. legacy rows), render nothing
 * so existing pages do not get cluttered with "unknown" pills.
 */
export function QualityBadge({
  mode,
  reasons,
  size = 'sm',
  title,
}: {
  mode: QualityMode | string | null | undefined
  reasons?: QualityBadgeReason[] | null
  size?: 'xs' | 'sm' | 'md'
  title?: string
}) {
  if (!mode) return null
  const normalized = String(mode).toLowerCase() as QualityMode
  const theme = QUALITY_THEME[normalized] || QUALITY_THEME.degraded
  const padding = size === 'xs' ? '1px 6px' : size === 'md' ? '3px 10px' : '2px 8px'
  const fontSize = size === 'xs' ? 10 : size === 'md' ? 13 : 11
  const tooltip =
    title ||
    (reasons && reasons.length > 0
      ? reasons.map((r) => r.code).join(', ')
      : `quality_mode = ${normalized}`)
  return (
    <span
      title={tooltip}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding,
        borderRadius: 999,
        background: theme.bg,
        color: theme.fg,
        fontSize,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: 0.4,
      }}
    >
      {theme.label}
    </span>
  )
}

/**
 * Banner shown on every SEO generation surface while the module runs in
 * research-preview mode. Tells the operator that generated text is NOT
 * publishable and explains what the mode means. Owned by iteration 1
 * (see 10_implementation_decision_lock_v1.md — CD-1 / CD-2).
 */
export function ResearchPreviewBanner({
  previewEnabled,
  extra,
}: {
  previewEnabled?: boolean
  extra?: ReactNode
}) {
  const palette = previewEnabled
    ? { bg: '#fffbeb', border: '#fcd34d', fg: '#92400e' }
    : { bg: '#fef2f2', border: '#fecaca', fg: '#991b1b' }
  return (
    <div
      role="status"
      style={{
        border: `1px solid ${palette.border}`,
        background: palette.bg,
        color: palette.fg,
        borderRadius: 8,
        padding: '10px 14px',
        fontSize: 13,
        lineHeight: 1.45,
        marginBottom: 14,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4 }}>
        {previewEnabled ? 'Research preview' : 'Research preview · отключено'}
      </div>
      <div>
        {previewEnabled ? (
          <>
            Модуль генерации работает в режиме исследовательского превью.
            Сгенерированные названия и описания не готовы к публикации на WB —
            ручная проверка обязательна. Итерация 1 не включает критерии
            продвижения в производство.
          </>
        ) : (
          <>
            Генерация отключена: <code>SEO_GENERATION_PREVIEW_ENABLED=false</code>.
            Поднимите флаг, чтобы включить исследовательский режим. Публикация
            результатов без ручной проверки недопустима даже после включения.
          </>
        )}
        {extra ? <div style={{ marginTop: 6 }}>{extra}</div> : null}
      </div>
    </div>
  )
}
