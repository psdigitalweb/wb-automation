'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useMemo, useEffect, useState } from 'react'
import { apiGetData } from '../lib/apiClient'

interface Project {
  id: number
  name: string
}

type Crumb = {
  href: string
  label: string
}

export default function Breadcrumbs() {
  const pathname = usePathname() ?? ''
  const [projectName, setProjectName] = useState<string | null>(null)

  // Extract projectId from pathname and load project name
  useEffect(() => {
    const match = pathname?.match(/\/app\/project\/(\d+)/)
    if (match) {
      const projectId = match[1]
      apiGetData<Project>(`/api/v1/projects/${projectId}`)
        .then((project) => setProjectName(project.name))
        .catch(() => setProjectName(null))
    } else {
      setProjectName(null)
    }
  }, [pathname])

  const normalizedPathname = useMemo(() => {
    if (!pathname) return ''
    return pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
  }, [pathname])

  const isHidden = useMemo(() => {
    if (!pathname) return true
    // Hide breadcrumbs on the Projects page (main app screen).
    return normalizedPathname === '/app/projects'
  }, [pathname, normalizedPathname])

  const items = useMemo(() => {
    if (!pathname) return []
    const isAppPath = normalizedPathname.startsWith('/app')
    if (!isAppPath) {
      return [{ href: '/', label: 'Главная' }]
    }

    const match = normalizedPathname.match(/^\/app\/project\/(\d+)(?:\/(.*))?$/)
    if (match) {
      const projectId = match[1]
      const rest = (match[2] || '').trim()

      const extraLabelByPath: Record<string, string> = {
        'frontend-prices': 'Цены на витрине Wildberries',
      }

      const base: Crumb[] = [
        { href: '/app/projects', label: 'Проекты' },
        { href: `/app/project/${projectId}/dashboard`, label: projectName || `#${projectId}` },
      ]

      // For deeper project pages (except dashboard itself), show the current page as the last crumb.
      if (rest && rest !== 'dashboard') {
        const firstSeg = rest.split('/')[0]
        const label = extraLabelByPath[firstSeg]
        if (label) {
          base.push({ href: `/app/project/${projectId}/${firstSeg}`, label })
        }
      }

      return base
    }

    // Non-project app pages: keep breadcrumbs minimal.
    return [{ href: '/app/projects', label: 'Проекты' }]
  }, [pathname, normalizedPathname, projectName])

  if (isHidden) return null

  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol className="breadcrumbs-list">
        {items.map((it, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li key={it.href} className="breadcrumbs-item">
              {isLast ? (
                <span className="breadcrumbs-current" aria-current="page">
                  {it.label}
                </span>
              ) : (
                <Link className="breadcrumbs-link" href={it.href}>
                  {it.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}


