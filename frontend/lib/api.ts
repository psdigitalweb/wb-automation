/**
 * Get the base URL for API requests.
 * Always use same-origin `/api` and rely on nginx/Next rewrites proxying to backend.
 */
export function getApiBase(): string {
  return '/api'
}






