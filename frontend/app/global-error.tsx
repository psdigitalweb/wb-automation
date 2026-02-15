'use client'

import { useEffect } from 'react'

/**
 * Root error boundary: catches errors in root layout and logs for debugging.
 * Next.js calls this when an error is thrown during render.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // #region agent log
    const payload = {
      hypothesisId: 'H1',
      location: 'global-error.tsx',
      message: 'Root layout or render error',
      data: {
        errorMessage: error?.message,
        digest: error?.digest,
        stack: error?.stack?.slice(0, 1000),
      },
      timestamp: Date.now(),
    }
    console.error('[DEBUG]', JSON.stringify(payload))
    // #endregion
  }, [error])

  return (
    <html lang="ru">
      <body>
        <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: '600px' }}>
          <h2>Something went wrong</h2>
          <p>{error?.message ?? 'Unknown error'}</p>
          <button onClick={() => reset()} type="button">
            Try again
          </button>
        </div>
      </body>
    </html>
  )
}
