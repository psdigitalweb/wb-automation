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

function messageFromApiErrorValue(value: unknown): string | null {
  if (typeof value === 'string') {
    const message = value.trim()
    return message || null
  }

  if (!value || typeof value !== 'object') return null

  const errorValue = value as Record<string, unknown>
  for (const key of ['message', 'reason', 'detail']) {
    const candidate = errorValue[key]
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim()
  }

  return null
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') return fallback

  const apiError = error as Record<string, unknown>
  return (
    messageFromApiErrorValue(apiError.detail) ??
    messageFromApiErrorValue(apiError.message) ??
    fallback
  )
}

export interface ApiResult<T> {
  data: T
  debug: ApiDebug
}

export interface ApiDownloadResult {
  blob: Blob
  filename: string | null
  contentType: string | null
}

/**
 * Refresh access token using refresh token
 */
async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return null

  try {
    const refreshUrl = buildFullUrl('/api/v1/auth/refresh')
    const res = await fetch(refreshUrl, {
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

function shouldUseDirectBackend(url: string): boolean {
  if (typeof window === 'undefined') {
    return false
  }

  const hostname = window.location.hostname || 'localhost'
  const port = window.location.port || ''
  const isLocalDevHost =
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    hostname === '0.0.0.0'
  if (!isLocalDevHost) {
    return false
  }

  const isSlowEndpoint =
    url.includes('/wildberries/search-report/keywords') ||
    url.includes('/wildberries/search-report/search-texts')
  const isSeoDebugEndpoint =
    url.includes('/seo/query-pipeline/debug') ||
    url.includes('/seo/categories/') ||
    url.includes('/seo/feature-flags') ||
    url.includes('/seo/sku-meaning') ||
    url.includes('/seo/query-meaning-library') ||
    url.includes('/seo/meaning-aware-matcher') ||
    url.includes('/seo/category-bootstrap') ||
    url.includes('/seo/products') ||
    url.includes('/seo/eval-datasets/export') ||
    url.includes('/wildberries/seo/query-import') ||
    url.includes('/wildberries/products/lookup') ||
    url.includes('/marketplaces/wildberries/products/subjects') ||
    /^\/api\/v1\/projects(?:\/\d+)?$/.test(url)
  const isAuthEndpoint = url.startsWith('/api/v1/auth/')

  return isSlowEndpoint || isSeoDebugEndpoint || isAuthEndpoint
}

function buildFullUrl(url: string): string {
  const apiBase = getApiBase()
  if (url.startsWith('http')) return url
  if (apiBase) return `${apiBase}${url}`

  // Default: same-origin /api/... via Next.js rewrites.
  // In local dev on the Next dev server, some proxy paths are unstable,
  // so use backend:8000 directly for targeted endpoints only.
  if (shouldUseDirectBackend(url)) {
    const pageHost = window.location.hostname || 'localhost'
    const backendHost = pageHost === 'localhost' || pageHost === '0.0.0.0' ? '127.0.0.1' : pageHost
    return `http://${backendHost}:8000${url}`
  }

  return url
}

function buildFetchOptions(
  url: string,
  options: RequestInit = {},
  accessToken?: string | null
): RequestInit {
  const headers = new Headers(options.headers)
  const hasBody = options.body !== undefined && options.body !== null
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData

  if (hasBody && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const fetchOptions: RequestInit = {
    ...options,
    headers,
  }

  const isDataEndpoint = url.match(/\/v1\/(projects\/\d+\/)?(stocks|prices|dashboard)/)
  if ((options.method === 'GET' || !options.method) && isDataEndpoint) {
    fetchOptions.cache = 'no-store' as RequestCache
  }

  return fetchOptions
}

function buildNetworkError(fullUrl: string, fetchError: any): ApiError {
  return {
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
  }
}

function buildAuthError(fullUrl: string): ApiError {
  const debugObj: ApiDebug = {
    url: fullUrl,
    status: 401,
    bodyPreview: 'Authentication failed',
    isJson: true,
    parsed: { detail: 'Authentication failed' },
  }

  return {
    detail: 'Authentication failed',
    status: 401,
    url: fullUrl,
    bodyPreview: 'Authentication failed',
    isJson: true,
    parsed: { detail: 'Authentication failed' },
    debug: debugObj,
  }
}

async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<{ res: Response; fullUrl: string }> {
  const fullUrl = buildFullUrl(url)
  const accessToken = getAccessToken()
  let fetchOptions = buildFetchOptions(url, options, accessToken)

  let res: Response
  try {
    res = await fetch(fullUrl, fetchOptions)
  } catch (fetchError: any) {
    throw buildNetworkError(fullUrl, fetchError)
  }

  if (res.status === 401 && accessToken) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      fetchOptions = buildFetchOptions(url, options, newToken)
      res = await fetch(fullUrl, fetchOptions)
    } else {
      clearAuth()
      if (typeof window !== 'undefined') {
        window.location.href = '/'
      }
      throw buildAuthError(fullUrl)
    }
  }

  return { res, fullUrl }
}

function getFilenameFromContentDisposition(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null

  const utf8Match = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim())
    } catch {
      return utf8Match[1].trim()
    }
  }

  const plainMatch = contentDisposition.match(/filename\s*=\s*"?([^\";]+)"?/i)
  return plainMatch?.[1]?.trim() || null
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
  const { res, fullUrl } = await fetchWithAuth(url, options)

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
  if (isJson && parsed !== null) {
    return { data: parsed as T, debug: debugObj }
  }

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

export async function apiDownload(
  url: string,
  options: RequestInit = {}
): Promise<ApiDownloadResult> {
  const { res, fullUrl } = await fetchWithAuth(url, options)

  if (!res.ok) {
    const rawText = await res.text()
    const bodyPreview = rawText.slice(0, 500)
    const contentType = (res.headers.get('content-type') || '').toLowerCase()
    const isJson =
      contentType.includes('application/json') ||
      rawText.trim().startsWith('{') ||
      rawText.trim().startsWith('[')

    let parsed: any | null = null
    if (rawText && isJson) {
      try {
        parsed = JSON.parse(rawText)
      } catch {
        parsed = null
      }
    }

    const debugObj: ApiDebug = {
      url: fullUrl,
      status: res.status,
      bodyPreview,
      isJson,
      parsed,
    }

    throw {
      detail: parsed?.detail || parsed?.message || `HTTP ${res.status}: ${res.statusText}`,
      status: res.status,
      url: fullUrl,
      bodyPreview,
      isJson,
      parsed,
      debug: debugObj,
    } as ApiError
  }

  return {
    blob: await res.blob(),
    filename: getFilenameFromContentDisposition(res.headers.get('content-disposition')),
    contentType: res.headers.get('content-type'),
  }
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
  progress_current?: number | null
  progress_total?: number | null
  progress_pct?: number | null
  progress_text?: string | null
  progress_detail?: string | null
  active_run_id?: number | null
  active_mode?: string | null
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
  params?: Record<string, any>
): Promise<IngestRunResponse> {
  const body = params ? { params_json: params } : undefined
  const res = await apiPost<IngestRunResponse>(
    `/api/v1/projects/${projectId}/ingestions/wb/${jobCode}/run`,
    body
  )
  return res.data
}

export async function markIngestRunTimeout(
  projectId: string,
  runId: number,
  body?: { reason_code?: string; reason_text?: string }
): Promise<IngestRunResponse> {
  const res = await apiPost<IngestRunResponse>(
    `/api/v1/projects/${projectId}/ingest/runs/${runId}/mark-timeout`,
    body ?? { reason_code: 'manual', reason_text: 'Stopped from project settings UI' }
  )
  return res.data
}

// --- WB Search Report (tabular) ---
export type WBSearchReportSnapshot = {
  id: number
  project_id: number
  period_from: string
  period_to: string
  include_search_texts: boolean
  include_substituted_skus: boolean
  position_cluster: string
  order_by: any
  stats: any
  ingest_run_id: number | null
  created_at: string
  updated_at: string
}

export type WBSearchReportSnapshotListResponse = {
  items: WBSearchReportSnapshot[]
}

export type WBSearchReportSnapshotResponse = {
  snapshot: WBSearchReportSnapshot
  raw_main_page: any | null
  request_params: any
}

export type WBSearchReportProduct = {
  nm_id: number
  vendor_code: string | null
  name: string | null
  photos: string[]
  vendor_code_norm?: string | null
  brand_name: string | null
  subject_id: number | null
  subject_name: string | null
  tag_id: number | null
  tag_name: string | null
  opens?: number | null
  add_to_cart?: number | null
  conversion_to_order?: number | null
  orders_sum?: number | null
  fbo_stock_qty?: number | null
  enterprise_stock_qty?: number | null
  metrics: any
  raw: any
  updated_at: string | null
}

export type WBSearchReportProductsResponse = {
  items: WBSearchReportProduct[]
  page: number
  page_size: number
  total: number
  pages: number
}

export type WBSearchReportSearchTextsResponse = {
  items: any[]
}

export type WBSearchReportSubjectItem = {
  subject_id: number
  subject_name: string | null
  products_cnt: number
}

export type WBSearchReportSubjectsResponse = {
  items: WBSearchReportSubjectItem[]
}

export type WBSearchReportKeywordsMultiResponse = {
  orders: any[]
  openCard: any[]
  addToCart: any[]
  cached: Record<string, boolean>
  errors: Record<string, any>
}

export async function getWBSearchReportSnapshots(projectId: string, limit = 50) {
  const res = await apiGet<WBSearchReportSnapshotListResponse>(
    `/api/v1/projects/${projectId}/wildberries/search-report/snapshots?limit=${limit}`
  )
  return res.data
}

export async function getWBSearchReportSnapshot(projectId: string, snapshotId: number) {
  const res = await apiGet<WBSearchReportSnapshotResponse>(
    `/api/v1/projects/${projectId}/wildberries/search-report/snapshots/${snapshotId}`
  )
  return res.data
}

export async function getWBSearchReportProducts(
  projectId: string,
  params: {
    snapshot_id: number
    q?: string
    brand_name?: string
    subject_id?: number
    date_from?: string
    date_to?: string
    sort?: string
    order?: 'asc' | 'desc' | string
    page?: number
    page_size?: number
  }
) {
  const qs = new URLSearchParams()
  qs.set('snapshot_id', String(params.snapshot_id))
  if (params.q) qs.set('q', params.q)
  if (params.brand_name) qs.set('brand_name', params.brand_name)
  if (params.subject_id != null) qs.set('subject_id', String(params.subject_id))
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  if (params.sort) qs.set('sort', params.sort)
  if (params.order) qs.set('order', params.order)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  const res = await apiGet<WBSearchReportProductsResponse>(
    `/api/v1/projects/${projectId}/wildberries/search-report/products?${qs.toString()}`
  )
  return res.data
}

export async function getWBSearchReportSubjects(
  projectId: string,
  params: {
    snapshot_id: number
    q?: string
    brand_name?: string
  }
) {
  const qs = new URLSearchParams()
  qs.set('snapshot_id', String(params.snapshot_id))
  if (params.q) qs.set('q', params.q)
  if (params.brand_name) qs.set('brand_name', params.brand_name)
  const res = await apiGet<WBSearchReportSubjectsResponse>(
    `/api/v1/projects/${projectId}/wildberries/search-report/subjects?${qs.toString()}`
  )
  return res.data
}

export async function getWBSearchReportSearchTexts(
  projectId: string,
  params: {
    snapshot_id: number
    nm_id: number
    limit?: number
  }
) {
  const qs = new URLSearchParams()
  qs.set('snapshot_id', String(params.snapshot_id))
  qs.set('nm_id', String(params.nm_id))
  if (params.limit) qs.set('limit', String(params.limit))
  const res = await apiGet<WBSearchReportSearchTextsResponse>(
    `/api/v1/projects/${projectId}/wildberries/search-report/search-texts?${qs.toString()}`
  )
  return res.data
}

export async function getWBSearchReportKeywordsMulti(
  projectId: string,
  params: {
    snapshot_id: number
    nm_id: number
    date_from?: string
    date_to?: string
    limit?: number
    cache_ttl_hours?: number
  }
) {
  const qs = new URLSearchParams()
  qs.set('snapshot_id', String(params.snapshot_id))
  qs.set('nm_id', String(params.nm_id))
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.cache_ttl_hours != null) qs.set('cache_ttl_hours', String(params.cache_ttl_hours))
  const res = await apiGet<WBSearchReportKeywordsMultiResponse>(
    `/api/v1/projects/${projectId}/wildberries/search-report/keywords?${qs.toString()}`
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
  trips_cnt?: number | null
  returns_cnt?: number | null
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

export interface SeoCategoryListItem {
  category_id: number
  category_name: string
  skus_count: number
  readiness_status: CategoryBootstrapStatusResponse['readiness_status']
  queries_count: number
  clusters_count: number
  query_meanings_count: number
  query_atoms_count: number
  embeddings_count: number
  category_axes_status: string
  latest_run_id: number | null
  has_query_corpus: boolean
  has_category_profile: boolean
}

// Unit PnL (WB finance report lines aggregated by nm_id)

export interface WBUnitPnlRow {
  nm_id: number
  vendor_code?: string | null
  title?: string | null
  photos: string[]
  sale_amount: number
  transfer_amount: number
  logistics_cost: number
  storage_cost: number
  acceptance_cost: number
  other_withholdings: number
  penalties: number
  loyalty_comp_display: number
  total_to_pay: number
  sales_cnt: number
  returns_cnt: number
  net_sales_cnt: number
  deliveries_qty?: number | null
  returns_log_qty?: number | null
  buyout_rate?: number | null
  wb_price_avg?: number | null
  spp_avg?: number | null
  fact_price_avg?: number | null
  rrp_price?: number | null
  rrp_missing?: boolean
  cogs_per_unit?: number | null
  cogs_total?: number | null
  cogs_rule_text?: string | null
  cogs_missing?: boolean
  commission_vv_signed?: number | null
  acquiring?: number | null
  wb_own_total_signed?: number | null
  wb_common_allocated_total?: number | null
  wb_common_allocated_per_unit?: number | null
  wb_total_signed?: number | null
  wb_total_cost_per_unit?: number | null
  profit_per_unit?: number | null
  margin_pct_of_revenue?: number | null
  margin_pct_of_rrp?: number | null
  markup_pct_of_cogs?: number | null
  packaging_cost_per_unit?: number | null
  packaging_cost_total?: number | null
  packaging_missing?: boolean
  additional_costs_total?: number
  additional_costs_per_unit?: number
  full_profit_per_unit?: number | null
  full_profit_total?: number | null
  full_margin_pct_of_revenue?: number | null
}

export interface WBUnitPnlResponse {
  scope: { mode: string; report_id?: number; rr_dt_from?: string; rr_dt_to?: string }
  rows_total: number
  items: WBUnitPnlRow[]
  header_totals: {
    lines_total?: number
    scope_lines_total?: number
    skus_total?: number
    rows_total?: number
    filter_header?: boolean
    sale?: number
    transfer_for_goods?: number
    logistics_cost?: number
    storage_cost?: number
    acceptance_cost?: number
    other_withholdings?: number
    penalties?: number
    loyalty_comp_display?: number
    commission_vv_signed?: number | null
    acquiring?: number | null
    wb_total_signed?: number | null
    wb_total_pct_of_revenue?: number | null
    total_to_pay?: number
    rrp_sales_model?: number | null
    wb_take_from_rrp?: number | null
    wb_take_pct_of_rrp?: number | null
    rrp_coverage_pct?: number | null
    rrp_net_units_covered?: number | null
    net_units_total?: number | null
    packaging_cost_total?: number | null
    cogs_cost_total?: number | null
    cogs_missing_count?: number
    packaging_missing_count?: number
    additional_costs_total?: number | null
    marketplace_additional_costs_total?: number | null
    warehouse_labor_costs_total?: number | null
    tax_model_code?: string | null
    tax_base?: number | null
    tax_vat_amount?: number | null
    tax_profit_amount?: number | null
    tax_expense_total?: number | null
    tax_rate?: number | null
    tax_vat_rate?: number | null
    full_profit_before_tax_total?: number | null
    full_profit_total?: number | null
    full_margin_pct_of_revenue?: number | null
  }
  debug?: Record<string, number>
}

export interface WBUnitPnlDetailsResponse {
  nm_id: number
  scope: Record<string, unknown>
  product?: { title?: string; vendor_code?: string; photos: string[] } | null
  base_calc: {
    wb_price_avg?: number
    spp_avg?: number
    fact_price_avg?: number
    rrp_price?: number | null
    delta_fact_to_rrp_pct?: number | null
  }
  commission_vv_signed?: number | null
  acquiring?: number | null
  wb_own_total_signed?: number | null
  wb_common_allocated_total?: number | null
  wb_common_allocated_per_unit?: number | null
  wb_total_signed?: number | null
  wb_total_pct_of_sale?: number | null
  wb_costs_per_unit: {
    total?: number | null
    breakdown?: {
      commission?: number | null
      acquiring?: number | null
      pvz_reward?: number | null
      rebill_logistic_cost?: number | null
      settlement_adjustment?: number | null
      settlement_total?: number | null
      logistics?: number | null
      storage?: number | null
      acceptance?: number | null
      withholdings?: number | null
      penalties?: number | null
      common_wb_allocated?: number | null
      total?: number | null
    }
    own_wb_total_signed?: number
    common_wb_allocated_total?: number
    common_wb_allocation_basis?: Record<string, number>
    settlement_cost?: number
    pvz_reward?: number
    rebill_logistic_cost?: number
    settlement_adjustment?: number
    logistics_cost?: number
    storage_cost?: number
    acceptance_cost?: number
    other_withholdings?: number
    penalties?: number
  }
  logistics_counts: {
    deliveries_qty?: number | null
    returns_log_qty?: number | null
    buyout_rate?: number | null
  }
  profitability?: {
    profit_per_unit?: number
    margin_pct_of_revenue?: number
    margin_pct_of_rrp?: number
    cogs_rule_text?: string
    markup_pct_of_cogs?: number
    rrp_missing?: boolean
    cogs_missing?: boolean
    cogs_per_unit?: number
    cogs_total?: number
  }
  extended_costs?: {
    packaging_cost_per_unit?: number | null
    packaging_cost_total?: number | null
    packaging_missing?: boolean
    product_additional_costs_total?: number
    marketplace_additional_costs_total?: number
    warehouse_labor_costs_total?: number
    additional_costs_total?: number
    additional_costs_per_unit?: number
  }
  debug?: {
    retail_price_nonzero_rows?: number
    spp_nonzero_rows?: number
    retail_amount_nonzero_rows?: number
  }
}

export interface WBFinanceReportSearchItem {
  report_id: number
  period_from: string | null
  period_to: string | null
  currency: string | null
  total_amount: number | null
  rows_count: number
  first_seen_at: string | null
  last_seen_at: string | null
}

export interface WBFinanceReportLatest {
  report_id: number
  period_from: string | null
  period_to: string | null
  currency: string | null
  total_amount: number | null
  rows_count: number
  first_seen_at: string
  last_seen_at: string
}

export async function getWBFinanceReportsLatest(
  projectId: string
): Promise<WBFinanceReportLatest | null> {
  try {
    const res = await apiGet<WBFinanceReportLatest>(
      `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/reports/latest`
    )
    return res.data
  } catch {
    return null
  }
}

export async function getWBFinanceReportsSearch(
  projectId: string,
  params: { query?: string; limit?: number }
): Promise<WBFinanceReportSearchItem[]> {
  const qs = new URLSearchParams()
  if (params.query) qs.set('query', params.query)
  if (params.limit != null) qs.set('limit', String(params.limit))
  const res = await apiGet<WBFinanceReportSearchItem[]>(
    `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/reports/search?${qs.toString()}`
  )
  return res.data
}

export async function getWBUnitPnl(
  projectId: string,
  params: {
    report_id?: number
    rr_dt_from?: string
    rr_dt_to?: string
    limit?: number
    offset?: number
    sort?: string
    order?: string
    q?: string
    category?: number
    filter_header?: boolean
  }
): Promise<WBUnitPnlResponse> {
  const qs = new URLSearchParams()
  if (params.report_id != null) qs.set('report_id', String(params.report_id))
  if (params.rr_dt_from) qs.set('rr_dt_from', params.rr_dt_from)
  if (params.rr_dt_to) qs.set('rr_dt_to', params.rr_dt_to)
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.offset != null) qs.set('offset', String(params.offset))
  if (params.sort) qs.set('sort', params.sort)
  if (params.order) qs.set('order', params.order)
  if (params.q) qs.set('q', params.q)
  if (params.category != null) qs.set('category', String(params.category))
  if (params.filter_header) qs.set('filter_header', '1')
  const res = await apiGet<WBUnitPnlResponse>(
    `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/unit-pnl?${qs.toString()}`
  )
  return res.data
}

export async function getWBUnitPnlDetails(
  projectId: string,
  nmId: number,
  params: { report_id?: number; rr_dt_from?: string; rr_dt_to?: string }
): Promise<WBUnitPnlDetailsResponse> {
  const qs = new URLSearchParams()
  if (params.report_id != null) qs.set('report_id', String(params.report_id))
  if (params.rr_dt_from) qs.set('rr_dt_from', params.rr_dt_from)
  if (params.rr_dt_to) qs.set('rr_dt_to', params.rr_dt_to)
  const res = await apiGet<WBUnitPnlDetailsResponse>(
    `/api/v1/projects/${projectId}/marketplaces/wildberries/finances/unit-pnl/${nmId}?${qs.toString()}`
  )
  return res.data
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
}

export async function getSeoCategories(projectId: string): Promise<SeoCategoryListItem[]> {
  const res = await apiGet<SeoCategoryListItem[]>(`/api/v1/projects/${projectId}/seo/categories`)
  return res.data
}

export async function getWBSkuPnl(
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

// Content analytics (funnel) summary
export interface ContentAnalyticsSummaryItem {
  nm_id: number
  opens: number
  add_to_cart: number
  cart_rate: number | null
  orders: number
  conversion: number | null
  revenue: number
}

export interface ContentAnalyticsSummaryResponse {
  items: ContentAnalyticsSummaryItem[]
}

export interface WBProductLookupItem {
  nm_id: number
  vendor_code: string | null
  title: string | null
  wb_category: string | null
}

export interface WBProductLookupResponse {
  items: WBProductLookupItem[]
}

export interface SalesTrendPoint {
  date: string
  orders: number
  revenue: number
  impressions: number
  card_clicks: number
  ctr_percent: number | null
  moving_average_orders: number
  moving_average_revenue: number
  moving_average_impressions: number
  moving_average_card_clicks: number
  moving_average_ctr_percent: number | null
}

export interface SalesTrendSeries {
  nm_id: number
  vendor_code: string | null
  title: string | null
  points: SalesTrendPoint[]
}

export interface SalesTrendsResponse {
  period_from: string
  period_to: string
  window_days: number
  series: SalesTrendSeries[]
}

export async function getWBSalesTrends(
  projectId: string,
  params: { period_from: string; period_to: string; nm_ids: number[]; window_days: number }
): Promise<SalesTrendsResponse> {
  const qs = new URLSearchParams()
  qs.set('period_from', params.period_from)
  qs.set('period_to', params.period_to)
  params.nm_ids.forEach((nmId) => qs.append('nm_ids', String(nmId)))
  qs.set('window_days', String(params.window_days))
  const res = await apiGet<SalesTrendsResponse>(
    `/api/v1/projects/${projectId}/wildberries/sales-trends?${qs.toString()}`
  )
  return res.data
}

export async function getWBProductLookup(
  projectId: string,
  params: { q: string; limit?: number }
): Promise<WBProductLookupResponse> {
  const qs = new URLSearchParams()
  qs.set('q', params.q)
  if (params.limit != null) qs.set('limit', String(params.limit))
  const res = await apiGet<WBProductLookupResponse>(
    `/api/v1/projects/${projectId}/wildberries/products/lookup?${qs.toString()}`
  )
  return res.data
}

export async function getSkuMeaningProductLookup(
  projectId: string,
  params: { q: string; limit?: number }
): Promise<WBProductLookupResponse> {
  const qs = new URLSearchParams()
  qs.set('q', params.q)
  if (params.limit != null) qs.set('limit', String(params.limit))
  const res = await apiGet<WBProductLookupResponse>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/products/lookup?${qs.toString()}`
  )
  return res.data
}

// --- SEO SKU Meaning Preview / Annotation Tool ---
export type SkuMeaningStatus = 'draft' | 'verified' | 'needs_more_data' | 'rejected'
export type SkuQueryJudgmentLabel =
  | 'highly_relevant'
  | 'maybe_relevant'
  | 'too_broad'
  | 'irrelevant'
  | 'conflict'
  | 'dangerous_claim'
  | 'manual_rejected'

export interface SkuMeaningPayload {
  schema_version: string
  functional: Record<string, any>
  expressive: Record<string, any>
  audience: string[]
  negative_constraints: string[]
  confidence: Record<string, number>
  evidence_refs: string[]
  review_status: SkuMeaningStatus
}

export interface SkuMeaningEvidencePack {
  schema_version: string
  project_id: number
  category_id: number
  nm_id: number
  evidence_hash: string
  product: Record<string, any>
  reviews: Array<{ ref: string; nm_id: number; rating: number | null; text: string; created_at: string | null }>
  category_prior: Record<string, any>
  product_projection: Record<string, any>
  product_projection_flags: Record<string, any>
  evidence_refs: Record<string, string>
  warnings: string[]
}

export interface SkuMeaningDraftResponse {
  meaning: SkuMeaningPayload
  evidence_hash: string
  cached: boolean
  model: string | null
  prompt_version: string
  artifact_path: string | null
  raw_response_preview: string | null
}

export interface SkuMeaningAnnotationResponse {
  id: number
  project_id: number
  category_id: number
  nm_id: number
  schema_version: string
  status: SkuMeaningStatus
  meaning: SkuMeaningPayload
  reviewer: string | null
  evidence_hash: string
  source_metadata: Record<string, any>
  draft_model: string | null
  draft_prompt_version: string | null
  draft_artifact_path: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SkuMeaningCandidateQuery {
  query_text: string
  normalized_query_text: string
  ranking_value_used: string | null
  bucket: string | null
  intent_type: string | null
  pruning_status: string | null
  query_id: number | null
  cluster_id: number | null
  cluster_key: string | null
  cluster_label_candidate: string | null
  existing_label: SkuQueryJudgmentLabel | null
  existing_rationale: string | null
}

export interface SkuMeaningCandidateQueriesResponse {
  project_id: number
  category_id: number
  nm_id: number
  items: SkuMeaningCandidateQuery[]
}

export interface SkuMeaningEvalExportResponse {
  schema_version: string
  project_id: number
  category_id: number | null
  exported_count: number
  format: 'jsonl' | 'csv'
  content: string
  items: Record<string, any>[]
}

export type QueryMeaningGenericness = 'specific' | 'broad' | 'generic'
export type MeaningAwareMatcherBucket = 'primary' | 'secondary' | 'broad' | 'rejected'

export interface QueryMeaningLibraryBuildResponse {
  project_id: number
  category_id: number
  total_clusters: number
  processed: number
  created: number
  updated: number
  skipped: number
  errors: number
  error_items: Array<Record<string, any>>
}

export interface QueryMeaningLibraryItem {
  id: number
  project_id: number
  category_id: number
  cluster_id: number | null
  cluster_key: string
  schema_version: string
  source_query_examples: string[]
  meaning_payload: Record<string, any>
  canonical_text: string
  genericness: QueryMeaningGenericness
  constraints: string[]
  conflicts_if_missing: string[]
  llm_model: string | null
  prompt_version: string
  input_hash: string
  status: string
  created_at: string | null
  updated_at: string | null
}

export interface QueryMeaningLibraryResponse {
  project_id: number
  category_id: number
  total: number
  items: QueryMeaningLibraryItem[]
}

export interface MeaningAwareMatcherItem {
  query: string
  cluster_id: number | null
  cluster_key: string | null
  query_meaning_id: number
  bucket: MeaningAwareMatcherBucket
  score: number
  semantic_similarity: number
  ranking_value_used: number | null
  genericness: QueryMeaningGenericness
  matched_meanings: string[]
  conflicts: string[]
  reasons: string[]
  user_bucket_label?: string | null
  user_reasons?: string[]
  matched_atoms?: string[]
  missing_atoms?: string[]
  conflict_atoms?: string[]
  debug_reasons?: string[]
}

export interface MeaningAwareMatcherResponse {
  project_id: number
  category_id: number
  nm_id: number
  sku_annotation_id: number
  sku_annotation_status: string
  buckets: Record<MeaningAwareMatcherBucket, MeaningAwareMatcherItem[]>
  diagnostics: {
    matcher_version: string
    query_meanings_total: number
    scored_total: number
    missing_library: boolean
    embedding_model: string | null
    atoms_version?: string | null
    atoms_gate_enabled?: boolean
    notes: string[]
  }
}

export type CategoryReadinessStatus =
  | 'not_started'
  | 'building'
  | 'ready_with_fallback'
  | 'ready_for_matching'
  | 'failed'

export interface CategoryBootstrapStatusResponse {
  project_id: number
  category_id: number
  readiness_status: CategoryReadinessStatus
  latest_run_id: number | null
  run_status: string | null
  current_step: string | null
  step_statuses: Record<string, any>
  queries_count: number
  clusters_count: number
  query_meanings_count: number
  query_atoms_count?: number
  embeddings_count: number
  category_axes_status: string
  last_error: string | null
  updated_at: string | null
}

export interface CategoryBootstrapRunResponse {
  run_id: number
  project_id: number
  category_id: number
  status: string
  readiness_status: CategoryReadinessStatus
}

export async function getSkuMeaningEvidence(
  projectId: string,
  nmId: number,
  params?: { category_id?: number }
): Promise<SkuMeaningEvidencePack> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<SkuMeaningEvidencePack>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/${nmId}/evidence${suffix}`
  )
  return res.data
}

export async function postSkuMeaningDraft(
  projectId: string,
  nmId: number,
  params?: { category_id?: number; force_refresh?: boolean }
): Promise<SkuMeaningDraftResponse> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  if (params?.force_refresh) qs.set('force_refresh', 'true')
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiPost<SkuMeaningDraftResponse>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/${nmId}/draft${suffix}`
  )
  return res.data
}

export async function getSkuMeaningAnnotation(
  projectId: string,
  nmId: number,
  params?: { category_id?: number }
): Promise<{ annotation: SkuMeaningAnnotationResponse | null }> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<{ annotation: SkuMeaningAnnotationResponse | null }>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/${nmId}/annotation${suffix}`
  )
  return res.data
}

export async function putSkuMeaningAnnotation(
  projectId: string,
  nmId: number,
  body: {
    category_id?: number | null
    meaning: SkuMeaningPayload
    status: SkuMeaningStatus
    evidence_hash: string
    reviewer?: string | null
    source_metadata?: Record<string, any>
    draft_model?: string | null
    draft_prompt_version?: string | null
    draft_artifact_path?: string | null
  }
): Promise<SkuMeaningAnnotationResponse> {
  const res = await apiPut<SkuMeaningAnnotationResponse>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/${nmId}/annotation`,
    body
  )
  return res.data
}

export async function getSkuMeaningCandidateQueries(
  projectId: string,
  nmId: number,
  params: { category_id?: number; limit?: number; search?: string }
): Promise<SkuMeaningCandidateQueriesResponse> {
  const qs = new URLSearchParams()
  if (params.category_id != null) qs.set('category_id', String(params.category_id))
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.search) qs.set('search', params.search)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<SkuMeaningCandidateQueriesResponse>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/${nmId}/candidate-queries${suffix}`
  )
  return res.data
}

export async function putSkuMeaningQueryJudgments(
  projectId: string,
  nmId: number,
  body: {
    category_id?: number | null
    annotation_id?: number | null
    items: Array<{
      query_text: string
      normalized_query_text?: string | null
      query_id?: number | null
      cluster_id?: number | null
      cluster_key?: string | null
      label: SkuQueryJudgmentLabel
      rationale?: string | null
      reviewer?: string | null
      matcher_version?: string | null
      source?: string
    }>
  }
): Promise<{ items: any[] }> {
  const res = await apiPut<{ items: any[] }>(
    `/api/v1/projects/${projectId}/seo/sku-meaning/${nmId}/query-judgments`,
    body
  )
  return res.data
}

export async function postSkuMeaningEvalExport(
  projectId: string,
  body: {
    category_id?: number | null
    nm_ids?: number[] | null
    include_drafts?: boolean
    format?: 'jsonl' | 'csv'
  }
): Promise<SkuMeaningEvalExportResponse> {
  const res = await apiPost<SkuMeaningEvalExportResponse>(
    `/api/v1/projects/${projectId}/seo/eval-datasets/export`,
    body
  )
  return res.data
}

export async function postQueryMeaningLibraryBuild(
  projectId: string,
  body: { category_id: number; limit?: number; force_refresh?: boolean; use_llm?: boolean }
): Promise<QueryMeaningLibraryBuildResponse> {
  const res = await apiPost<QueryMeaningLibraryBuildResponse>(
    `/api/v1/projects/${projectId}/seo/query-meaning-library/build`,
    body
  )
  return res.data
}

export async function getQueryMeaningLibrary(
  projectId: string,
  params: { category_id: number; limit?: number; offset?: number; status?: string }
): Promise<QueryMeaningLibraryResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.offset != null) qs.set('offset', String(params.offset))
  if (params.status) qs.set('status', params.status)
  const res = await apiGet<QueryMeaningLibraryResponse>(
    `/api/v1/projects/${projectId}/seo/query-meaning-library?${qs.toString()}`
  )
  return res.data
}

export async function postMeaningAwareMatcherPreview(
  projectId: string,
  body: { category_id: number; nm_id: number; limit?: number; include_rejected?: boolean }
): Promise<MeaningAwareMatcherResponse> {
  const res = await apiPost<MeaningAwareMatcherResponse>(
    `/api/v1/projects/${projectId}/seo/meaning-aware-matcher/preview`,
    body
  )
  return res.data
}

export async function getCategoryBootstrapStatus(
  projectId: string,
  params: { category_id: number }
): Promise<CategoryBootstrapStatusResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  const res = await apiGet<CategoryBootstrapStatusResponse>(
    `/api/v1/projects/${projectId}/seo/category-bootstrap/status?${qs.toString()}`
  )
  return res.data
}

export async function postCategoryBootstrapRun(
  projectId: string,
  body: { category_id: number; force_refresh?: boolean; use_llm?: boolean }
): Promise<CategoryBootstrapRunResponse> {
  const res = await apiPost<CategoryBootstrapRunResponse>(
    `/api/v1/projects/${projectId}/seo/category-bootstrap/run`,
    body
  )
  return res.data
}

export interface SeoProductListItem {
  nm_id: number
  vendor_code: string | null
  article?: string | null
  title: string | null
  name?: string | null
  photo_url?: string | null
  brand: string | null
  category_id: number | null
  category_name: string | null
  subject_id?: number | null
  subject_name?: string | null
  rating: number | null
  feedbacks: number | null
  review_count?: number | null
  stock_quantity?: number | null
  in_stock?: boolean | null
  analysis_status: string
  category_status: string | null
  has_sku_meaning: boolean
  has_sku_atoms: boolean
  has_vision_atoms: boolean
}

export interface SeoProductListResponse {
  project_id: number
  total: number
  items: SeoProductListItem[]
}

export interface SeoReadableBlock {
  title: string
  items: string[]
  empty_text: string | null
}

export interface SeoProductSummaryResponse {
  project_id: number
  nm_id: number
  category_id: number
  product: Record<string, any>
  product_status_label: string
  category_status_label: string
  vision_status_label: string
  blocks: SeoReadableBlock[]
  diagnostics: Record<string, any>
  quality_mode?: SeoQualityMode | null
  degraded_reasons?: SeoQualityReason[]
}

export interface SeoProductAnalysisRunResponse {
  project_id: number
  nm_id: number
  category_id: number
  status: string
  product_status_label: string
  vision_status_label: string
  annotation_id: number | null
  evidence_hash: string | null
  warnings: string[]
}

export interface SeoProductAnalysisStatusResponse {
  project_id: number
  nm_id: number
  category_id: number | null
  status: string
  product_status_label: string
  has_sku_meaning: boolean
  has_sku_atoms: boolean
  has_vision_atoms: boolean
}

export interface SeoProductReadinessItem {
  key: string
  label: string
  ready: boolean
  details: string | null
}

export interface SeoProductAiVisionVerdict {
  ready: boolean
  status: string | null
  label: string
  items: string[]
  image_urls: string[]
  prompt_version?: string | null
  input_prompt?: string | null
  evidence_block?: string | null
}

export interface SeoProductQuerySetSummary {
  query_set_id: number
  status: string
  approval_state: string | null
  trust_state: string | null
  items_total: number
  selected_items: number
  approved: boolean
  updated_at: string | null
}

export interface SeoProductReadinessResponse {
  project_id: number
  nm_id: number
  category_id: number | null
  product_card_exists: boolean
  category_id_known: boolean
  query_count: number
  normalized_query_count: number
  cluster_count: number
  expressive_prior_ready: boolean
  ai_vision: SeoProductAiVisionVerdict
  existing_query_set: SeoProductQuerySetSummary | null
  readiness: SeoProductReadinessItem[]
  can_select_queries: boolean
  blocking_reasons: string[]
}

export interface SeoProductionProductBlock {
  nm_id: number
  title: string | null
  description: string | null
  product_type?: string | null
  dimensions: Record<string, any>
  characteristics: Array<Record<string, any>>
}

export interface SeoProductionCategoryBlock {
  category_id: number
  query_count: number
  cluster_count: number
  expressive_prior_axes: Record<string, any>
}

export interface SeoProductionCandidate {
  cluster_id: number | null
  cluster_key: string | null
  query: string
  frequency: number | null
  ranking_value: number | null
  meaning_line: string | null
  sku_relevance_score: number | null
}

export interface SeoProductionMeaningLine {
  line: string
  evidence: string[]
  coverage_status: string
}

export interface SeoProductionQuerySelectionPreviewResponse {
  project_id: number
  nm_id: number
  category_id: number
  product: SeoProductionProductBlock
  category: SeoProductionCategoryBlock
  ai_vision: SeoProductAiVisionVerdict
  candidates: {
    candidate_count: number
    total_candidate_count: number
    display_candidate_count: number
    sent_candidate_count: number
    preview_limit: number
    items: SeoProductionCandidate[]
  }
  readiness: {
    can_run: boolean
    blocking_reasons: string[]
  }
  prompt_version?: string | null
  input_prompt?: string | null
}

export interface SeoProductionSelectedQuery {
  query: string
  status: string
  risk: string | null
  explanation: string
  cluster_id: number | null
  meaning_line: string | null
  frequency: number | null
  confidence: number | null
}

export interface SeoProductionOperatorCandidate {
  meaning_line: string
  query: string
  status: string
  risk: string | null
  explanation: string
  cluster_id: number | null
  frequency: number | null
  confidence: number | null
}

export interface SeoProductionQuerySelectionRunResponse {
  run_id: number
  project_id: number
  nm_id: number
  category_id: number
  status: string
  meaning_lines: SeoProductionMeaningLine[]
  selected_queries: SeoProductionSelectedQuery[]
  operator_candidates: Record<string, SeoProductionOperatorCandidate[]>
  model: string | null
  prompt_version: string
  artifact_path: string | null
  candidate_count: number
  sent_candidate_count: number
  input_prompt?: string | null
}

export interface SeoQuerySelectionItem {
  id: number | null
  normalized_query_text: string
  display_query: string
  cluster_key: string | null
  bucket: MeaningAwareMatcherBucket
  user_bucket_label: string
  score: number
  ranking_value_used: number | null
  selection_state: 'auto_selected' | 'pinned' | 'excluded'
  user_reasons: string[]
  matched_atoms: string[]
  missing_atoms: string[]
  conflict_atoms: string[]
}

export interface SeoQuerySetResponse {
  id: number | null
  project_id: number
  category_id: number
  nm_id: number
  status: 'draft' | 'confirmed'
  matcher_version: string | null
  atoms_version: string | null
  items: SeoQuerySelectionItem[]
  matcher?: MeaningAwareMatcherResponse | null
  quality_mode?: SeoQualityMode | null
  degraded_reasons?: SeoQualityReason[]
  matcher_run_id?: number | null
}

export interface SeoCategorySelectedQueryItem {
  id: number
  query_text: string
  sort_order: number
  source: 'category_list' | 'saved_sku' | string
  sku_count: number
  ranking_value_used: number | null
  created_at: string | null
  updated_at: string | null
}

export interface SeoCategorySelectedQueryListResponse {
  project_id: number
  category_id: number
  total: number
  items: SeoCategorySelectedQueryItem[]
}

export type SeoGenerationBrandVoice = 'экспертный' | 'тёплый' | 'минималистичный' | 'игривый'

export interface GeneratedCharacteristic {
  field: string
  value: string
}

export interface GeneratedCard {
  title: string
  characteristics: GeneratedCharacteristic[]
  description: string
  report: Record<string, any>
}

export interface GenerationValidationIssue {
  check_name: string
  severity: 'error' | 'warning'
  message: string
  details: Record<string, any>
}

export interface SeoRelevanceQueryCoverage {
  query: string
  bucket: string
  weight: number
  found: boolean
  zones: string[]
  occurrences: number
}

export interface SeoRelevanceReport {
  score: number
  grade: 'high' | 'medium' | 'low'
  main_query_text: string | null
  main_query_in_title: boolean
  main_query_in_title_start: boolean
  weighted_coverage: number
  selected_queries_count: number
  covered_queries_count: number
  title_queries_count: number
  description_queries_count: number
  overused_queries: string[]
  missing_primary_queries: string[]
  query_coverage: SeoRelevanceQueryCoverage[]
  notes: string[]
}

export interface SeoRelevanceV2QueryScore {
  query: string
  bucket: string
  weight: number
  score: number
  intent_score: number
  semantic_score: number
  lexical_score: number
  zone_score: number
  naturalness_score: number
  supported_atoms: string[]
  unsupported_atoms: string[]
  conflict_atoms: string[]
  zones: string[]
  notes: string[]
}

export interface SeoRelevanceV2Report {
  version: 'seo_relevance_v2'
  score: number
  grade: 'high' | 'medium' | 'low'
  main_query_text: string | null
  intent_fit: number
  semantic_similarity: number
  lexical_relevance: number
  zone_placement: number
  naturalness: number
  product_truthfulness: number
  evaluated_queries_count: number
  strong_queries_count: number
  weak_queries: string[]
  unsupported_intents: string[]
  query_scores: SeoRelevanceV2QueryScore[]
  notes: string[]
}

export type SeoQualityMode = 'full' | 'preview' | 'degraded' | 'fallback'

export interface SeoQualityReason {
  code: string
  details?: Record<string, any>
}

export interface SeoFeatureFlags {
  generation_preview_enabled: boolean
  generation_max_attempts: number
  generation_publishable: boolean
}

/**
 * @deprecated Iteration 1 renamed to {@link SeoFeatureFlags} to match the
 * backend contract at `/api/v1/seo/feature-flags`.
 */
export type SeoGenerationConfig = SeoFeatureFlags

export interface SeoGenerationRunResponse {
  project_id: number
  category_id: number
  nm_id: number
  run_id: number
  query_set_id: number | null
  content_version_id: number | null
  status: 'completed' | 'needs_review' | 'failed'
  content_status: string | null
  provider_name: string | null
  model_name: string | null
  attempts: number
  prompt_version: string
  validator_version: string
  generated_card: GeneratedCard | null
  validation_results: GenerationValidationIssue[]
  seo_relevance: SeoRelevanceReport | null
  seo_relevance_v2: SeoRelevanceV2Report | null
  error_text: string | null
  quality_mode?: SeoQualityMode | null
  degraded_reasons?: SeoQualityReason[]
  mode_used?: string | null
  publishable?: boolean
  matcher_run_id?: number | null
  strategy?: 'two_pass' | 'single_pass_sonnet'
  single_pass_validation?: Record<string, any> | null
}

export interface SeoGenerationPromptPreviewResponse {
  project_id: number
  category_id: number
  nm_id: number
  query_set_id: number
  query_set_status: string
  provider_name: string
  model_name: string
  prompt_version: string
  system_prompt: string
  user_prompt: string
}

export interface SeoGenerationLatestResponse {
  project_id: number
  category_id: number
  nm_id: number
  content_version_id: number | null
  generation_run_id: number | null
  status: string | null
  title: string | null
  description: string | null
  query_snapshot: Record<string, any>
  score_breakdown: Record<string, any>
  response_payload: Record<string, any>
  seo_relevance: SeoRelevanceReport | null
  seo_relevance_v2: SeoRelevanceV2Report | null
  error_text: string | null
  quality_mode?: SeoQualityMode | null
  degraded_reasons?: SeoQualityReason[]
  mode_used?: string | null
  publishable?: boolean
  matcher_run_id?: number | null
}

export async function getSeoProducts(
  projectId: string,
  params?: { category_id?: number; q?: string; analysis_status?: string; stock_status?: string; limit?: number; offset?: number }
): Promise<SeoProductListResponse> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  if (params?.q) qs.set('q', params.q)
  if (params?.analysis_status) qs.set('analysis_status', params.analysis_status)
  if (params?.stock_status) qs.set('stock_status', params.stock_status)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<SeoProductListResponse>(`/api/v1/projects/${projectId}/seo/products${suffix}`)
  return res.data
}

export async function getSeoProductSummary(
  projectId: string,
  nmId: number,
  params?: { category_id?: number }
): Promise<SeoProductSummaryResponse> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<SeoProductSummaryResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/seo-summary${suffix}`)
  return res.data
}

export async function postSeoProductAnalysisRun(
  projectId: string,
  nmId: number,
  body: { category_id?: number | null; force_refresh?: boolean; include_vision?: boolean; selected_image_urls?: string[] }
): Promise<SeoProductAnalysisRunResponse> {
  const res = await apiPost<SeoProductAnalysisRunResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/analysis/run`, body)
  return res.data
}

export async function getSeoProductAnalysisStatus(
  projectId: string,
  nmId: number,
  params?: { category_id?: number }
): Promise<SeoProductAnalysisStatusResponse> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<SeoProductAnalysisStatusResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/analysis/status${suffix}`)
  return res.data
}

export async function getSeoProductReadiness(
  projectId: string,
  nmId: number,
  params?: { category_id?: number }
): Promise<SeoProductReadinessResponse> {
  const qs = new URLSearchParams()
  if (params?.category_id != null) qs.set('category_id', String(params.category_id))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<SeoProductReadinessResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/readiness${suffix}`)
  return res.data
}

export async function postSeoQuerySelectionRun(
  projectId: string,
  nmId: number,
  body: { category_id: number; limit?: number; include_rejected?: boolean }
): Promise<SeoQuerySetResponse> {
  const res = await apiPost<SeoQuerySetResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/legacy-run`, body)
  return res.data
}

export async function getSeoProductionQuerySelectionPreview(
  projectId: string,
  nmId: number,
  params: { category_id: number },
): Promise<SeoProductionQuerySelectionPreviewResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  const res = await apiGet<SeoProductionQuerySelectionPreviewResponse>(
    `/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/preview?${qs.toString()}`,
  )
  return res.data
}

export async function postSeoProductionQuerySelectionRun(
  projectId: string,
  nmId: number,
  params: { category_id: number },
): Promise<SeoProductionQuerySelectionRunResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  const res = await apiPost<SeoProductionQuerySelectionRunResponse>(
    `/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/run?${qs.toString()}`,
  )
  return res.data
}

export async function getSeoProductionQuerySelectionLatest(
  projectId: string,
  nmId: number,
  params: { category_id: number },
): Promise<SeoProductionQuerySelectionRunResponse | null> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  const res = await apiGet<SeoProductionQuerySelectionRunResponse | null>(
    `/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/latest-production?${qs.toString()}`,
  )
  return res.data
}

export async function postSeoProductionQuerySelectionSave(
  projectId: string,
  nmId: number,
  body: {
    category_id: number
    run_id?: number | null
    status?: 'draft' | 'confirmed'
    items: Array<{
      query: string
      selected: boolean
      frequency?: number | null
      meaning_line?: string | null
      risk?: string | null
      confidence?: number | null
      explanation?: string | null
      source?: string
    }>
  },
): Promise<SeoQuerySetResponse> {
  const res = await apiPost<SeoQuerySetResponse>(
    `/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/save-production`,
    body,
  )
  return res.data
}

export async function getSeoCategorySelectedQueries(
  projectId: string,
  categoryId: number,
): Promise<SeoCategorySelectedQueryListResponse> {
  const qs = new URLSearchParams()
  qs.set('_ts', String(Date.now()))
  const res = await apiGet<SeoCategorySelectedQueryListResponse>(
    `/api/v1/projects/${projectId}/seo/categories/${categoryId}/selected-queries?${qs.toString()}`,
  )
  return res.data
}

export async function putSeoCategorySelectedQueries(
  projectId: string,
  categoryId: number,
  body: { queries: string[] },
): Promise<SeoCategorySelectedQueryListResponse> {
  const res = await apiPut<SeoCategorySelectedQueryListResponse>(
    `/api/v1/projects/${projectId}/seo/categories/${categoryId}/selected-queries`,
    body,
  )
  return res.data
}

export async function postSeoApplyCategorySelectedQueries(
  projectId: string,
  nmId: number,
  body: { category_id: number; query_texts?: string[] },
): Promise<SeoQuerySetResponse> {
  const res = await apiPost<SeoQuerySetResponse>(
    `/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/apply-category-list`,
    body,
  )
  return res.data
}

export async function postSeoQuerySelectionLegacyRun(
  projectId: string,
  nmId: number,
  body: { category_id: number; limit?: number; include_rejected?: boolean }
): Promise<SeoQuerySetResponse> {
  const res = await apiPost<SeoQuerySetResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection/legacy-run`, body)
  return res.data
}

export async function getSeoQuerySelection(
  projectId: string,
  nmId: number,
  params: { category_id: number }
): Promise<SeoQuerySetResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  const res = await apiGet<SeoQuerySetResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection?${qs.toString()}`)
  return res.data
}

export async function putSeoQuerySelection(
  projectId: string,
  nmId: number,
  body: {
    category_id: number
    status?: 'draft' | 'confirmed'
    items: Array<{ normalized_query_text: string; selection_state: 'auto_selected' | 'pinned' | 'excluded' }>
  }
): Promise<SeoQuerySetResponse> {
  const res = await apiPut<SeoQuerySetResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/query-selection`, body)
  return res.data
}

export async function postSeoGenerationRun(
  projectId: string,
  nmId: number,
  body: {
    category_id: number
    query_set_id?: number | null
    main_query_text?: string | null
    brand_voice?: SeoGenerationBrandVoice
    strategy?: 'two_pass' | 'single_pass_sonnet'
    force_refresh?: boolean
  }
): Promise<SeoGenerationRunResponse> {
  const res = await apiPost<SeoGenerationRunResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/generation/run`, body)
  return res.data
}

export async function postSeoGenerationPromptPreview(
  projectId: string,
  nmId: number,
  body: {
    category_id: number
    query_set_id?: number | null
    main_query_text?: string | null
    brand_voice?: SeoGenerationBrandVoice
  }
): Promise<SeoGenerationPromptPreviewResponse> {
  const res = await apiPost<SeoGenerationPromptPreviewResponse>(
    `/api/v1/projects/${projectId}/seo/products/${nmId}/generation/prompt-preview`,
    body,
  )
  return res.data
}

export async function getSeoGenerationLatest(
  projectId: string,
  nmId: number,
  params: { category_id: number }
): Promise<SeoGenerationLatestResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  const res = await apiGet<SeoGenerationLatestResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/generation/latest?${qs.toString()}`)
  return res.data
}

export async function postSeoGenerationRecalculateSeoV2(
  projectId: string,
  nmId: number,
  body: { category_id: number }
): Promise<SeoGenerationLatestResponse> {
  const res = await apiPost<SeoGenerationLatestResponse>(`/api/v1/projects/${projectId}/seo/products/${nmId}/generation/recalculate-seo-v2`, body)
  return res.data
}

export async function getSeoFeatureFlags(projectId?: string): Promise<SeoFeatureFlags> {
  const path = projectId ? `/api/v1/projects/${projectId}/seo/feature-flags` : `/api/v1/seo/feature-flags`
  const res = await apiGet<SeoFeatureFlags>(path)
  return res.data
}

/**
 * @deprecated Iteration 1 renamed to {@link getSeoFeatureFlags}.
 */
export const getSeoGenerationConfig = getSeoFeatureFlags

// ---------------------------------------------------------------------------
// Iteration 1: candidate matcher (matcher_v2) — additive API surface.
// ---------------------------------------------------------------------------

export interface MatcherV2RunRequest {
  category_id: number
  nm_id: number
  limit?: number
  include_rejected?: boolean
}

export interface MatcherV2RunResponse {
  run_id: number
  quality_mode: SeoQualityMode
  degraded_reasons: SeoQualityReason[]
  response: MeaningAwareMatcherResponse
}

export interface MatcherV2ResultItem {
  id: number
  query_meaning_id: number | null
  cluster_key: string | null
  query_display: string
  normalized_query_text: string
  bucket: string
  eligibility_verdict: string
  score: number
  score_components: Record<string, number>
  matched_atoms: string[]
  missing_atoms: string[]
  conflict_atoms: string[]
  reasons: string[]
  ranking_value_used: number | null
  semantic_similarity: number | null
  created_at: string
}

export interface MatcherV2RunDetailResponse {
  run_id: number
  project_id: number
  category_id: number
  nm_id: number
  matcher_version: string
  policy_version: string
  category_profile_version: string
  sku_atoms_id: number | null
  vision_atoms_id: number | null
  query_atoms_version: string | null
  embedding_model: string | null
  readiness_snapshot: Record<string, any>
  quality_mode: SeoQualityMode | null
  degraded_reasons: SeoQualityReason[]
  metrics: Record<string, any>
  error: Record<string, any> | null
  started_at: string
  completed_at: string | null
  results: MatcherV2ResultItem[]
}

export async function postSeoMatcherV2Run(
  projectId: string,
  body: MatcherV2RunRequest,
): Promise<MatcherV2RunResponse> {
  const res = await apiPost<MatcherV2RunResponse>(
    `/api/v1/projects/${projectId}/seo/matcher/v2/run`,
    body,
  )
  return res.data
}

export async function getSeoMatcherV2Run(
  projectId: string,
  runId: number,
): Promise<MatcherV2RunDetailResponse> {
  const res = await apiGet<MatcherV2RunDetailResponse>(
    `/api/v1/projects/${projectId}/seo/matcher/v2/runs/${runId}`,
  )
  return res.data
}

export async function getContentAnalyticsSummary(
  projectId: string,
  params: { period_from: string; period_to: string; nm_id?: number }
): Promise<ContentAnalyticsSummaryResponse> {
  const qs = new URLSearchParams()
  qs.set('period_from', params.period_from)
  qs.set('period_to', params.period_to)
  if (params.nm_id != null && !Number.isNaN(params.nm_id)) qs.set('nm_id', String(params.nm_id))
  const res = await apiGet<ContentAnalyticsSummaryResponse>(
    `/api/v1/projects/${projectId}/wildberries/content-analytics/summary?${qs.toString()}`
  )
  return res.data
}

// Reviews summary
export interface ReviewsSummaryItem {
  nm_id: number
  title: string | null
  wb_category: string | null
  image_url: string | null
  vendor_code: string | null
  avg_rating: number | null
  reviews_count_total: number
  new_reviews: number | null
}

export interface ReviewsSummaryResponse {
  items: ReviewsSummaryItem[]
}

export interface ReviewDetailItem {
  external_id: string
  nm_id: number
  created_date: string | null
  rating: number | null
  user_name: string | null
  text: string | null
  pros: string | null
  cons: string | null
  answer_text: string | null
  photo_urls: string[]
  video_url: string | null
  is_answered: boolean
  has_media: boolean
  is_archived: boolean
  source_endpoint: string | null
}

export interface ReviewsListResponse {
  items: ReviewDetailItem[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export async function getReviewsSummary(
  projectId: string,
  params: {
    period_from?: string
    period_to?: string
    nm_id?: number
    vendor_code?: string
    wb_category?: string
    rating_lte?: number
    only_enterprise_gt0?: boolean
    only_fbo_gt0?: boolean
    only_with_reviews_in_period?: boolean
  }
): Promise<ReviewsSummaryResponse> {
  const qs = new URLSearchParams()
  if (params.period_from != null && params.period_from !== '') qs.set('period_from', params.period_from)
  if (params.period_to != null && params.period_to !== '') qs.set('period_to', params.period_to)
  if (params.nm_id != null && !Number.isNaN(params.nm_id)) qs.set('nm_id', String(params.nm_id))
  if (params.vendor_code != null && params.vendor_code.trim() !== '') qs.set('vendor_code', params.vendor_code.trim())
  if (params.wb_category != null && params.wb_category !== '') qs.set('wb_category', params.wb_category)
  if (params.rating_lte != null && !Number.isNaN(params.rating_lte)) qs.set('rating_lte', String(params.rating_lte))
  if (params.only_enterprise_gt0) qs.set('only_enterprise_gt0', 'true')
  if (params.only_fbo_gt0) qs.set('only_fbo_gt0', 'true')
  if (params.only_with_reviews_in_period) qs.set('only_with_reviews_in_period', 'true')
  const res = await apiGet<ReviewsSummaryResponse>(
    `/api/v1/projects/${projectId}/wildberries/reviews/summary?${qs.toString()}`
  )
  return res.data
}

export async function getReviewsList(
  projectId: string,
  params: {
    nm_id: number
    period_from?: string
    period_to?: string
    limit?: number
    offset?: number
  }
): Promise<ReviewsListResponse> {
  const qs = new URLSearchParams()
  qs.set('nm_id', String(params.nm_id))
  if (params.period_from != null && params.period_from !== '') qs.set('period_from', params.period_from)
  if (params.period_to != null && params.period_to !== '') qs.set('period_to', params.period_to)
  if (params.limit != null && !Number.isNaN(params.limit)) qs.set('limit', String(params.limit))
  if (params.offset != null && !Number.isNaN(params.offset)) qs.set('offset', String(params.offset))
  const res = await apiGet<ReviewsListResponse>(
    `/api/v1/projects/${projectId}/wildberries/reviews/items?${qs.toString()}`
  )
  return res.data
}

// Funnel signals
export interface FunnelSignalsItem {
  nm_id: number
  title: string | null
  wb_category: string | null
  image_url: string | null
  vendor_code: string | null
  fbo_stock_qty?: number | null
  fbo_stock_updated_at?: string | null
  enterprise_stock_qty?: number | null
  enterprise_stock_updated_at?: string | null
  opens: number
  carts: number
  orders: number
  revenue: number
  cart_rate: number | null
  order_rate: number | null
  cart_to_order: number | null
  avg_check: number | null
  impressions: number
  card_clicks: number
  funnel_ctr_percent: number | null
  active_days_with_impressions: number
  quality_excluded_rows: number
  ctr_sample_tier: 'insufficient' | 'indicative' | 'reliable' | 'high_sample'
  ctr_quality_flags: string[]
  signal_code: string
  signal: string
  signal_label: string
  severity: 'low' | 'med' | 'high' | null
  potential_rub: number
  bucket: 'low' | 'mid' | 'high' | null
  signal_details: string | null
}

export interface FunnelSignalsResponse {
  items: FunnelSignalsItem[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface FunnelSignalsCategoryItem {
  wb_category: string
  products_cnt: number
}

export async function getFunnelSignals(
  projectId: string,
  params: {
    period_from: string
    period_to: string
    min_opens?: number
    only_cart_gt0?: boolean
    only_enterprise_gt0?: boolean
    only_fbo_gt0?: boolean
    wb_category?: string
    signal_code?: string
    ctr_mode?: 'raw' | 'quality_filtered'
    page?: number
    page_size?: number
    sort?: string
    order?: 'asc' | 'desc'
  }
): Promise<FunnelSignalsResponse> {
  const qs = new URLSearchParams()
  qs.set('period_from', params.period_from)
  qs.set('period_to', params.period_to)
  if (params.min_opens != null && !Number.isNaN(params.min_opens)) {
    qs.set('min_opens', String(params.min_opens))
  }
  if (params.only_cart_gt0 === true) qs.set('only_cart_gt0', 'true')
  if (params.only_enterprise_gt0 === true) qs.set('only_enterprise_gt0', 'true')
  if (params.only_fbo_gt0 === true) qs.set('only_fbo_gt0', 'true')
  if (params.wb_category != null && params.wb_category !== '') qs.set('wb_category', params.wb_category)
  if (params.signal_code != null && params.signal_code !== '') qs.set('signal_code', params.signal_code)
  if (params.ctr_mode != null) qs.set('ctr_mode', params.ctr_mode)
  if (params.page != null && params.page >= 1) qs.set('page', String(params.page))
  if (params.page_size != null && params.page_size >= 1) qs.set('page_size', String(params.page_size))
  if (params.sort != null && params.sort !== '') qs.set('sort', params.sort)
  if (params.order != null) qs.set('order', params.order)
  const res = await apiGet<FunnelSignalsResponse>(
    `/api/v1/projects/${projectId}/wildberries/analytics/funnel-signals?${qs.toString()}`
  )
  return res.data
}

export interface WBFunnelImportResponse {
  id: number
  original_filename: string
  source_type: string
  period_from: string
  period_to: string
  rows_total: number
  quality_summary: { flag_counts?: Record<string, number>; warning_rows?: number }
  duplicate: boolean
}

export async function uploadWBFunnelReport(projectId: string, file: File): Promise<WBFunnelImportResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await apiRequest<WBFunnelImportResponse>(
    `/api/v1/projects/${projectId}/wildberries/funnel-report/import`,
    { method: 'POST', body: form }
  )
  return res.data
}

export async function getFunnelSignalsCategories(projectId: string): Promise<string[]> {
  const res = await apiGet<string[]>(
    `/api/v1/projects/${projectId}/wildberries/analytics/funnel-signals/categories`
  )
  return res.data
}

export async function getFunnelSignalsCategoriesStats(
  projectId: string,
  params: {
    period_from: string
    period_to: string
    min_opens?: number
    only_cart_gt0?: boolean
    only_enterprise_gt0?: boolean
    only_fbo_gt0?: boolean
    signal_code?: string
  }
): Promise<FunnelSignalsCategoryItem[]> {
  const qs = new URLSearchParams()
  qs.set('period_from', params.period_from)
  qs.set('period_to', params.period_to)
  if (params.min_opens != null && !Number.isNaN(params.min_opens)) {
    qs.set('min_opens', String(params.min_opens))
  }
  if (params.only_cart_gt0 === true) qs.set('only_cart_gt0', 'true')
  if (params.only_enterprise_gt0 === true) qs.set('only_enterprise_gt0', 'true')
  if (params.only_fbo_gt0 === true) qs.set('only_fbo_gt0', 'true')
  if (params.signal_code != null && params.signal_code !== '') qs.set('signal_code', params.signal_code)
  const res = await apiGet<FunnelSignalsCategoryItem[]>(
    `/api/v1/projects/${projectId}/wildberries/analytics/funnel-signals/categories-stats?${qs.toString()}`
  )
  return res.data
}

// Order geography
export type OrderGeographyGroupBy = 'country' | 'region' | 'city' | 'ppvz' | 'office'

export interface OrderGeographySummary {
  orders: number
  gross_sales: number
  countries: number
  regions: number
  cities: number
  ppvz_count: number
  top_region: string | null
}

export interface OrderGeographyItem {
  country: string | null
  region: string | null
  city: string | null
  ppvz_office_id: string | null
  ppvz_office_name: string | null
  office_name: string | null
  orders: number
  share: number
  gross_sales: number
  unique_nm_ids: number
  top_nm_id: number | null
  top_nm_orders: number
  first_order_date: string | null
  last_order_date: string | null
}

export interface OrderGeographyResponse {
  summary: OrderGeographySummary
  items: OrderGeographyItem[]
  group_by: OrderGeographyGroupBy
  limit: number
  total_groups: number
}

export async function getOrderGeography(
  projectId: string,
  params: {
    period_from: string
    period_to: string
    group_by?: OrderGeographyGroupBy
    country?: string
    nm_id?: number
    vendor_code?: string
    office_name?: string
    limit?: number
  }
): Promise<OrderGeographyResponse> {
  const qs = new URLSearchParams()
  qs.set('period_from', params.period_from)
  qs.set('period_to', params.period_to)
  if (params.group_by != null) qs.set('group_by', params.group_by)
  if (params.country != null && params.country !== '') qs.set('country', params.country)
  if (params.nm_id != null && !Number.isNaN(params.nm_id)) qs.set('nm_id', String(params.nm_id))
  if (params.vendor_code != null && params.vendor_code !== '') qs.set('vendor_code', params.vendor_code)
  if (params.office_name != null && params.office_name !== '') qs.set('office_name', params.office_name)
  if (params.limit != null && !Number.isNaN(params.limit)) qs.set('limit', String(params.limit))
  const res = await apiGet<OrderGeographyResponse>(
    `/api/v1/projects/${projectId}/wildberries/order-geography?${qs.toString()}`
  )
  return res.data
}

// --- Hypothesis Lab v5.1 MVP ---
export interface HypothesisLabRunSummary {
  id: number
  experiment_id: number
  status: string
  effective_start_ts: string | null
  baseline_start_date: string | null
  baseline_end_date: string | null
  test_start_date: string | null
  test_end_date: string | null
  control_mode: string
  analysis_population: string
  computed_at: string | null
  created_at: string
  experiment_name: string
  project_id: number
  marketplace: string
}

export interface HypothesisLabRunDetail extends HypothesisLabRunSummary {
  washout_start_date?: string | null
  washout_end_date?: string | null
  pretrend_window_days?: number | null
  pretrend_status?: string | null
  scope_nm_ids: number[]
  actions: Record<string, unknown>[]
  control_items: Record<string, unknown>[]
  context_events: Record<string, unknown>[]
  latest_result: Record<string, unknown> | null
  metric_aggregates: Record<string, unknown> | null
  health_reasons?: Record<string, unknown> | null
  warnings_text_array?: string[] | null
  limitations_flags_jsonb?: Record<string, unknown> | null
}

export interface HypothesisLabResultItem {
  run_id: number
  result_version: number
  computed_at: string
  primary_metric_key: string | null
  decision: string | null
  did_effect_pct: number | null
  did_ci_lower: number | null
  did_ci_upper: number | null
  health_grade: string | null
  health_reasons_jsonb: Record<string, unknown> | null
  limitations_flags_jsonb: Record<string, unknown> | null
  warnings_text_array: string[] | null
  experiment_id: number
  experiment_name: string
}

export async function getHypothesisLabRuns(
  projectId: string,
  params?: { marketplace?: string; status?: string }
): Promise<HypothesisLabRunSummary[]> {
  const qs = new URLSearchParams()
  if (params?.marketplace) qs.set('marketplace', params.marketplace)
  if (params?.status) qs.set('status', params.status)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<HypothesisLabRunSummary[]>(
    `/api/v1/projects/${projectId}/hypothesis-lab/runs${suffix}`
  )
  return res.data
}

export async function getHypothesisLabRunDetail(
  projectId: string,
  runId: number
): Promise<HypothesisLabRunDetail> {
  const res = await apiGet<HypothesisLabRunDetail>(
    `/api/v1/projects/${projectId}/hypothesis-lab/runs/${runId}`
  )
  return res.data
}

export async function getHypothesisLabResults(
  projectId: string,
  params?: { marketplace?: string; limit?: number }
): Promise<HypothesisLabResultItem[]> {
  const qs = new URLSearchParams()
  if (params?.marketplace) qs.set('marketplace', params.marketplace)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<HypothesisLabResultItem[]>(
    `/api/v1/projects/${projectId}/hypothesis-lab/results${suffix}`
  )
  return res.data
}

export async function postHypothesisLabStartRun(
  projectId: string,
  experimentId: number
): Promise<Record<string, unknown>> {
  const res = await apiPost<Record<string, unknown>>(
    `/api/v1/projects/${projectId}/hypothesis-lab/experiments/${experimentId}/runs/start`
  )
  return res.data
}

export async function postHypothesisLabRecompute(
  projectId: string,
  runId: number,
  body: { reason?: string }
): Promise<Record<string, unknown>> {
  const res = await apiPost<Record<string, unknown>>(
    `/api/v1/projects/${projectId}/hypothesis-lab/runs/${runId}/recompute`,
    body
  )
  return res.data
}

// --- Hypothesis Lab MVP (experiments: 1 test SKU, lifecycle draft→running→completed) ---
export interface HypothesisLatestVersion {
  id: number
  version: number
  primary_metric_key: string | null
}

export interface HypothesisMvpItem {
  id: number
  key: string
  title: string | null
  description?: string | null
  domain: string | null
  hypothesis_type?: string | null
  status: string
  created_at: string | null
  updated_at: string | null
  latest_version?: HypothesisLatestVersion | null
}

export interface HypothesisExperimentListItem {
  id: number
  project_id: number
  hypothesis_id: number
  nm_id: number
  change_type: string
  change_note: string
  metric: string
  control_mode: string
  controls_count: number | null
  status: string
  period_start: string | null
  period_end: string | null
  created_at: string | null
  updated_at: string | null
  hypothesis_title: string | null
  product_title: string | null
}

export interface HypothesisExperimentDetail extends HypothesisExperimentListItem {
  runs: { id: number; experiment_id: number; started_at: string | null; change_confirmed_at: string | null; ended_at: string | null; status: string }[]
  latest_result: {
    id: number
    run_id: number
    control_mode: string
    did_effect: number | null
    p_value: number | null
    ci_low: number | null
    ci_high: number | null
    pretrend_pass: boolean | null
    before_after_delta: number | null
    computed_at: string | null
  } | null
}

export async function getHypothesesMvp(params?: { query?: string; limit?: number; status?: string }): Promise<HypothesisMvpItem[]> {
  const qs = new URLSearchParams()
  if (params?.query) qs.set('query', params.query)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.status) qs.set('status', params.status)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<HypothesisMvpItem[]>(`/api/v1/hypotheses${suffix}`)
  return res.data
}

export async function createHypothesis(body: {
  key: string
  title: string
  description?: string
  domain?: string
  hypothesis_type?: string
  hypothesis_text?: string
  primary_metric_key?: string
}): Promise<HypothesisMvpItem> {
  const res = await apiPost<HypothesisMvpItem>('/api/v1/hypotheses', body)
  return res.data
}

export async function getHypothesisMvpDetail(hypothesisId: number): Promise<HypothesisMvpItem> {
  const res = await apiGet<HypothesisMvpItem>(`/api/v1/hypotheses/${hypothesisId}`)
  return res.data
}

export async function getHypothesisExperiments(
  projectId: string,
  params?: { status?: string; metric?: string; hypothesis_id?: number; nm_id?: number; query?: string; limit?: number }
): Promise<HypothesisExperimentListItem[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.metric) qs.set('metric', params.metric)
  if (params?.hypothesis_id != null) qs.set('hypothesis_id', String(params.hypothesis_id))
  if (params?.nm_id != null) qs.set('nm_id', String(params.nm_id))
  if (params?.query) qs.set('query', params.query)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await apiGet<HypothesisExperimentListItem[]>(`/api/v1/projects/${projectId}/hypothesis/experiments${suffix}`)
  return res.data
}

export async function createHypothesisExperiment(
  projectId: string,
  body: { hypothesis_id: number; nm_id: number; change_type: string; change_note: string; metric: string }
): Promise<HypothesisExperimentListItem> {
  const res = await apiPost<HypothesisExperimentListItem>(`/api/v1/projects/${projectId}/hypothesis/experiments`, body)
  return res.data
}

export async function getHypothesisExperimentDetail(projectId: string, experimentId: number): Promise<HypothesisExperimentDetail> {
  const res = await apiGet<HypothesisExperimentDetail>(`/api/v1/projects/${projectId}/hypothesis/experiments/${experimentId}`)
  return res.data
}

export async function startHypothesisExperiment(projectId: string, experimentId: number): Promise<HypothesisExperimentListItem> {
  const res = await apiPost<HypothesisExperimentListItem>(`/api/v1/projects/${projectId}/hypothesis/experiments/${experimentId}/start`)
  return res.data
}

export async function confirmHypothesisRun(projectId: string, runId: number): Promise<{ run_id: number }> {
  const res = await apiPost<{ run_id: number }>(`/api/v1/projects/${projectId}/hypothesis/runs/${runId}/confirm`)
  return res.data
}

export async function stopHypothesisExperiment(projectId: string, experimentId: number): Promise<HypothesisExperimentListItem> {
  const res = await apiPost<HypothesisExperimentListItem>(`/api/v1/projects/${projectId}/hypothesis/experiments/${experimentId}/stop`)
  return res.data
}

// ---------------------------------------------------------------------------
// Iteration 2 (WS-E / WS-C / WS-D / compare) — SEO eval, candidate selection,
// generation promotion, read-only compare layer.
// ---------------------------------------------------------------------------

export interface SeoEvalRunRequest {
  category_id: number
  nm_ids?: number[]
  matcher_run_ids?: number[]
  label_set_id?: number
  notes?: string
}

export interface SeoEvalRunResponse {
  eval_run_id: number
  project_id: number
  category_id: number
  label_set_id: number
  verdict: string
  metrics: Record<string, any>
  thresholds: Record<string, number>
  matcher_run_ids: number[]
  nm_ids: number[]
  labels_used: number
  labels_missing: number
  eligibility_tier_after: string
}

export interface SeoEvalRunListItem {
  eval_run_id: number
  category_id: number
  label_set_id: number
  verdict: string
  metrics: Record<string, any>
  thresholds: Record<string, number>
  matcher_run_ids: number[]
  nm_ids: number[]
  notes: string | null
  created_by: string | null
  created_at: string
}

export interface SeoEvalRunListResponse {
  items: SeoEvalRunListItem[]
  eligibility_tier: string
}

export interface SeoEvalLabelStatsResponse {
  category_id: number
  label_set_id: number
  total_labels: number
  by_bucket: Record<string, number>
  by_nm_id: Record<string, number>
}

export async function postSeoMatcherEvalRun(
  projectId: string,
  body: SeoEvalRunRequest,
): Promise<SeoEvalRunResponse> {
  const res = await apiPost<SeoEvalRunResponse>(
    `/api/v1/projects/${projectId}/seo/eval/matcher/run`,
    body,
  )
  return res.data
}

export async function getSeoEvalRuns(
  projectId: string,
  params: { category_id: number; limit?: number },
): Promise<SeoEvalRunListResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  if (params.limit) qs.set('limit', String(params.limit))
  const res = await apiGet<SeoEvalRunListResponse>(
    `/api/v1/projects/${projectId}/seo/eval/runs?${qs.toString()}`,
  )
  return res.data
}

export async function getSeoEvalLabelStats(
  projectId: string,
  params: { category_id: number; label_set_id?: number },
): Promise<SeoEvalLabelStatsResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  if (params.label_set_id) qs.set('label_set_id', String(params.label_set_id))
  const res = await apiGet<SeoEvalLabelStatsResponse>(
    `/api/v1/projects/${projectId}/seo/eval/labels/stats?${qs.toString()}`,
  )
  return res.data
}

export interface SeoCandidateProjectRequest {
  category_id: number
  nm_id: number
  matcher_run_id?: number
}

export interface SeoCandidateProjectResponse {
  query_set_id: number
  matcher_run_id: number
  items_written: number
  approval_state: string
  trust_state: string
  category_profile_version: string | null
}

export async function postSeoCandidateProject(
  projectId: string,
  body: SeoCandidateProjectRequest,
): Promise<SeoCandidateProjectResponse> {
  const res = await apiPost<SeoCandidateProjectResponse>(
    `/api/v1/projects/${projectId}/seo/query-sets/candidate/project`,
    body,
  )
  return res.data
}

export interface SeoCandidateApprovalRequest {
  approval_state: 'draft' | 'preview' | 'candidate' | 'approved'
  operator_override?: boolean
  has_accepted_human_review?: boolean
}

export interface SeoCandidateQuerySetResponse {
  query_set_id: number
  project_id: number
  category_id: number
  nm_id: number
  approval_state: string
  trust_state: string
  category_profile_version: string | null
}

export async function postSeoCandidateApproval(
  projectId: string,
  querySetId: number,
  body: SeoCandidateApprovalRequest,
): Promise<SeoCandidateQuerySetResponse> {
  const res = await apiPost<SeoCandidateQuerySetResponse>(
    `/api/v1/projects/${projectId}/seo/query-sets/candidate/${querySetId}/approval`,
    body,
  )
  return res.data
}

export interface SeoGenerationPromoteRequest {
  target_kind: 'candidate' | 'approved' | 'published'
}

export interface SeoGenerationPromoteResponse {
  content_version_id: number
  previous_content_kind: string
  new_content_kind: string
  eligibility_tier: string
  human_review_id: number | null
}

export async function postSeoGenerationPromote(
  projectId: string,
  contentVersionId: number,
  body: SeoGenerationPromoteRequest,
): Promise<SeoGenerationPromoteResponse> {
  const res = await apiPost<SeoGenerationPromoteResponse>(
    `/api/v1/projects/${projectId}/seo/generation/content/${contentVersionId}/promote`,
    body,
  )
  return res.data
}

export interface SeoGenerationHumanReviewRequest {
  verdict: 'accept' | 'reject' | 'needs_changes'
  reviewer?: string
  rubric?: Record<string, any>
  notes?: string
}

export interface SeoGenerationHumanReviewResponse {
  id: number
  content_version_id: number
  reviewer: string | null
  verdict: string
}

export async function postSeoGenerationHumanReview(
  projectId: string,
  contentVersionId: number,
  body: SeoGenerationHumanReviewRequest,
): Promise<SeoGenerationHumanReviewResponse> {
  const res = await apiPost<SeoGenerationHumanReviewResponse>(
    `/api/v1/projects/${projectId}/seo/generation/content/${contentVersionId}/human-review`,
    body,
  )
  return res.data
}

export interface SeoMatcherCompareResponse {
  project_id: number
  category_id: number
  nm_id: number
  current: { meta: Record<string, any>; items: any[] }
  candidate: { meta: Record<string, any>; items: any[] }
  diff: {
    per_query_bucket: any[]
    bucket_changes: number
    bucket_change_ratio: number
    primary_rejected_flips: any[]
    only_in_current: string[]
    only_in_candidate: string[]
    total_queries_compared: number
  }
}

export async function getSeoCompareMatcher(
  projectId: string,
  params: { category_id: number; nm_id: number },
): Promise<SeoMatcherCompareResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  qs.set('nm_id', String(params.nm_id))
  const res = await apiGet<SeoMatcherCompareResponse>(
    `/api/v1/projects/${projectId}/seo/compare/matcher?${qs.toString()}`,
  )
  return res.data
}

export interface SeoGenerationCompareResponse {
  project_id: number
  category_id: number
  nm_id: number
  by_kind: Record<string, any[]>
  latest_preview_id: number | null
  latest_candidate_id: number | null
  latest_approved_id: number | null
}

export async function getSeoCompareGeneration(
  projectId: string,
  params: { category_id: number; nm_id: number },
): Promise<SeoGenerationCompareResponse> {
  const qs = new URLSearchParams()
  qs.set('category_id', String(params.category_id))
  qs.set('nm_id', String(params.nm_id))
  const res = await apiGet<SeoGenerationCompareResponse>(
    `/api/v1/projects/${projectId}/seo/compare/generation?${qs.toString()}`,
  )
  return res.data
}

export interface SeoCompareVerdictRequest {
  subject_id: number
  related_id?: number
  verdict: 'accept' | 'reject' | 'needs_changes'
  notes?: string
  created_by?: string
}

export async function postSeoCompareVerdict(
  projectId: string,
  subjectType: 'matcher' | 'generation',
  body: SeoCompareVerdictRequest,
): Promise<{ id: number; subject_type: string; subject_id: number; verdict: string }> {
  const res = await apiPost<{ id: number; subject_type: string; subject_id: number; verdict: string }>(
    `/api/v1/projects/${projectId}/seo/compare/${subjectType}/verdict`,
    body,
  )
  return res.data
}
