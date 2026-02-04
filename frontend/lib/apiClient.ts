/**
 * API client with automatic token handling and refresh
 */

import { getAccessToken, getRefreshToken, saveTokens, clearAuth } from './auth'
import { getApiBase } from './api'

// Feature flag for verbose API debug logging (must be defined to avoid ReferenceError in runtime).
// Keep disabled by default.
const debugEnabled = false

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
}

export interface IngestRunResponse {
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
}

/**
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

// --- Project proxy settings (frontend_prices) ---
export type ProjectProxySettings = {
  enabled: boolean
  scheme: 'http' | 'https' | string
  host: string
  port: number
  username: string | null
  rotate_mode: 'fixed' | string
  test_url: string
  last_test_at: string | null
  last_test_ok: boolean | null
  last_test_error: string | null
  password_set: boolean
}

export type ProjectProxySettingsUpdate = {
  enabled?: boolean
  scheme?: 'http' | 'https' | string
  host?: string
  port?: number
  username?: string | null
  rotate_mode?: 'fixed' | string
  test_url?: string
  password?: string
}

export type ProjectProxyTestResponse = {
  ok: boolean
  error?: string | null
  status_code?: number | null
  elapsed_ms?: number | null
}

export async function getProjectProxySettings(projectId: string): Promise<ProjectProxySettings> {
  const res = await apiGet<ProjectProxySettings>(`/api/v1/projects/${projectId}/settings/proxy`)
  return res.data
}

export async function updateProjectProxySettings(
  projectId: string,
  payload: ProjectProxySettingsUpdate
): Promise<ProjectProxySettings> {
  const res = await apiPut<ProjectProxySettings>(`/api/v1/projects/${projectId}/settings/proxy`, payload)
  return res.data
}export async function testProjectProxySettings(projectId: string): Promise<ProjectProxyTestResponse> {
  const res = await apiPost<ProjectProxyTestResponse>(`/api/v1/projects/${projectId}/settings/proxy/test`, {})
  return res.data
}

// --- WB SKU PnL ---
export interface WBSkuPnlSourceItem {
  report_id: number
  report_period_from: string | null
  report_period_to: string | null
  report_type: string
  rows_count: number
  amount_total: number
}

export interface WBSkuPnlItem {
  internal_sku: string
  product_name?: string | null
  product_image_url?: string | null
  product_image?: string | null
  wb_category?: string | null
  quantity_sold: number
  gmv: number
  avg_price_realization_unit?: number | null
  wb_price_admin?: number | null
  rrp_price?: number | null
  cogs_per_unit?: number | null
  cogs_total?: number | null
  income_before_cogs_unit?: number | null
  income_before_cogs_pct_rrp?: number | null
  wb_total_total?: number
  wb_total_unit?: number | null
  wb_total_pct_unit?: number | null
  wb_total_pct_rrp?: number | null
  product_profit?: number | null
  product_margin_pct?: number | null
  net_before_cogs_pct?: number | null
  wb_total_pct?: number | null
  trips_cnt?: number
  returns_cnt?: number
  buyout_pct?: number | null
  gmv_per_unit?: number | null // deprecated alias
  profit_per_unit?: number | null // deprecated alias
  profit_unit?: number | null
  margin_pct_unit?: number | null
  profit_pct_of_rrp_unit?: number | null // deprecated alias
  profit_pct_rrp?: number | null
  cogs_missing?: boolean
  wb_commission_total: number
  wb_commission_pct_unit?: number | null
  acquiring_fee: number
  delivery_fee: number
  pvz_fee: number
  rebill_logistics_cost?: number
  net_before_cogs: number
  events_count: number
  wb_commission_no_vat?: number
  wb_commission_vat?: number
  net_payable_metric?: number
  wb_sales_commission_metric?: number
  sources?: WBSkuPnlSourceItem[]
}

export interface WBSkuPnlListResponse {
  items: WBSkuPnlItem[]
  total_count: number
}

export interface WBProductSubjectItem {
  subject_id: number
  subject_name: string
  skus_count: number
}

export async function getWBProductSubjects(projectId: string): Promise<WBProductSubjectItem[]> {
  try {
    const res = await apiGet<WBProductSubjectItem[]>(
      `/api/v1/projects/${projectId}/marketplaces/wildberries/products/subjects`
    )
    return res.data
  } catch (e) {
    throw e
  }
}export async function getWBSkuPnl(
  projectId: string,
  params: {
    period_from: string
    period_to: string
    version?: number
    q?: string
    subject_id?: number
    sold_only?: boolean
    sort?: 'net_before_cogs' | 'net_before_cogs_pct' | 'wb_total_pct' | 'quantity_sold' | 'internal_sku' | 'gmv'
    order?: 'asc' | 'desc'
    limit?: number
    offset?: number
  }
): Promise<WBSkuPnlListResponse> {
  const qs = new URLSearchParams()
  qs.set('period_from', params.period_from)
  qs.set('period_to', params.period_to)
  if (params.version != null) qs.set('version', String(params.version))
  if (params.q) qs.set('q', params.q)
  if (params.subject_id != null) qs.set('subject_id', String(params.subject_id))
  if (params.sold_only) qs.set('sold_only', 'true')
  if (params.sort) qs.set('sort', params.sort)
  if (params.order) qs.set('order', params.order)
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.offset != null) qs.set('offset', String(params.offset))
  const res = await apiGet<WBSkuPnlListResponse>(
    `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/sku-pnl?${qs.toString()}`
  )
  return res.data
}export async function buildWBSkuPnl(
  projectId: string,
  body: {
    period_from: string
    period_to: string
    version?: number
    rebuild?: boolean
    ensure_events?: boolean
  }
): Promise<{ status: string; task_id: string | null; period_from: string; period_to: string }> {
  const res = await apiPost<{
    status: string
    task_id: string | null
    period_from: string
    period_to: string
  }>(`/api/v1/projects/${projectId}/marketplaces/wildberries/finances/sku-pnl/build`, body)
  return res.data
}