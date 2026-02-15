'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { apiGetData, apiPostData } from '../../../lib/apiClient'

interface Project {
  id: number
  name: string
  description: string | null
  created_by: number
  created_at: string
  updated_at: string
  role: string
}

export default function ProjectsPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateFormOpen, setIsCreateFormOpen] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [newProjectDesc, setNewProjectDesc] = useState('')
  const projectNameInputRef = useRef<HTMLInputElement>(null)
  const roleLabels: Record<string, string> = {
    owner: 'владелец',
  }

  useEffect(() => {
    loadProjects()
  }, [])

  // Auto-focus on project name input when form opens
  useEffect(() => {
    if (isCreateFormOpen && projectNameInputRef.current) {
      projectNameInputRef.current.focus()
    }
  }, [isCreateFormOpen])

  const loadProjects = async () => {
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'projects/page.tsx:loadProjects:entry',message:'loadProjects started',data:{},timestamp:Date.now(),runId:'run1',hypothesisId:'H1'})}).catch(()=>{})
    // #endregion
    try {
      setLoading(true)
      const projects = await apiGetData<Project[]>('/api/v1/projects')
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'projects/page.tsx:loadProjects:success',message:'apiGetData returned',data:{isArray:Array.isArray(projects),length:Array.isArray(projects)?projects.length:undefined,firstId:Array.isArray(projects)&&projects[0]?(projects[0] as any).id:undefined},timestamp:Date.now(),runId:'run1',hypothesisId:'H3'})}).catch(()=>{})
      // #endregion
      setProjects(Array.isArray(projects) ? projects : [])
      setLoading(false)
    } catch (error: any) {
      // #region agent log
      fetch('http://127.0.0.1:7242/ingest/66ddcc6b-d2d0-4156-a371-04fea067f11b',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'projects/page.tsx:loadProjects:catch',message:'loadProjects error',data:{detail:(error as any)?.detail,status:(error as any)?.status,url:(error as any)?.url,parsed:(error as any)?.parsed,bodyPreview:(error as any)?.debug?.bodyPreview},timestamp:Date.now(),runId:'run1',hypothesisId:'H2'})}).catch(()=>{})
      // #endregion
      console.error('Failed to load projects:', error)
      setLoading(false)
    }
  }

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return

    try {
      const project = await apiPostData<Project>('/api/v1/projects', {
        name: newProjectName,
        description: newProjectDesc || null,
      })
      setNewProjectName('')
      setNewProjectDesc('')
      setIsCreateFormOpen(false)
      await loadProjects()
      // Navigate to new project dashboard
      router.push(`/app/project/${project.id}/dashboard`)
    } catch (error: any) {
      console.error('Failed to create project:', error)
      // Show detailed error from API response
      const errorMessage = error?.detail || error?.message || String(error) || 'Failed to create project'
      alert(errorMessage)
    }
  }

  const handleCancelCreate = () => {
    setNewProjectName('')
    setNewProjectDesc('')
    setIsCreateFormOpen(false)
  }

  const handleProjectClick = (projectId: number) => {
    router.push(`/app/project/${projectId}/dashboard`)
  }

  const handleProjectSettings = (projectId: number) => {
    router.push(`/app/project/${projectId}/settings`)
  }

  return (
    <div className="container">
      {/* Create Project Form - shown only when isCreateFormOpen is true */}
      {isCreateFormOpen && (
        <div className="card" style={{ marginTop: '0', marginBottom: '32px', padding: '24px' }}>
          <h3 style={{ marginBottom: '20px', fontSize: '1.5rem', fontWeight: '600', color: '#333' }}>Создать новый проект</h3>
          <div className="form-group" style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>Название проекта *</label>
            <input
              ref={projectNameInputRef}
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Введите название проекта"
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid #ddd',
                borderRadius: '5px',
                fontSize: '14px'
              }}
            />
          </div>
          <div className="form-group" style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500' }}>Описание</label>
            <textarea
              value={newProjectDesc}
              onChange={(e) => setNewProjectDesc(e.target.value)}
              placeholder="Введите описание проекта (необязательно)"
              rows={3}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: '1px solid #ddd',
                borderRadius: '5px',
                fontSize: '14px',
                fontFamily: 'inherit',
                resize: 'vertical'
              }}
            />
          </div>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              className="btn-secondary"
              onClick={handleCancelCreate}
            >
              Отмена
            </button>
            <button
              className="btn-primary"
              onClick={handleCreateProject}
              disabled={!newProjectName.trim()}
            >
              Создать
            </button>
          </div>
        </div>
      )}

      {/* Projects List */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ marginBottom: '0' }}>Мои проекты</h2>
          {!isCreateFormOpen && (
            <button onClick={() => setIsCreateFormOpen(true)}>+ Новый проект</button>
          )}
        </div>

        {loading ? (
          <p>Загрузка...</p>
        ) : projects.length === 0 ? (
          <p>Проектов пока нет. Создайте первый проект!</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px' }}>
            {projects.map((project) => (
              <div
                key={project.id}
                className="card"
                style={{ cursor: 'pointer', padding: '20px' }}
                onClick={() => handleProjectClick(project.id)}
              >
                <h3>{project.name}</h3>
                {project.description && <p style={{ color: '#666', marginTop: '10px' }}>{project.description}</p>}
                <div style={{ marginTop: '15px', fontSize: '0.9rem', color: '#999' }}>
                  <div>Роль: <strong>{roleLabels[project.role] ?? project.role}</strong></div>
                  <div>Создан: {new Date(project.created_at).toLocaleDateString()}</div>
                </div>
                <div style={{ marginTop: '16px', display: 'flex', gap: '10px' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleProjectClick(project.id)
                    }}
                  >
                    Открыть
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleProjectSettings(project.id)
                    }}
                  >
                    Настройки
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

