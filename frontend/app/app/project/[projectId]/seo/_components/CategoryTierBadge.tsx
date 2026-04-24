'use client'

/**
 * CategoryTierBadge — Iteration 2 (WS-E/F).
 *
 * Surfaces the category's ``eligibility_tier`` as a small inline pill next
 * to the category / SKU title. Single source of truth is
 * ``SeoCategoryMatchingReadiness.eligibility_tier`` via the eval endpoints.
 *
 * Tiers follow the backend enum:
 *   - ``preview_only``  → "Preview only"   (grey)
 *   - ``evaluated``     → "Evaluated"      (blue)
 *   - ``approved``      → "Approved"       (green)
 *
 * When the tier is missing (legacy row, before the first eval run), the
 * badge renders "Preview only" which matches the server-side default.
 */

export type EligibilityTier = 'preview_only' | 'evaluated' | 'approved'

const TIER_THEME: Record<EligibilityTier, { bg: string; fg: string; label: string }> = {
  preview_only: { bg: '#f3f4f6', fg: '#4b5563', label: 'Preview only' },
  evaluated: { bg: '#eff6ff', fg: '#1d4ed8', label: 'Evaluated' },
  approved: { bg: '#ecfdf5', fg: '#047857', label: 'Approved' },
}

export function CategoryTierBadge({
  tier,
  size = 'sm',
  profileVersion,
}: {
  tier: EligibilityTier | string | null | undefined
  size?: 'xs' | 'sm' | 'md'
  profileVersion?: string | null
}) {
  const normalized = (String(tier || 'preview_only').toLowerCase() as EligibilityTier)
  const theme = TIER_THEME[normalized] || TIER_THEME.preview_only
  const padding = size === 'xs' ? '1px 6px' : size === 'md' ? '3px 10px' : '2px 8px'
  const fontSize = size === 'xs' ? 10 : size === 'md' ? 13 : 11
  const tooltip = profileVersion
    ? `eligibility_tier = ${normalized}; profile = ${profileVersion}`
    : `eligibility_tier = ${normalized}`
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
 * Small pill that distinguishes UI-visible "approved" vs "validated" on the
 * candidate path. ``approval_state`` is operator intent; ``trust_state`` is
 * the eval verdict. They are intentionally separate pills per the Iteration 2
 * UI decision (see 06_ui_and_operator_flow_changes.md §F).
 */
export function ApprovalStateBadge({
  approvalState,
  trustState,
}: {
  approvalState?: string | null
  trustState?: string | null
}) {
  const items: { label: string; bg: string; fg: string; title: string }[] = []
  if (approvalState && approvalState !== 'draft') {
    const themes: Record<string, { bg: string; fg: string; label: string }> = {
      preview: { bg: '#f3f4f6', fg: '#4b5563', label: 'Preview' },
      candidate: { bg: '#fef3c7', fg: '#92400e', label: 'Candidate' },
      approved: { bg: '#ecfdf5', fg: '#047857', label: 'Approved' },
    }
    const t = themes[approvalState.toLowerCase()] || themes.preview
    items.push({ ...t, title: `approval_state = ${approvalState}` })
  }
  if (trustState === 'validated') {
    items.push({
      label: 'Validated',
      bg: '#eff6ff',
      fg: '#1d4ed8',
      title: 'trust_state = validated (eval passed)',
    })
  }
  if (items.length === 0) return null
  return (
    <span style={{ display: 'inline-flex', gap: 6 }}>
      {items.map((item, idx) => (
        <span
          key={`${item.label}-${idx}`}
          title={item.title}
          style={{
            padding: '2px 8px',
            borderRadius: 999,
            background: item.bg,
            color: item.fg,
            fontSize: 11,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: 0.4,
          }}
        >
          {item.label}
        </span>
      ))}
    </span>
  )
}
