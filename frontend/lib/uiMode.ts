'use client'

export type UiMode = 'v1' | 'v2'

const UI_MODE_KEY = 'ecomcore.ui'

export function resolveUiMode(search: string = window.location.search): UiMode {
  const params = new URLSearchParams(search)
  const queryMode = params.get('ui')

  if (queryMode === 'v1') {
    return 'v1'
  }

  if (queryMode === 'v2') {
    localStorage.setItem(UI_MODE_KEY, queryMode)
  }

  return 'v2'
}
