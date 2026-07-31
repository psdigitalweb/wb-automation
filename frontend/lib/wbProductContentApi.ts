import { apiGet } from './apiClient'

export interface WBContentVersionSummary {
  id: number
  project_id: number
  nm_id: number
  version_no: number
  event_type: 'initial' | 'changed'
  content_hash: string
  normalization_version: string
  changed_fields: Record<string, unknown>
  change_types: string[]
  observed_at: string
  source_updated_at: string | null
  ingest_run_id: number | null
  created_at: string
}

export interface WBContentSnapshot {
  vendorCode?: string | null
  title?: string | null
  subjectID?: number | null
  subjectName?: string | null
  description?: string | null
  dimensions?: Record<string, unknown>
  characteristics?: unknown[]
  sizes?: Array<{
    chrtID?: number | null
    techSize?: string | null
    wbSize?: string | null
  }>
  photos?: Array<Record<string, unknown>>
  needKiz?: boolean | null
}

export interface WBContentVersion extends WBContentVersionSummary {
  content_snapshot: WBContentSnapshot
}

export interface WBMainPhotoPeriod {
  id: number
  content_version_id: number | null
  asset_id: number | null
  source_url: string | null
  observed_from: string
  observed_to: string | null
  source_updated_at: string | null
  archive_status: 'pending' | 'stored' | 'failed' | 'skipped_inactive'
  archive_error: string | null
  asset_content_type: string | null
  asset_file_size: number | null
}

export async function getWBContentHistory(
  projectId: string,
  nmId: string,
): Promise<WBContentVersionSummary[]> {
  const response = await apiGet<{ items: WBContentVersionSummary[] }>(
    `/api/v1/projects/${projectId}/products/${nmId}/content-history?limit=200`,
  )
  return response.data.items
}

export async function getWBContentVersion(
  projectId: string,
  nmId: string,
  versionId: number,
): Promise<WBContentVersion> {
  const response = await apiGet<WBContentVersion>(
    `/api/v1/projects/${projectId}/products/${nmId}/content-history/${versionId}`,
  )
  return response.data
}

export async function getWBMainPhotoHistory(
  projectId: string,
  nmId: string,
): Promise<WBMainPhotoPeriod[]> {
  const response = await apiGet<{ items: WBMainPhotoPeriod[] }>(
    `/api/v1/projects/${projectId}/products/${nmId}/main-photo-history`,
  )
  return response.data.items
}
