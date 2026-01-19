'use client'

import { useState, useEffect } from 'react'
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
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [newProjectDesc, setNewProjectDesc] = useState('')

  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    try {
      setLoading(true)
      const projects = await apiGetData<Project[]>('/v1/projects')
      setProjects(projects)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load projects:', error)
      setLoading(false)
    }
  }

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return

    try {
      const project = await apiPostData<Project>('/v1/projects', {
        name: newProjectName,
        description: newProjectDesc || null,
      })
      setShowCreateModal(false)
      setNewProjectName('')
      setNewProjectDesc('')
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

  const handleProjectClick = (projectId: number) => {
    router.push(`/app/project/${projectId}/dashboard`)
  }

  const handleProjectSettings = (projectId: number) => {
    router.push(`/app/project/${projectId}/settings`)
  }

  return (
    <div className="container">
      <h1>Projects</h1>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2>My Projects</h2>
          <button onClick={() => setShowCreateModal(true)}>+ New Project</button>
        </div>

        {loading ? (
          <p>Loading...</p>
        ) : projects.length === 0 ? (
          <p>No projects yet. Create your first project!</p>
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
                  <div>Role: <strong>{project.role}</strong></div>
                  <div>Created: {new Date(project.created_at).toLocaleDateString()}</div>
                </div>
                <div style={{ marginTop: '16px', display: 'flex', gap: '10px' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleProjectClick(project.id)
                    }}
                  >
                    Open
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleProjectSettings(project.id)
                    }}
                  >
                    Settings
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Create New Project</h3>
            <div className="form-group">
              <label>Project Name *</label>
              <input
                type="text"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="Enter project name"
                autoFocus
              />
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea
                value={newProjectDesc}
                onChange={(e) => setNewProjectDesc(e.target.value)}
                placeholder="Enter project description (optional)"
                rows={3}
              />
            </div>
            <div className="modal-actions">
              <button onClick={() => setShowCreateModal(false)}>Cancel</button>
              <button onClick={handleCreateProject} disabled={!newProjectName.trim()}>
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

