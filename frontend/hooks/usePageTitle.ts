'use client'

import { useEffect, useState } from 'react'
import { apiGetData } from '../lib/apiClient'

interface Project {
  id: number
  name: string
}

/**
 * Hook to set page title with project name
 * Format: "<Section Name> — {ProjectName} · E-com Core"
 */
export function usePageTitle(sectionName: string, projectId: string | null) {
  const [projectName, setProjectName] = useState<string | null>(null)

  // Load project name
  useEffect(() => {
    if (!projectId) {
      setProjectName(null)
      return
    }

    apiGetData<Project>(`/api/v1/projects/${projectId}`)
      .then((project) => setProjectName(project.name))
      .catch(() => setProjectName(null))
  }, [projectId])

  // Update document.title when project name is loaded
  useEffect(() => {
    if (projectName) {
      document.title = `${sectionName} — ${projectName} · E-com Core`
    } else if (projectId) {
      // Show section name even if project name is not loaded yet
      document.title = `${sectionName} — ... · E-com Core`
    } else {
      document.title = `${sectionName} · E-com Core`
    }
  }, [sectionName, projectName, projectId])
}
