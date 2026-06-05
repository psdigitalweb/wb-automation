'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { apiGetData } from '../../lib/apiClient'
import Icon from './Icon'
import { getProjectRoute, humanizeSegment } from './navModel'

type Project = {
  id: number
  name: string
}

type Crumb = {
  href: string
  label: string
}

export default function BreadcrumbsV2() {
  const pathname = usePathname() ?? ''
  const [projectName, setProjectName] = useState<string | null>(null)
  const { projectId } = useMemo(() => getProjectRoute(pathname), [pathname])

  useEffect(() => {
    if (!projectId) {
      setProjectName(null)
      return
    }

    apiGetData<Project>(`/api/v1/projects/${projectId}`)
      .then((project) => setProjectName(project.name))
      .catch(() => setProjectName(null))
  }, [projectId])

  const items = useMemo<Crumb[]>(() => {
    const normalized = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
    if (!normalized || normalized === '/app/projects') return []

    const route = getProjectRoute(normalized)
    if (route.projectId) {
      const crumbs: Crumb[] = [
        { href: '/app/projects', label: 'Проекты' },
        {
          href: `/app/project/${route.projectId}/dashboard`,
          label: projectName || `#${route.projectId}`,
        },
      ]
      const restSegments = route.restPath.split('/').filter(Boolean)
      let href = `/app/project/${route.projectId}`
      restSegments.forEach((segment) => {
        href += `/${segment}`
        if (segment !== 'dashboard') crumbs.push({ href, label: humanizeSegment(segment) })
      })
      return crumbs
    }

    const segments = normalized.replace(/^\/app\/?/, '').split('/').filter(Boolean)
    return [{ href: '/app/projects', label: 'Проекты' }].concat(
      segments.map((segment, index) => ({
        href: `/app/${segments.slice(0, index + 1).join('/')}`,
        label: humanizeSegment(segment),
      })),
    )
  }, [pathname, projectName])

  if (items.length === 0) return null

  return (
    <nav className="ec-breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((item, index) => {
          const current = index === items.length - 1
          return (
            <li key={`${item.href}-${index}`}>
              {index > 0 ? <Icon name="chevronRight" size={12} className="ec-breadcrumb-separator" /> : null}
              {current ? (
                <span aria-current="page">{item.label}</span>
              ) : (
                <Link href={item.href}>{item.label}</Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

