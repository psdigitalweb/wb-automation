import { apiGet, apiPost } from './apiClient'

export type WBCatalogActivity = 'active' | 'all'
export type WBCatalogOrder = 'asc' | 'desc'
export type WBCatalogSort =
  | 'title'
  | 'vendor_code'
  | 'price'
  | 'rating'
  | 'impressions'
  | 'ctr'
  | 'opens'
  | 'carts'
  | 'orders'
  | 'order_sum'
  | 'buyouts'

export interface WBCatalogSize {
  chrt_id: number | null
  tech_size: string | null
  wb_size: string | null
  skus: string[]
}

export interface WBCatalogItem {
  nm_id: number
  vendor_code: string | null
  title: string | null
  brand: string | null
  subject_name: string | null
  sizes: WBCatalogSize[]
  main_photo_url: string | null
  is_active: boolean

  showcase_price: number | null
  spp_percent: number | null
  seller_discount_percent: number | null
  rrp_price: number | null

  rating: number | null
  reviews_count: number

  impressions: number
  card_clicks: number
  ctr_percent: number | null

  opens: number
  cart_count: number
  cart_rate: number | null
  order_count: number
  cart_to_order_rate: number | null
  order_sum: number

  buyout_count: number
  buyout_sum: number
}

export interface WBCatalogMeta {
  page: number
  page_size: number
  total: number
  pages: number
  period_from: string
  period_to: string
}

export interface WBCatalogDataFreshness {
  products_at: string | null
  showcase_at: string | null
  prices_at: string | null
  rrp_at: string | null
  analytics_through: string | null
  ctr_through: string | null
  reviews_at: string | null
}

export interface WBCatalogResponse {
  items: WBCatalogItem[]
  meta: WBCatalogMeta
  data_freshness: WBCatalogDataFreshness
}

export interface WBCatalogProductResponse {
  item: WBCatalogItem
  period_from: string
  period_to: string
  data_freshness: WBCatalogDataFreshness
}

export interface WBCatalogParams {
  q?: string
  period_from?: string
  period_to?: string
  activity?: WBCatalogActivity
  sort?: WBCatalogSort
  order?: WBCatalogOrder
  page?: number
  page_size?: number
}

export type ReviewOpinionRunStatus = 'queued' | 'running' | 'ready' | 'failed'
export type ReviewOpinionCategory =
  | 'product'
  | 'packaging_delivery'
  | 'service'

export interface ReviewOpinionEvidence {
  review_id: string
  quote: string
}

export interface ReviewOpinionFinding {
  label: string
  category: ReviewOpinionCategory
  summary: string
  confidence: 'low' | 'medium' | 'high'
  supporting_review_ids: string[]
  support_count: number
  evidence: ReviewOpinionEvidence[]
}

export interface ReviewOpinionIsolatedFinding
  extends ReviewOpinionFinding {
  sentiment: 'positive' | 'negative' | 'mixed'
}

export interface ReviewOpinionConflict {
  label: string
  summary: string
  positive_review_ids: string[]
  negative_review_ids: string[]
}

export interface ReviewOpinionResult {
  schema_version: 'wb_customer_opinion_v1'
  overall_conclusion: string
  strengths: ReviewOpinionFinding[]
  weaknesses: ReviewOpinionFinding[]
  isolated_observations: ReviewOpinionIsolatedFinding[]
  conflicts: ReviewOpinionConflict[]
}

export interface ReviewOpinionRun {
  id: number
  status: ReviewOpinionRunStatus
  reviews_total: number
  reviews_with_text: number
  reviews_sent: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
}

export interface ReviewOpinionState {
  feature_enabled: boolean
  nm_id: number
  scope_type: 'all_time'
  reviews_total: number
  reviews_with_text: number
  reviews_sent: number
  max_reviews_sent: number
  can_analyze: boolean
  can_generate: boolean
  stale: boolean
  latest_run: ReviewOpinionRun | null
  result_run_id: number | null
  result_created_at: string | null
  result: ReviewOpinionResult | null
}

export interface ReviewOpinionGenerateResponse {
  run: ReviewOpinionRun
  reused: boolean
  message: string
}

export async function getWBCatalog(
  projectId: string,
  params: WBCatalogParams,
): Promise<WBCatalogResponse> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.period_from) query.set('period_from', params.period_from)
  if (params.period_to) query.set('period_to', params.period_to)
  query.set('activity', params.activity ?? 'all')
  query.set('sort', params.sort ?? 'order_sum')
  query.set('order', params.order ?? 'desc')
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.page_size ?? 50))
  query.set('ctr_mode', 'quality_filtered')

  const response = await apiGet<WBCatalogResponse>(
    `/api/v1/projects/${projectId}/wildberries/catalog?${query.toString()}`,
  )
  return response.data
}

export async function getWBCatalogProduct(
  projectId: string,
  nmId: string,
  params: { period_from?: string; period_to?: string } = {},
): Promise<WBCatalogProductResponse> {
  const query = new URLSearchParams()
  if (params.period_from) query.set('period_from', params.period_from)
  if (params.period_to) query.set('period_to', params.period_to)
  query.set('ctr_mode', 'quality_filtered')
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiGet<WBCatalogProductResponse>(
    `/api/v1/projects/${projectId}/wildberries/catalog/${nmId}${suffix}`,
  )
  return response.data
}

export async function getReviewOpinion(
  projectId: string,
  nmId: string,
): Promise<ReviewOpinionState> {
  const response = await apiGet<ReviewOpinionState>(
    `/api/v1/projects/${projectId}/wildberries/catalog/${nmId}/customer-opinion`,
  )
  return response.data
}

export async function generateReviewOpinion(
  projectId: string,
  nmId: string,
  refresh: boolean,
): Promise<ReviewOpinionGenerateResponse> {
  const response = await apiPost<ReviewOpinionGenerateResponse>(
    `/api/v1/projects/${projectId}/wildberries/catalog/${nmId}/customer-opinion/generate`,
    { refresh },
  )
  return response.data
}
