'use client'

import { usePathname } from 'next/navigation'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { apiGetData } from '../../lib/apiClient'
import RailNav from './RailNav'
import SubNav from './SubNav'
import TopbarV2 from './TopbarV2'
import { filterRailItemsByMarketplaces, getActiveRailId, getProjectRoute, railItems, subNavGroupsByRail } from './navModel'
import './ui-v2.css'

type AppShellV2Props = {
  children: ReactNode
}

type ProjectMarketplace = {
  marketplace_code: string | null
  is_enabled: boolean
}

export default function AppShellV2({ children }: AppShellV2Props) {
  const pathname = usePathname() || '/app/projects'
  const { projectId, restPath } = getProjectRoute(pathname)
  const activeRail = getActiveRailId(pathname)
  const isProjectsIndex = pathname === '/app/projects'
  const [openRail, setOpenRail] = useState(activeRail)
  const subNavGroups = subNavGroupsByRail[openRail] ?? []
  const showSubNav = Boolean(projectId && subNavGroups.length > 0)
  const [connectedMarketplaces, setConnectedMarketplaces] = useState<Set<string> | null>(null)
  const visibleRailItems = useMemo(
    () => filterRailItemsByMarketplaces(railItems, connectedMarketplaces),
    [connectedMarketplaces],
  )

  useEffect(() => {
    setOpenRail(activeRail)
  }, [activeRail])

  useEffect(() => {
    if (!projectId) {
      setConnectedMarketplaces(null)
      return
    }

    let alive = true
    setConnectedMarketplaces(new Set())
    apiGetData<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
      .then((marketplaces) => {
        if (!alive) return
        setConnectedMarketplaces(
          new Set(
            marketplaces
              .filter((marketplace) => marketplace.is_enabled && marketplace.marketplace_code)
              .map((marketplace) => marketplace.marketplace_code as string),
          ),
        )
      })
      .catch((error) => {
        console.error('Failed to load project marketplaces:', error)
        if (alive) setConnectedMarketplaces(new Set())
      })

    return () => {
      alive = false
    }
  }, [projectId])

  return (
    <div className={`ec-ui-v2 ${isProjectsIndex ? 'ec-ui-v2-projects-index' : ''}`}>
      {isProjectsIndex ? null : (
        <RailNav
          activePrimary={activeRail}
          openPrimary={openRail}
          projectId={projectId}
          items={visibleRailItems}
          onPrimaryOpen={setOpenRail}
        />
      )}
      {isProjectsIndex ? null : (
        <SubNav visible={showSubNav} projectId={projectId} restPath={restPath} groups={subNavGroups} />
      )}
      <div className="ec-main-zone">
        <TopbarV2 variant={isProjectsIndex ? 'projects' : 'app'} />
        <main className="ec-main-content">{children}</main>
      </div>
    </div>
  )
}
