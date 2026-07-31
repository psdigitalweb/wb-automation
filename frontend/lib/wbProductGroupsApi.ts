import { apiGet } from './apiClient'

export interface WBProductGroupPreview {
  nm_id: number
  title: string | null
  vendor_code: string | null
  image_url: string | null
}

export interface WBProductGroupListItem {
  wb_group_id: number
  members_count: number
  last_seen_at: string
  fbs_stock_qty: number
  fbo_stock_qty: number
  previews: WBProductGroupPreview[]
}

export interface WBProductGroupsResponse {
  items: WBProductGroupListItem[]
  total: number
  page: number
  page_size: number
}

export interface WBProductGroupCategory {
  name: string
  groups_count: number
}

export interface WBProductGroupMembership {
  wb_group_id: number
  members_count: number
  last_seen_at: string
}

export interface WBProductGroupComparisonMember {
  nm_id: number
  vendor_code: string | null
  title: string | null
  subject_name: string | null
  image_url: string | null
  stock: { fbs: number; fbo: number }
  price: { first: number | null; last: number | null; delta: number | null }
  spp: { first: number | null; last: number | null; delta: number | null }
  funnel: {
    impressions: number
    card_clicks: number
    ctr_percent: number | null
    opens: number
    carts: number
    cart_rate_percent: number | null
    orders: number
    cart_to_order_percent: number | null
    revenue: number
  }
}

export interface WBProductGroupComparisonResponse {
  wb_group_id: number
  members_count: number
  period_from: string
  period_to: string
  members: WBProductGroupComparisonMember[]
}

export interface WBProductGroupSeriesPoint {
  date: string
  price: number | null
  spp_percent: number | null
  impressions: number
  card_clicks: number
  ctr_percent: number | null
  opens: number
  carts: number
  orders: number
  revenue: number
}

export interface WBProductGroupSeriesItem {
  nm_id: number
  title: string | null
  vendor_code: string | null
  points: WBProductGroupSeriesPoint[]
}

export async function getWBProductGroups(
  projectId: string,
  params: { search?: string; category?: string; in_stock?: boolean; page?: number; page_size?: number }
): Promise<WBProductGroupsResponse> {
  const qs = new URLSearchParams()
  if (params.search) qs.set('search', params.search)
  if (params.category) qs.set('category', params.category)
  if (params.in_stock) qs.set('in_stock', 'true')
  qs.set('page', String(params.page ?? 1))
  qs.set('page_size', String(params.page_size ?? 30))
  const res = await apiGet<WBProductGroupsResponse>(
    `/api/v1/projects/${projectId}/wildberries/product-groups?${qs.toString()}`
  )
  return res.data
}

export async function getWBProductGroupCategories(projectId: string): Promise<WBProductGroupCategory[]> {
  const res = await apiGet<{ items: WBProductGroupCategory[] }>(
    `/api/v1/projects/${projectId}/wildberries/product-groups/categories`
  )
  return res.data.items
}

export async function getWBProductGroupsForProduct(
  projectId: string,
  nmId: string,
): Promise<WBProductGroupMembership[]> {
  const res = await apiGet<{ items: WBProductGroupMembership[] }>(
    `/api/v1/projects/${projectId}/wildberries/products/${nmId}/product-groups`,
  )
  return res.data.items
}

export async function getWBProductGroupComparison(
  projectId: string,
  groupId: number,
  params: { date_from: string; date_to: string }
): Promise<WBProductGroupComparisonResponse> {
  const qs = new URLSearchParams(params)
  const res = await apiGet<WBProductGroupComparisonResponse>(
    `/api/v1/projects/${projectId}/wildberries/product-groups/${groupId}/comparison?${qs.toString()}`
  )
  return res.data
}

export async function getWBProductGroupSeries(
  projectId: string,
  groupId: number,
  params: { date_from: string; date_to: string; nm_ids: number[] }
): Promise<{ wb_group_id: number; period_from: string; period_to: string; series: WBProductGroupSeriesItem[] }> {
  const qs = new URLSearchParams()
  qs.set('date_from', params.date_from)
  qs.set('date_to', params.date_to)
  params.nm_ids.forEach((nmId) => qs.append('nm_ids', String(nmId)))
  const res = await apiGet<{
    wb_group_id: number
    period_from: string
    period_to: string
    series: WBProductGroupSeriesItem[]
  }>(`/api/v1/projects/${projectId}/wildberries/product-groups/${groupId}/series?${qs.toString()}`)
  return res.data
}
