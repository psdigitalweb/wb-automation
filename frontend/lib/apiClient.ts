/**
 * API client with automatic token handling and refresh
 */

import { getAccessToken, getRefreshToken, saveTokens, clearAuth } from './auth'
import { getApiBase } from './api'

export interface ApiDebug {
  url: string
  status: number
  bodyPreview: string
  isJson: boolean
  parsed: any | null
}

export interface ApiError {
  detail: string
  status: number
  url: string
  bodyPreview: string
  isJson: boolean
  parsed: any | null
  debug: ApiDebug
}

export interface ApiResult<T> {
  data: T
  debug: ApiDebug
}

/**
 * Refresh access token using refresh token
 */
async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return null

  try {
    const apiBase = getApiBase()
    const res = await fetch(`${apiBase}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!res.ok) {
      return null
    }

    const data = await res.json()
    saveTokens(data)
    return data.access_token
  } catch {
    return null
  }
}

/**
 * Make API request with automatic token refresh
 * 
 * Note: For data endpoints (stocks, prices, metrics), Next.js caching is disabled
 * to ensure fresh data per project. Use cache: 'no-store' for GET requests.
 */
export async function apiRequest<T = any>(
  url: string,
  options: RequestInit = {}
): Promise<ApiResult<T>> {
  const apiBase = getApiBase()
  const fullUrl = url.startsWith('http') ? url : `${apiBase}${url}`

  const debugEnabled = process.env.NEXT_PUBLIC_DEBUG === 'true'

  // #region agent log
  try {
    const origin =
      typeof window !== 'undefined' && (window as any)?.location?.origin
        ? (window as any).location.origin
        : 'server'
    fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'apiClient.ts:apiRequest','message':'apiRequest built URL','data':{origin,apiBase,url,fullUrl,method:options?.method||'GET'},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'CORS1'})}).catch(()=>{});
  } catch {}
  // #endregion

  // Get access token
  let accessToken = getAccessToken()

  // Prepare headers
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  // Add authorization header if token exists
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }

  // Disable Next.js caching for data endpoints (GET requests to /v1/projects/*/stocks, /v1/projects/*/prices, etc.)
  // This ensures fresh data per project and prevents showing data from wrong project
  const isDataEndpoint = url.match(/\/v1\/(projects\/\d+\/)?(stocks|prices|dashboard)/)
  const fetchOptions: RequestInit = {
    ...options,
    headers,
  }
  
  // For GET requests to data endpoints, disable caching
  if (options.method === 'GET' || !options.method) {
    if (isDataEndpoint) {
      fetchOptions.cache = 'no-store' as RequestCache
    }
  }

  // Make request
  let res: Response
  try {
    res = await fetch(fullUrl, fetchOptions)
  } catch (fetchError: any) {
    // #region agent log
    try {
      fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'apiClient.ts:103','message':'fetch exception','data':{url:fullUrl,error:fetchError?.message||String(fetchError),name:fetchError?.name},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H6'})}).catch(()=>{});
    } catch {}
    // #endregion
    // Handle network errors (CORS, connection refused, etc.)
    throw {
      detail: fetchError?.message || 'Failed to fetch',
      status: 0,
      url: fullUrl,
      bodyPreview: fetchError?.message || 'Network error',
      isJson: false,
      parsed: null,
      debug: {
        url: fullUrl,
        status: 0,
        bodyPreview: fetchError?.message || 'Network error',
        isJson: false,
        parsed: null,
      },
    } as ApiError
  }

  // #region agent log
  try {
    const proxy = res.headers.get('x-ecomcore-proxy')
    const proxyTarget = res.headers.get('x-ecomcore-proxy-target')
    const ct = res.headers.get('content-type')
    fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'apiClient.ts:afterFetch','message':'fetch response received','data':{fullUrl,status:res.status,proxy,proxyTarget,contentType:ct},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'PROXY_OBS'})}).catch(()=>{});
  } catch {}
  // #endregion

  // If 401, try to refresh token and retry
  if (res.status === 401 && accessToken) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      // Retry with new token (preserve cache settings)
      fetchOptions.headers = {
        ...fetchOptions.headers,
        'Authorization': `Bearer ${newToken}`
      }
      res = await fetch(fullUrl, fetchOptions)
    } else {
      // Refresh failed, clear auth and throw error
      clearAuth()
      if (typeof window !== 'undefined') {
        window.location.href = '/'
      }
      const debugObj: ApiDebug = {
        url: fullUrl,
        status: 401,
        bodyPreview: 'Authentication failed',
        isJson: true,
        parsed: { detail: 'Authentication failed' },
      }
      throw {
        detail: 'Authentication failed',
        status: 401,
        url: fullUrl,
        bodyPreview: 'Authentication failed',
        isJson: true,
        parsed: { detail: 'Authentication failed' },
        debug: debugObj,
      } as ApiError
    }
  }

  const rawText = await res.text()
  const bodyPreview = rawText.slice(0, 500)
  const contentType = (res.headers.get('content-type') || '').toLowerCase()
  const isJson =
    contentType.includes('application/json') ||
    rawText.trim().startsWith('{') ||
    rawText.trim().startsWith('[')

  let parsed: any | null = null
  if (rawText) {
    if (isJson) {
      try {
        parsed = JSON.parse(rawText)
      } catch {
        parsed = null
      }
    }
  }

  const debugObj: ApiDebug = {
    url: fullUrl,
    status: res.status,
    bodyPreview,
    isJson,
    parsed,
  }

  if (debugEnabled) {
    // eslint-disable-next-line no-console
    console.log('apiRequest debug:', debugObj)
  }

  // Handle errors
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}: ${res.statusText}`
    try {
      const errorData = parsed || (rawText ? JSON.parse(rawText) : {})
      errorDetail = errorData?.detail || errorData?.message || errorDetail
    } catch {
      // Ignore JSON parse errors
    }
    throw {
      detail: errorDetail,
      status: res.status,
      url: fullUrl,
      bodyPreview,
      isJson,
      parsed,
      debug: debugObj,
    } as ApiError
  }

  // Parse response
  if (!rawText) return { data: {} as T, debug: debugObj }
  if (isJson && parsed !== null) return { data: parsed as T, debug: debugObj }

  // If backend returned non-JSON with 200, surface it as ApiError for UI.
  throw {
    detail: 'Non-JSON response from API',
    status: res.status,
    url: fullUrl,
    bodyPreview,
    isJson,
    parsed,
    debug: debugObj,
  } as ApiError
}

/**
 * GET request
 */
export async function apiGet<T = any>(url: string): Promise<ApiResult<T>> {
  return apiRequest<T>(url, { method: 'GET' })
}

/**
 * POST request
 */
export async function apiPost<T = any>(url: string, body?: any): Promise<ApiResult<T>> {
  return apiRequest<T>(url, {
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  })
}

/**
 * PUT request
 */
export async function apiPut<T = any>(url: string, body?: any): Promise<ApiResult<T>> {
  return apiRequest<T>(url, {
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
  })
}

/**
 * PATCH request
 */
export async function apiPatch<T = any>(url: string, body?: any): Promise<ApiResult<T>> {
  return apiRequest<T>(url, {
    method: 'PATCH',
    body: body ? JSON.stringify(body) : undefined,
  })
}

/**
 * DELETE request
 */
export async function apiDelete<T = any>(url: string): Promise<ApiResult<T>> {
  return apiRequest<T>(url, { method: 'DELETE' })
}

// Convenience adapters: return only `.data` so most UI code doesn't depend on `{data, debug}`
export async function apiGetData<T = any>(url: string): Promise<T> {
  const res = await apiGet<T>(url)
  return res.data
}

export async function apiPostData<T = any>(url: string, body?: any): Promise<T> {
  const res = await apiPost<T>(url, body)
  return res.data
}

export async function apiPutData<T = any>(url: string, body?: any): Promise<T> {
  const res = await apiPut<T>(url, body)
  return res.data
}

export async function apiPatchData<T = any>(url: string, body?: any): Promise<T> {
  const res = await apiPatch<T>(url, body)
  return res.data
}

export async function apiDeleteData<T = any>(url: string): Promise<T> {
  const res = await apiDelete<T>(url)
  return res.data
}

// WB Ingest Status types
export interface WBIngestStatus {
  job_code: string
  title: string
  has_schedule: boolean
  schedule_summary: string | null
  last_run_at: string | null
  last_status: string | null
  is_running: boolean
}export interface IngestRunResponse {
  id: number
  schedule_id: number | null
  project_id: number
  marketplace_code: string
  job_code: string
  triggered_by: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error_message: string | null
  error_trace: string | null
  stats_json: any
  created_at: string
  updated_at: string
}/**
 * Get WB ingest status for a project
 */
export async function getWBIngestStatus(projectId: string): Promise<WBIngestStatus[]> {
  const res = await apiGet<WBIngestStatus[]>(`/api/v1/projects/${projectId}/ingestions/wb/status`)
  return res.data
}/**
 * Manually trigger a WB ingest job
 */
export async function runWBIngest(
  projectId: string, 
  jobCode: string,
  params?: { date_from?: string; date_to?: string }
): Promise<IngestRunResponse> {
  const body = params ? { params_json: params } : undefined
  const res = await apiPost<IngestRunResponse>(
    `/api/v1/projects/${projectId}/ingestions/wb/${jobCode}/run`,
    body
  )
  return res.data
}