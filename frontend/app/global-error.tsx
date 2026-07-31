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
    console.error(error)
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
