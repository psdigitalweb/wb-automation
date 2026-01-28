'use client'

import { useState, useEffect, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { getUser } from '../../../../../lib/auth'
import { isSuperuser } from '../../../../../lib/admin'
import { apiGetData, apiPostData, apiPatchData, apiDeleteData } from '../../../../../lib/apiClient'

interface AdminProjectMember {
  id: number
  project_id: number
  user_id: number
  username: string
  email: string | null
  role: string
  created_at: string
  updated_at: string
}

interface AdminUser {
  id: number
  username: string
  email: string | null
  is_active: boolean
  is_superuser: boolean
}

interface AdminUserListResponse {
  users: AdminUser[]
  total: number
}

export default function AdminProjectMembersPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const currentUser = getUser()
  const [members, setMembers] = useState<AdminProjectMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  // Add member form
  const [userSearchQuery, setUserSearchQuery] = useState('')
  const [availableUsers, setAvailableUsers] = useState<AdminUser[]>([])
  const [searchingUsers, setSearchingUsers] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [newRole, setNewRole] = useState('member')
  const [submitting, setSubmitting] = useState(false)
  const [showUserDropdown, setShowUserDropdown] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Check permissions
  useEffect(() => {
    if (!isSuperuser()) {
      router.push('/app/projects')
    }
  }, [router])

  // Load members
  useEffect(() => {
    if (projectId) {
      loadMembers()
    }
  }, [projectId])

  // Search users when query changes
  useEffect(() => {
    if (userSearchQuery.trim().length >= 2) {
      const timeoutId = setTimeout(() => {
        searchUsers()
      }, 400)
      return () => clearTimeout(timeoutId)
    } else {
      setAvailableUsers([])
      setShowUserDropdown(false)
    }
  }, [userSearchQuery])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        searchInputRef.current &&
        !searchInputRef.current.contains(event.target as Node)
      ) {
        setShowUserDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const loadMembers = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await apiGetData<AdminProjectMember[]>(
        `/api/v1/admin/projects/${projectId}/members`
      )
      setMembers(response)
    } catch (err: any) {
      console.error('Failed to load members:', err)
      setError(err?.detail || 'Failed to load members')
      if (err?.status === 403) {
        router.push('/app/projects')
      }
    } finally {
      setLoading(false)
    }
  }

  const searchUsers = async () => {
    try {
      setSearchingUsers(true)
      const params = new URLSearchParams({
        limit: '20',
        offset: '0',
        q: userSearchQuery.trim(),
      })
      const response = await apiGetData<AdminUserListResponse>(`/api/v1/admin/users?${params}`)
      setAvailableUsers(response.users)
      setShowUserDropdown(true)
    } catch (err: any) {
      console.error('Failed to search users:', err)
      setAvailableUsers([])
    } finally {
      setSearchingUsers(false)
    }
  }

  const handleSelectUser = (user: AdminUser) => {
    setSelectedUser(user)
    setSelectedUserId(user.id)
    setUserSearchQuery(`${user.username}${user.email ? ` — ${user.email}` : ''} (ID: ${user.id})`)
    setShowUserDropdown(false)
  }

  const handleAddMember = async () => {
    if (!selectedUserId) {
      showToast('Выберите пользователя', 'error')
      return
    }

    try {
      setSubmitting(true)
      await apiPostData(`/api/v1/admin/projects/${projectId}/members`, {
        user_id: selectedUserId,
        role: newRole,
      })
      showToast('Участник добавлен', 'success')
      setShowAddModal(false)
      resetForm()
      await loadMembers()
    } catch (err: any) {
      console.error('Failed to add member:', err)
      const errorMsg = err?.detail || 'Не удалось добавить участника'
      if (err?.status === 409) {
        showToast('Пользователь уже добавлен в проект', 'error')
      } else if (err?.status === 403) {
        showToast('Недостаточно прав', 'error')
      } else {
        showToast(errorMsg, 'error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleUpdateRole = async (userId: number, newRole: string) => {
    try {
      await apiPatchData(`/api/v1/admin/projects/${projectId}/members/${userId}`, {
        role: newRole,
      })
      showToast('Роль обновлена', 'success')
      await loadMembers()
    } catch (err: any) {
      console.error('Failed to update role:', err)
      showToast(err?.detail || 'Не удалось обновить роль', 'error')
    }
  }

  const handleRemoveMember = async (userId: number, username: string) => {
    if (!confirm(`Удалить "${username}" из проекта?`)) {
      return
    }

    try {
      await apiDeleteData(`/api/v1/admin/projects/${projectId}/members/${userId}`)
      showToast('Участник удален', 'success')
      await loadMembers()
    } catch (err: any) {
      console.error('Failed to remove member:', err)
      showToast(err?.detail || 'Не удалось удалить участника', 'error')
    }
  }

  const resetForm = () => {
    setSelectedUserId(null)
    setSelectedUser(null)
    setUserSearchQuery('')
    setNewRole('member')
  }

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 5000)
  }

  if (!isSuperuser()) {
    return (
      <div className="container">
        <h1>Access Denied</h1>
        <p>Not enough permissions. Superuser access required.</p>
      </div>
    )
  }

  return (
    <div className="container">
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '24px',
          gap: '16px',
        }}
      >
        <h1 style={{ margin: 0 }}>Участники проекта</h1>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <button
            onClick={() => router.back()}
            className="btn-secondary"
            style={{ padding: '8px 16px', height: '36px' }}
          >
            ← Назад
          </button>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            backgroundColor: toast.type === 'success' ? '#28a745' : '#dc3545',
            color: 'white',
            borderRadius: '4px',
            zIndex: 10000,
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          }}
        >
          {toast.message}
        </div>
      )}

      {/* Members Table */}
      <div className="card">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '20px',
          }}
        >
          <h2 style={{ margin: 0 }}>Участники</h2>
          <button
            onClick={() => setShowAddModal(true)}
            className="btn-primary"
            style={{ padding: '8px 16px', height: '36px' }}
          >
            + Добавить участника
          </button>
        </div>

        {loading ? (
          <p>Загрузка...</p>
        ) : error ? (
          <p style={{ color: '#dc3545' }}>{error}</p>
        ) : members.length === 0 ? (
          <p>Участники не найдены</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #ddd' }}>
                  <th style={{ padding: '12px', textAlign: 'left', width: '35%' }}>Username</th>
                  <th style={{ padding: '12px', textAlign: 'left', width: '35%' }}>Email</th>
                  <th style={{ padding: '12px', textAlign: 'left', width: '20%' }}>Role</th>
                  <th style={{ padding: '12px', textAlign: 'center', width: '10%' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '12px' }}>{member.username}</td>
                    <td style={{ padding: '12px', color: member.email ? '#333' : '#999' }}>
                      {member.email || '-'}
                    </td>
                    <td style={{ padding: '12px' }}>
                      <select
                        value={member.role}
                        onChange={(e) => handleUpdateRole(member.user_id, e.target.value)}
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          fontSize: '14px',
                          border: '1px solid #ddd',
                          borderRadius: '4px',
                          backgroundColor: 'white',
                        }}
                      >
                        <option value="viewer">Viewer</option>
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                        <option value="owner">Owner</option>
                      </select>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <button
                        onClick={() => handleRemoveMember(member.user_id, member.username)}
                        style={{
                          padding: '4px 12px',
                          backgroundColor: '#dc3545',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '13px',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = '#c82333'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = '#dc3545'
                        }}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Member Modal */}
      {showAddModal && (
        <div
          className="modal-overlay"
          onClick={() => {
            setShowAddModal(false)
            resetForm()
          }}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: 'white',
              padding: '24px',
              borderRadius: '8px',
              maxWidth: '500px',
              width: '90%',
              maxHeight: '90vh',
              overflow: 'auto',
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            }}
          >
            <h2 style={{ marginTop: 0, marginBottom: '20px' }}>Добавить участника</h2>

            {/* User Search Combobox */}
            <div className="form-group" style={{ marginBottom: '16px', position: 'relative' }}>
              <label
                style={{
                  display: 'block',
                  marginBottom: '6px',
                  fontWeight: '500',
                  fontSize: '14px',
                }}
              >
                Пользователь *
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  ref={searchInputRef}
                  type="text"
                  value={userSearchQuery}
                  onChange={(e) => {
                    setUserSearchQuery(e.target.value)
                    if (selectedUser) {
                      setSelectedUser(null)
                      setSelectedUserId(null)
                    }
                  }}
                  onFocus={() => {
                    if (availableUsers.length > 0) {
                      setShowUserDropdown(true)
                    }
                  }}
                  placeholder="Введите username или email для поиска..."
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    fontSize: '14px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                  autoFocus
                />
                {searchingUsers && (
                  <div
                    style={{
                      position: 'absolute',
                      right: '12px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: '12px',
                      color: '#666',
                    }}
                  >
                    Поиск...
                  </div>
                )}
              </div>

              {/* Dropdown */}
              {showUserDropdown && availableUsers.length > 0 && (
                <div
                  ref={dropdownRef}
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    marginTop: '4px',
                    backgroundColor: 'white',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                    maxHeight: '200px',
                    overflowY: 'auto',
                    zIndex: 1001,
                  }}
                >
                  {availableUsers.map((user) => (
                    <div
                      key={user.id}
                      onClick={() => handleSelectUser(user)}
                      style={{
                        padding: '10px 12px',
                        cursor: 'pointer',
                        borderBottom: '1px solid #f0f0f0',
                        fontSize: '14px',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = '#f8f9fa'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'white'
                      }}
                    >
                      <div style={{ fontWeight: '500' }}>{user.username}</div>
                      <div style={{ fontSize: '12px', color: '#666', marginTop: '2px' }}>
                        {user.email || 'Нет email'} {user.is_superuser && '(Superuser)'} (ID: {user.id})
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {availableUsers.length === 0 &&
                userSearchQuery.trim().length >= 2 &&
                !searchingUsers && (
                  <div
                    style={{
                      marginTop: '4px',
                      padding: '8px 12px',
                      fontSize: '13px',
                      color: '#666',
                      backgroundColor: '#f8f9fa',
                      borderRadius: '4px',
                    }}
                  >
                    Пользователи не найдены
                  </div>
                )}
            </div>

            {/* Role Select */}
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label
                style={{
                  display: 'block',
                  marginBottom: '6px',
                  fontWeight: '500',
                  fontSize: '14px',
                }}
              >
                Роль
              </label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  fontSize: '14px',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  backgroundColor: 'white',
                }}
              >
                <option value="viewer">Viewer</option>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
                <option value="owner">Owner</option>
              </select>
            </div>

            {/* Actions */}
            <div
              style={{
                display: 'flex',
                gap: '12px',
                justifyContent: 'flex-end',
                marginTop: '24px',
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setShowAddModal(false)
                  resetForm()
                }}
                className="btn-secondary"
                style={{ padding: '8px 16px', height: '36px' }}
                disabled={submitting}
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleAddMember}
                disabled={!selectedUserId || submitting}
                className="btn-primary"
                style={{ padding: '8px 16px', height: '36px' }}
              >
                {submitting ? 'Добавление...' : 'Добавить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
