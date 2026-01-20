'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useMemo, useEffect, useState } from 'react'
import { apiGetData } from '../lib/apiClient'

const LABELS: Record<string, string> = {
  app: 'Приложение',
  projects: 'Проекты',
  project: 'Проект',
  dashboard: 'Дашборд',
  prices: 'Цены',
  stocks: 'FBS остатки',
  'supplier-stocks': 'FBO остатки',
  'rrp-snapshots': 'RRP',
  'frontend-prices': 'Frontend цены',
  'articles-base': 'База артикулов',
  wildberries: 'Wildberries',
  'price-discrepancies': 'Расхождения цен',
  settings: 'Настройки',
  marketplaces: 'Маркетплейсы',
}

function humanize(segment: string) {
  if (!segment) return segment
  if (/^\d+$/.test(segment)) return `#${segment}`
  return (
    segment
      .replace(/[-_]+/g, ' ')
      .split(' ')
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ')
  )
}

interface Project {
  id: number
  name: string
}

export default function Breadcrumbs() {
  const pathname = usePathname() || '/'
  const [projectName, setProjectName] = useState<string | null>(null)

  // Extract projectId from pathname and load project name
  useEffect(() => {
    const match = pathname?.match(/\/app\/project\/(\d+)/)
    if (match) {
      const projectId = match[1]
      apiGetData<Project>(`/v1/projects/${projectId}`)
        .then((project) => setProjectName(project.name))
        .catch(() => setProjectName(null))
    } else {
      setProjectName(null)
    }
  }, [pathname])

  const items = useMemo(() => {
    const segments = pathname.split('/').filter(Boolean)
    
    // If path starts with /app, start with "Проекты" instead of "Главная"
    const isAppPath = pathname.startsWith('/app')
    const crumbs: Array<{ href: string; label: string }> = isAppPath 
      ? [{ href: '/app/projects', label: 'Проекты' }]
      : [{ href: '/', label: 'Главная' }]

    if (!isAppPath) {
      // For non-app paths, build breadcrumbs normally
      let href = ''
      for (const seg of segments) {
        href += `/${seg}`
        const label = LABELS[seg] || humanize(seg)
        crumbs.push({ href, label })
      }
      return crumbs
    }

    // For /app paths, skip "app" and handle special cases
    let href = '/app'
    let i = 1 // Skip "app" segment (index 0)
    
    while (i < segments.length) {
      const seg = segments[i]
      
      // If this is "projects", skip it (we already added "Проекты")
      if (seg === 'projects') {
        href += `/${seg}`
        i++
        continue
      }
      
      // If this is "project" followed by a number, replace with project name
      if (seg === 'project' && i + 1 < segments.length && /^\d+$/.test(segments[i + 1])) {
        const projectId = segments[i + 1]
        href += `/${seg}/${projectId}`
        const label = projectName || `#${projectId}`
        crumbs.push({ href, label })
        i += 2 // Skip both "project" and the ID
        continue
      }

      // For dashboard route, do not add extra "Дашборд" segment;
      // keep breadcrumb as "Проекты / {ProjectName}"
      if (seg === 'dashboard') {
        break
      }
      
      // Regular segment
      href += `/${seg}`
      const label = LABELS[seg] || humanize(seg)
      crumbs.push({ href, label })
      i++
    }

    return crumbs
  }, [pathname, projectName])

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


