/**
 * Get the base URL for API requests.
 *
 * Uses NEXT_PUBLIC_API_BASE if provided.
 * Default is empty string, so browser calls same-origin `/api/...` and Next.js rewrites proxy to backend.
 *
 * Example override (if you really need direct backend calls):
 * NEXT_PUBLIC_API_BASE="http://localhost:8000"
 */
export function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE || ''
}






