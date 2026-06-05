'use client'

export type UiMode = 'v1' | 'v2'

const UI_MODE_KEY = 'ecomcore.ui'

function isUiMode(value: string | null): value is UiMode {
  return value === 'v1' || value === 'v2'
}

export function resolveUiMode(search: string = window.location.search): UiMode {
  const params = new URLSearchParams(search)
  const queryMode = params.get('ui')

  if (isUiMode(queryMode)) {
    localStorage.setItem(UI_MODE_KEY, queryMode)
    return queryMode
  }

  const storedMode = localStorage.getItem(UI_MODE_KEY)
  return isUiMode(storedMode) ? storedMode : 'v1'
}

