'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { getUser, clearAuth } from '../lib/auth'
import { apiGetData } from '../lib/apiClient'
import './Topbar.css'

interface Project {
  id: number
  name: string
  description: string | null
  role: string
}

export default function Topbar() {
  const router = useRouter()
  const pathname = usePathname()
  const [user, setUser] = useState(getUser())
  const [projects, setProjects] = useState<Project[]>([])
  const [currentProjectId, setCurrentProjectId] = useState<number | null>(null)

  // Extract projectId from pathname
  useEffect(() => {
    const match = pathname?.match(/\/app\/project\/(\d+)/)
    if (match) {
      setCurrentProjectId(parseInt(match[1]))
    } else {
      setCurrentProjectId(null)
    }
  }, [pathname])

  // Load projects
  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    try {
      const projects = await apiGetData<Project[]>('/api/v1/projects')
      setProjects(projects)
    } catch (error) {
      console.error('Failed to load projects:', error)
    }
  }

  const handleProjectChange = (projectId: string) => {
    const id = parseInt(projectId)
    setCurrentProjectId(id)
    // Navigate to dashboard of selected project
    router.push(`/app/project/${id}/dashboard`)
  }

  const handleLogout = () => {
    clearAuth()
    router.push('/')
  }

  if (!user) return null

  return (
    <div className="topbar">
      <div className="container">
        <div className="topbar-left">
          <Link href="/" className="topbar-brand" aria-label="Главная">
            <Image
              src="/header_logo.jpg?v=3"
              alt="E-com Core"
              width={200}
              height={48}
              priority
              className="topbar-logo"
              unoptimized
            />
          </Link>
          <div className="topbar-project-selector">
            <select
              value={currentProjectId || ''}
              onChange={(e) => handleProjectChange(e.target.value)}
              disabled={projects.length === 0}
            >
              {projects.length === 0 ? (
                <option value="">Нет проектов</option>
              ) : (
                <>
                  <option value="">Выбрать проект…</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </>
              )}
            </select>
          </div>
        </div>
        <div className="topbar-right">
          {user.is_superuser && (
            <Link href="/app/admin/settings" className="topbar-admin-link" title="Настройки администратора">
              ⚙️
            </Link>
          )}
          <span className="topbar-user">{user.email || user.username}</span>
          <button onClick={handleLogout} className="btn-logout">
            Выйти
          </button>
        </div>
      </div>
    </div>
  )
}

