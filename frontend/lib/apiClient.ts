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

function buildFullUrl(url: string): string {
  const apiBase = getApiBase()
  if (url.startsWith('http')) return url
  if (apiBase) return `${apiBase}${url}`

    // Default: same-origin /api/... via Next.js rewrites.
    // In local dev, Next.js proxy may reset long-running upstream requests,
    // so a direct call to backend:8000 is helpful there. On prod we must keep
    // same-origin /api to avoid mixed-origin/network failures in the browser.
    if (typeof window !== 'undefined') {
      const isSlowEndpoint =
        url.includes('/wildberries/search-report/keywords') ||
        url.includes('/wildberries/search-report/search-texts')
      const hostname = window.location.hostname || 'localhost'
      const isLocalDevHost =
        hostname === 'localhost' ||
        hostname === '127.0.0.1' ||
        hostname === '0.0.0.0'
      if (isSlowEndpoint && isLocalDevHost) {
        const protocol = window.location.protocol || 'http:'
        return `${protocol}//${hostname}:8000${url}`
      }
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
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'apiClient.ts:fetchWithAuth:before_fetch',message:'API request',data:{fullUrl,url},timestamp:Date.now(),runId:'api',hypothesisId:'H1'})}).catch(()=>{});
    // #endregion
    res = await fetch(fullUrl, fetchOptions)
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'apiClient.ts:fetchWithAuth:after_fetch',message:'API response',data:{status:res.status,ok:res.ok,fullUrl},timestamp:Date.now(),runId:'api',hypothesisId:'H4'})}).catch(()=>{});
    // #endregion
  } catch (fetchError: any) {
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'apiClient.ts:fetchWithAuth:fetch_error',message:'Fetch failed',data:{message:fetchError?.message,fullUrl},timestamp:Date.now(),runId:'api',hypothesisId:'H1'})}).catch(()=>{});
    // #endregion
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
  wb_total_signed?: number | null
  wb_total_cost_per_unit?: number | null
  profit_per_unit?: number | null
  margin_pct_of_revenue?: number | null
  margin_pct_of_rrp?: number | null
  markup_pct_of_cogs?: number | null
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
    total_to_pay?: number
    rrp_sales_model?: number | null
    wb_take_from_rrp?: number | null
    wb_take_pct_of_rrp?: number | null
    rrp_coverage_pct?: number | null
    rrp_net_units_covered?: number | null
    net_units_total?: number | null
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
  wb_total_signed?: number | null
  wb_total_pct_of_sale?: number | null
  wb_costs_per_unit: {
    total?: number | null
    breakdown?: {
      commission?: number | null
      acquiring?: number | null
      logistics?: number | null
      storage?: number | null
      acceptance?: number | null
      withholdings?: number | null
      penalties?: number | null
      total?: number | null
    }
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

export async function getReviewsSummary(
  projectId: string,
  params: {
    period_from?: string
    period_to?: string
    nm_id?: number
    vendor_code?: string
    wb_category?: string
    rating_lte?: number
  }
): Promise<ReviewsSummaryResponse> {
  const qs = new URLSearchParams()
  if (params.period_from != null && params.period_from !== '') qs.set('period_from', params.period_from)
  if (params.period_to != null && params.period_to !== '') qs.set('period_to', params.period_to)
  if (params.nm_id != null && !Number.isNaN(params.nm_id)) qs.set('nm_id', String(params.nm_id))
  if (params.vendor_code != null && params.vendor_code.trim() !== '') qs.set('vendor_code', params.vendor_code.trim())
  if (params.wb_category != null && params.wb_category !== '') qs.set('wb_category', params.wb_category)
  if (params.rating_lte != null && !Number.isNaN(params.rating_lte)) qs.set('rating_lte', String(params.rating_lte))
  const res = await apiGet<ReviewsSummaryResponse>(
    `/api/v1/projects/${projectId}/wildberries/reviews/summary?${qs.toString()}`
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
  if (params.page != null && params.page >= 1) qs.set('page', String(params.page))
  if (params.page_size != null && params.page_size >= 1) qs.set('page_size', String(params.page_size))
  if (params.sort != null && params.sort !== '') qs.set('sort', params.sort)
  if (params.order != null && params.order !== '') qs.set('order', params.order)
  const res = await apiGet<FunnelSignalsResponse>(
    `/api/v1/projects/${projectId}/wildberries/analytics/funnel-signals?${qs.toString()}`
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
