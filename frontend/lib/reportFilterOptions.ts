import { apiGet } from './apiClient'

export interface CoverageSegment {
  start: string
  end: string
  count: number
}

export interface ReportDatasetCoverage {
  code: string
  title: string
  role: 'primary' | 'supplementary'
  min_date: string | null
  max_date: string | null
  present_count: number
  segments: CoverageSegment[]
}

export interface ReportFilterOptions {
  project_id: number
  report_code: string
  primary_dataset: string
  date_filter: {
    enabled: boolean
    min_date: string | null
    max_date: string | null
    default_from: string | null
    default_to: string | null
    segments: CoverageSegment[]
  }
  datasets: ReportDatasetCoverage[]
}

export async function getReportFilterOptions(
  projectId: string,
  reportCode: string,
): Promise<ReportFilterOptions> {
  const response = await apiGet<ReportFilterOptions>(
    `/api/v1/projects/${projectId}/wildberries/report-filter-options/${reportCode}`,
  )
  return response.data
}

export function periodHasData(
  options: ReportFilterOptions | null,
  from: string,
  to: string,
): boolean {
  if (!options?.date_filter.enabled || !from || !to) return false
  return options.date_filter.segments.some(
    (segment) => segment.start <= to && segment.end >= from,
  )
}

export function normalizeReportPeriod(
  options: ReportFilterOptions,
  from: string,
  to: string,
): { from: string; to: string } {
  const filter = options.date_filter
  if (!filter.enabled || !filter.default_from || !filter.default_to) {
    return { from: '', to: '' }
  }
  const normalizedFrom = from
    ? from < (filter.min_date ?? from)
      ? filter.min_date ?? from
      : from
    : filter.default_from
  const normalizedTo = to
    ? to > (filter.max_date ?? to)
      ? filter.max_date ?? to
      : to
    : filter.default_to
  if (normalizedFrom > normalizedTo || !periodHasData(options, normalizedFrom, normalizedTo)) {
    return { from: filter.default_from, to: filter.default_to }
  }
  return { from: normalizedFrom, to: normalizedTo }
}
