/**
 * Get the base URL for API requests.
 *
 * - If NEXT_PUBLIC_API_BASE is set (including to ""), use it.
 * - Default: empty string = same-origin /api/... via Next.js rewrites/proxy.
 *   Browser talks to Next.js (no CORS), Next.js proxies to backend (api:8000 in Docker).
 * - For direct backend access in dev, set NEXT_PUBLIC_API_BASE=http://localhost:8000 explicitly.
 */
export function getApiBase(): string {
  const envBase = process.env.NEXT_PUBLIC_API_BASE
  if (envBase !== undefined && envBase !== '') return envBase
  return ''
}






