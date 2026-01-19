'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPost, apiPut, apiDelete } from '../../../../../lib/apiClient'
import { getUser } from '../../../../../lib/auth'
import '../../../../globals.css'

interface ProjectMember {
  id: number
  user_id: number
  role: string
  username: string
  email: string | null
}

export default function ProjectMembersPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const currentUser = getUser()
  const [members, setMembers] = useState<ProjectMember[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [newUserId, setNewUserId] = useState('')
  const [newRole, setNewRole] = useState('member')

  useEffect(() => {
    loadMembers()
  }, [projectId])

  const loadMembers = async () => {
    try {
      setLoading(true)
      const { data: project } = await apiGet<any>(`/v1/projects/${projectId}`)
      setMembers(project.members || [])
      setLoading(false)
    } catch (error) {
      console.error('Failed to load members:', error)
      setLoading(false)
    }
  }

  const handleAddMember = async () => {
    if (!newUserId.trim()) return

    try {
      await apiPost(`/v1/projects/${projectId}/members`, {
        user_id: parseInt(newUserId),
        role: newRole
      })
      setShowAddModal(false)
      setNewUserId('')
      setNewRole('member')
      await loadMembers()
    } catch (error: any) {
      alert(error.detail || 'Failed to add member')
    }
  }

  const handleRoleChange = async (userId: number, newRole: string) => {
    try {
      await apiPut(`/v1/projects/${projectId}/members/${userId}`, {
        role: newRole
      })
      await loadMembers()
    } catch (error: any) {
      alert(error.detail || 'Failed to update role')
    }
  }

  const handleRemoveMember = async (userId: number) => {
    if (!confirm('Remove this member from project?')) return

    try {
      await apiDelete(`/v1/projects/${projectId}/members/${userId}`)
      await loadMembers()
    } catch (error: any) {
      alert(error.detail || 'Failed to remove member')
    }
  }

  const canManage = currentUser?.is_superuser || members.find(m => m.user_id === currentUser?.id)?.role === 'owner' || members.find(m => m.user_id === currentUser?.id)?.role === 'admin'

  return (
    <div className="container">
      <h1>Project Members</h1>
      <button onClick={() => router.back()} style={{ marginBottom: '20px' }}>
        ← Back
      </button>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2>Members</h2>
          {canManage && (
            <button onClick={() => setShowAddModal(true)}>+ Add Member</button>
          )}
        </div>

        {loading ? (
          <p>Loading...</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.id}>
                  <td>{member.username}</td>
                  <td>{member.email || '-'}</td>
                  <td>
                    {canManage ? (
                      <select
                        value={member.role}
                        onChange={(e) => handleRoleChange(member.user_id, e.target.value)}
                      >
                        <option value="viewer">Viewer</option>
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                        <option value="owner">Owner</option>
                      </select>
                    ) : (
                      <strong>{member.role}</strong>
                    )}
                  </td>
                  <td>
                    {canManage && member.user_id !== currentUser?.id && (
                      <button
                        onClick={() => handleRemoveMember(member.user_id)}
                        style={{ backgroundColor: '#dc3545' }}
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Add Member</h3>
            <div className="form-group">
              <label>User ID *</label>
              <input
                type="number"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
                placeholder="Enter user ID"
                autoFocus
              />
            </div>
            <div className="form-group">
              <label>Role</label>
              <select value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                <option value="viewer">Viewer</option>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div className="modal-actions">
              <button onClick={() => setShowAddModal(false)}>Cancel</button>
              <button onClick={handleAddMember} disabled={!newUserId.trim()}>
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}




