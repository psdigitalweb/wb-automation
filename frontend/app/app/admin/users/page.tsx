'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { getUser } from '../../../../lib/auth'
import { isSuperuser } from '../../../../lib/admin'
import { apiGetData, apiPostData, apiDeleteData, ApiError } from '../../../../lib/apiClient'

interface AdminUser {
  id: number
  username: string
  email: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string
  updated_at: string
}

interface AdminUserListResponse {
  users: AdminUser[]
  total: number
}

export default function AdminUsersPage() {
  const router = useRouter()
  const currentUser = getUser()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  // Form state
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    is_active: true,
    is_superuser: false,
  })

  // Check permissions
  useEffect(() => {
    if (!isSuperuser()) {
      router.push('/app/projects')
    }
  }, [router])

  // Load users
  useEffect(() => {
    loadUsers()
  }, [limit, offset, searchQuery])

  const loadUsers = async () => {
    try {
      setLoading(true)
      setError(null)
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      })
      if (searchQuery.trim()) {
        params.append('q', searchQuery.trim())
      }
      const response = await apiGetData<AdminUserListResponse>(`/api/v1/admin/users?${params}`)
      setUsers(response.users)
      setTotal(response.total)
    } catch (err: any) {
      console.error('Failed to load users:', err)
      setError(err?.detail || 'Failed to load users')
      if (err?.status === 403) {
        router.push('/app/projects')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.username.trim() || !formData.password.trim()) {
      showToast('Username and password are required', 'error')
      return
    }

    try {
      setCreating(true)
      const payload = {
        username: formData.username.trim(),
        email: formData.email.trim() || null,
        password: formData.password,
        is_active: formData.is_active,
        is_superuser: formData.is_superuser,
      }
      await apiPostData('/api/v1/admin/users', payload)
      showToast('User created successfully', 'success')
      setShowCreateModal(false)
      setFormData({
        username: '',
        email: '',
        password: '',
        is_active: true,
        is_superuser: false,
      })
      await loadUsers()
    } catch (err: any) {
      console.error('Failed to create user:', err)
      showToast(err?.detail || 'Failed to create user', 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleDeleteUser = async (userId: number, username: string) => {
    if (!confirm(`Are you sure you want to delete user "${username}"?`)) {
      return
    }

    try {
      await apiDeleteData(`/api/v1/admin/users/${userId}`)
      showToast('User deleted successfully', 'success')
      await loadUsers()
    } catch (err: any) {
      console.error('Failed to delete user:', err)
      const errorMsg = err?.detail || 'Failed to delete user'
      if (errorMsg.includes('last superuser')) {
        showToast('Cannot delete the last superuser in the system', 'error')
      } else {
        showToast(errorMsg, 'error')
      }
    }
  }

  const showToast = (message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 5000)
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1>Пользователи</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary"
          style={{ padding: '8px 16px' }}
        >
          + Создать пользователя
        </button>
      </div>

      {/* Search */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Поиск по username или email..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setOffset(0) // Reset to first page on search
            }}
            style={{ flex: 1, padding: '8px 12px', fontSize: '14px' }}
          />
          <button
            onClick={() => {
              setSearchQuery('')
              setOffset(0)
            }}
            style={{ padding: '8px 16px' }}
          >
            Очистить
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

      {/* Table */}
      <div className="card">
        {loading ? (
          <p>Загрузка...</p>
        ) : error ? (
          <p style={{ color: '#dc3545' }}>{error}</p>
        ) : users.length === 0 ? (
          <p>Пользователи не найдены</p>
        ) : (
          <>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #ddd' }}>
                  <th style={{ padding: '12px', textAlign: 'left' }}>Username</th>
                  <th style={{ padding: '12px', textAlign: 'left' }}>Email</th>
                  <th style={{ padding: '12px', textAlign: 'center' }}>Active</th>
                  <th style={{ padding: '12px', textAlign: 'center' }}>Superuser</th>
                  <th style={{ padding: '12px', textAlign: 'left' }}>Created</th>
                  <th style={{ padding: '12px', textAlign: 'center' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '12px' }}>{user.username}</td>
                    <td style={{ padding: '12px' }}>{user.email || '-'}</td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      {user.is_active ? '✓' : '✗'}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      {user.is_superuser ? '✓' : '-'}
                    </td>
                    <td style={{ padding: '12px', fontSize: '13px', color: '#666' }}>
                      {formatDate(user.created_at)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <button
                        onClick={() => handleDeleteUser(user.id, user.username)}
                        style={{
                          padding: '4px 12px',
                          backgroundColor: '#dc3545',
                          color: 'white',
                          border: 'none',
                          borderRadius: '4px',
                          cursor: 'pointer',
                          fontSize: '13px',
                        }}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ color: '#666', fontSize: '14px' }}>
                Показано {offset + 1}-{Math.min(offset + limit, total)} из {total}
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                  style={{ padding: '6px 12px', cursor: offset === 0 ? 'not-allowed' : 'pointer' }}
                >
                  ← Назад
                </button>
                <button
                  onClick={() => setOffset(offset + limit)}
                  disabled={offset + limit >= total}
                  style={{
                    padding: '6px 12px',
                    cursor: offset + limit >= total ? 'not-allowed' : 'pointer',
                  }}
                >
                  Вперед →
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div
          className="modal-overlay"
          onClick={() => setShowCreateModal(false)}
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
            }}
          >
            <h2 style={{ marginTop: 0 }}>Создать пользователя</h2>
            <form onSubmit={handleCreateUser}>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontWeight: '500' }}>
                  Username *
                </label>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px 12px', fontSize: '14px' }}
                  autoFocus
                />
              </div>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontWeight: '500' }}>
                  Email (optional)
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', fontSize: '14px' }}
                />
              </div>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '4px', fontWeight: '500' }}>
                  Password *
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px 12px', fontSize: '14px' }}
                />
              </div>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                  Active
                </label>
              </div>
              <div className="form-group" style={{ marginBottom: '20px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <input
                    type="checkbox"
                    checked={formData.is_superuser}
                    onChange={(e) => setFormData({ ...formData, is_superuser: e.target.checked })}
                  />
                  Superuser
                </label>
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  style={{ padding: '8px 16px' }}
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="btn-primary"
                  style={{ padding: '8px 16px' }}
                >
                  {creating ? 'Создание...' : 'Создать'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
