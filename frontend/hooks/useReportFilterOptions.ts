'use client'

import { type Dispatch, type SetStateAction, useEffect, useState } from 'react'
import {
  getReportFilterOptions,
  normalizeReportPeriod,
  type ReportFilterOptions,
} from '@/lib/reportFilterOptions'

export function useReportFilterOptions(projectId: string, reportCode: string) {
  const [options, setOptions] = useState<ReportFilterOptions | null>(null)
  const [loading, setLoading] = useState(Boolean(projectId))

  useEffect(() => {
    if (!projectId) return
    let active = true
    setLoading(true)
    getReportFilterOptions(projectId, reportCode)
      .then((result) => {
        if (active) setOptions(result)
      })
      .catch(() => {
        if (active) setOptions(null)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, reportCode])

  return { options, loading }
}

export function useConstrainedReportPeriod(
  projectId: string,
  reportCode: string,
  periodFrom: string,
  periodTo: string,
  setPeriodFrom: Dispatch<SetStateAction<string>>,
  setPeriodTo: Dispatch<SetStateAction<string>>,
) {
  const state = useReportFilterOptions(projectId, reportCode)
  useEffect(() => {
    if (!state.options) return
    const normalized = normalizeReportPeriod(state.options, periodFrom, periodTo)
    if (normalized.from !== periodFrom) setPeriodFrom(normalized.from)
    if (normalized.to !== periodTo) setPeriodTo(normalized.to)
  }, [periodFrom, periodTo, setPeriodFrom, setPeriodTo, state.options])
  return state
}
