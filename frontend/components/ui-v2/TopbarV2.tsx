'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { apiGetData } from '../../lib/apiClient'
import { clearAuth, getUser } from '../../lib/auth'
import Icon from './Icon'
import BreadcrumbsV2 from './BreadcrumbsV2'

type TopbarV2Props = {
  variant?: 'app' | 'projects'
}

type Project = {
  id: number
  name: string
  description: string | null
  role: string
}

export default function TopbarV2({ variant = 'app' }: TopbarV2Props) {
  const router = useRouter()
  const pathname = usePathname()
  const [user, setUser] = useState(getUser())
  const [projects, setProjects] = useState<Project[]>([])
  const [currentProjectId, setCurrentProjectId] = useState<number | null>(null)

  useEffect(() => {
    const match = pathname?.match(/\/app\/project\/(\d+)/)
    setCurrentProjectId(match ? Number.parseInt(match[1], 10) : null)
    setUser(getUser())
  }, [pathname])

  useEffect(() => {
    apiGetData<Project[]>('/api/v1/projects')
      .then(setProjects)
      .catch((error) => console.error('Failed to load projects:', error))
  }, [])

  const handleProjectChange = (projectId: string) => {
    const id = Number.parseInt(projectId, 10)
    if (Number.isNaN(id)) return
    setCurrentProjectId(id)
    router.push(`/app/project/${id}/dashboard`)
  }

  const handleLogout = () => {
    clearAuth()
    router.push('/')
  }

  if (!user) return null

  return (
    <header className="ec-topbar">
      <div className="ec-topbar-left">
        {variant === 'projects' ? (
          <Link className="ec-topbar-brand" href="/app/projects" aria-label="EcomCore">
            <span className="ec-logo-mark">EC</span>
            <span>EcomCore</span>
          </Link>
        ) : (
          <BreadcrumbsV2 />
        )}
      </div>
      <div className="ec-topbar-right">
        {variant === 'app' ? (
          <label className="ec-project-select-wrap">
            <span className="ec-sr-only">Выбрать проект</span>
            <select
              className="ec-project-select"
              value={currentProjectId ?? ''}
              onChange={(event) => handleProjectChange(event.target.value)}
              disabled={projects.length === 0}
            >
              {projects.length === 0 ? (
                <option value="">Нет проектов</option>
              ) : (
                <>
                  <option value="">Выбрать проект...</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </>
              )}
            </select>
          </label>
        ) : null}
        {user.is_superuser ? (
          <Link className="ec-icon-button" href="/app/admin/settings" title="Настройки администратора" aria-label="Настройки администратора">
            <Icon name="gear" size={16} />
          </Link>
        ) : null}
        <div className="ec-user-pill" title={user.email || user.username}>
          <span className="ec-user-avatar">{(user.email || user.username || 'U').slice(0, 1).toUpperCase()}</span>
          <span className="ec-user-name">{user.email || user.username}</span>
        </div>
        <button className="ec-button ec-button-ghost ec-button-sm" type="button" onClick={handleLogout}>
          <Icon name="logout" size={14} />
          <span>Выйти</span>
        </button>
      </div>
    </header>
  )
}
