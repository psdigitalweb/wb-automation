import { apiDelete, apiGet, apiPost } from './apiClient'

export type CompetitorReviewTargetStatus =
  | 'queued'
  | 'collecting'
  | 'ready'
  | 'partial'
  | 'failed'
  | 'not_found'

export type CompetitorReviewRunStatus = 'queued' | 'running' | 'completed' | 'failed'
export type CompetitorAnalysisStatus = 'queued' | 'running' | 'ready' | 'failed'

export interface CompetitorReviewTarget {
  nm_id: number
  title: string | null
  brand: string | null
  category_name: string | null
  text_reviews_count: number
  collected_reviews_count: number
  calculated_avg_rating: number | null
  wb_review_rating: number | null
  wb_feedback_count: number | null
  status: CompetitorReviewTargetStatus
  last_collected_at: string | null
  last_error: string | null
  analysis_status: CompetitorAnalysisStatus | null
  analysis_is_stale: boolean
  analysis_reviews_count: number | null
  analysis_cost_usd: number | null
  analysis_finished_at: string | null
  analysis_error: string | null
  analysis_estimated_cost_usd: number | null
}

export interface CompetitorReview {
  id: string | number
  rating: number | null
  text: string | null
  pros: string | null
  cons: string | null
  created_at: string | null
}

export interface CompetitorReviewRun {
  id: number
  status: CompetitorReviewRunStatus
  requested_nm_ids: number[]
  completed_nm_ids?: number[]
  failed_nm_ids?: number[]
  created_at: string
  started_at: string | null
  finished_at: string | null
  error_message: string | null
}

export interface AddCompetitorReviewTargetsResponse {
  items: CompetitorReviewTarget[]
  added_count: number
  existing_count: number
}

export interface CompetitorReviewTargetsResponse {
  items: CompetitorReviewTarget[]
}

export interface DeleteCompetitorReviewTargetsResponse {
  deleted_nm_ids: number[]
  deleted_count: number
}

export interface CollectCompetitorReviewsResponse {
  run: CompetitorReviewRun
}

export interface CompetitorReviewRunResponse {
  run: CompetitorReviewRun
}

export interface CompetitorReviewListResponse {
  items: CompetitorReview[]
  total: number
  has_more: boolean
}

export interface CompetitorAnalysisEvidence {
  review_id: string
  quote: string
}

export interface CompetitorAnalysisFinding {
  label: string
  category: 'product' | 'packaging_delivery' | 'service' | null
  summary: string
  confidence: 'low' | 'medium' | 'high' | null
  priority: 'low' | 'medium' | 'high' | null
  support_count: number
  prevalence: 'frequent' | 'occasional' | 'isolated'
  evidence: CompetitorAnalysisEvidence[]
}

export interface CompetitorAnalysisConflict {
  label: string
  summary: string
  support_count: number
  prevalence: 'frequent' | 'occasional' | 'isolated'
}

export interface CompetitorAnalysisResult {
  schema_version: string
  overall_conclusion: string
  strengths: CompetitorAnalysisFinding[]
  weaknesses: CompetitorAnalysisFinding[]
  opportunities: CompetitorAnalysisFinding[]
  conflicts: CompetitorAnalysisConflict[]
}

export interface CompetitorAnalysisRun {
  id: number
  status: CompetitorAnalysisStatus
  reviews_sent: number
  estimated_cost_usd: number
  max_cost_usd: number
  actual_cost_usd: number | null
  result: CompetitorAnalysisResult | null
  error_code: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface CompetitorAnalysisState {
  nm_id: number
  reviews_with_text: number
  estimated_cost_usd: number
  can_generate: boolean
  is_stale: boolean
  latest: CompetitorAnalysisRun | null
  latest_ready: CompetitorAnalysisRun | null
}

export interface GenerateCompetitorAnalysisResponse {
  run: CompetitorAnalysisRun
  cached: boolean
}

const basePath = (projectId: string) => `/api/v1/projects/${projectId}/competitor-reviews`

export async function addCompetitorReviewTargets(
  projectId: string,
  nmIds: number[],
): Promise<AddCompetitorReviewTargetsResponse> {
  const response = await apiPost<AddCompetitorReviewTargetsResponse>(`${basePath(projectId)}/targets`, {
    nm_ids: nmIds,
  })
  return response.data
}

export async function getCompetitorReviewTargets(projectId: string): Promise<CompetitorReviewTargetsResponse> {
  const response = await apiGet<CompetitorReviewTargetsResponse>(`${basePath(projectId)}/targets`)
  return response.data
}

export async function deleteCompetitorReviewTargets(
  projectId: string,
  nmIds: number[],
): Promise<DeleteCompetitorReviewTargetsResponse> {
  const query = new URLSearchParams()
  nmIds.forEach((nmId) => query.append('nm_ids', String(nmId)))
  const response = await apiDelete<DeleteCompetitorReviewTargetsResponse>(
    `${basePath(projectId)}/targets?${query.toString()}`,
  )
  return response.data
}

export async function collectCompetitorReviews(
  projectId: string,
  nmIds?: number[],
): Promise<CollectCompetitorReviewsResponse> {
  const response = await apiPost<CollectCompetitorReviewsResponse>(`${basePath(projectId)}/collect`,
    nmIds && nmIds.length > 0 ? { nm_ids: nmIds } : {},
  )
  return response.data
}

export async function getCompetitorReviewRun(
  projectId: string,
  runId: number,
): Promise<CompetitorReviewRunResponse> {
  const response = await apiGet<CompetitorReviewRunResponse>(`${basePath(projectId)}/runs/${runId}`)
  return response.data
}

export async function getCompetitorReviews(
  projectId: string,
  nmId: number,
  params: { limit?: number; offset?: number } = {},
): Promise<CompetitorReviewListResponse> {
  const query = new URLSearchParams({
    limit: String(params.limit ?? 20),
    offset: String(params.offset ?? 0),
  })
  const response = await apiGet<CompetitorReviewListResponse>(
    `${basePath(projectId)}/targets/${nmId}/reviews?${query.toString()}`,
  )
  return response.data
}

export async function getCompetitorAnalysis(
  projectId: string,
  nmId: number,
): Promise<CompetitorAnalysisState> {
  const response = await apiGet<CompetitorAnalysisState>(
    `${basePath(projectId)}/targets/${nmId}/analysis`,
  )
  return response.data
}

export async function generateCompetitorAnalysis(
  projectId: string,
  nmId: number,
  options: { refresh?: boolean; maxCostUsd?: number } = {},
): Promise<GenerateCompetitorAnalysisResponse> {
  const response = await apiPost<GenerateCompetitorAnalysisResponse>(
    `${basePath(projectId)}/targets/${nmId}/analysis`,
    {
      refresh: options.refresh ?? false,
      max_cost_usd: options.maxCostUsd ?? 0.2,
    },
  )
  return response.data
}
