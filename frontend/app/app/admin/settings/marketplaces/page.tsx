'use client'

import { useEffect, useState } from 'react'
import { apiGet, apiPut, ApiError } from '../../../../../lib/apiClient'
import { getUser, User } from '../../../../../lib/auth'

interface SystemMarketplaceSettings {
  marketplace_code: string
  display_name?: string | null
  is_globally_enabled: boolean
  is_visible: boolean
  sort_order: number
  settings_json: Record<string, any>
  has_record: boolean
  created_at?: string | null
  updated_at?: string | null
}

export default function SystemMarketplacesAdminPage() {
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [loadingUser, setLoadingUser] = useState<boolean>(true)
  const [settings, setSettings] = useState<SystemMarketplaceSettings[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const [editingJson, setEditingJson] = useState<Record<string, { open: boolean; value: string }>>({})

  const localUser = getUser()
  const isAdmin = (currentUser?.is_superuser ?? localUser?.is_superuser) ?? false

  useEffect(() => {
    const loadMe = async () => {
      try {
        setLoadingUser(true)
        const { data } = await apiGet<User>('/api/v1/auth/me')
        setCurrentUser(data)
      } catch (e) {
        setCurrentUser(null)
      } finally {
        setLoadingUser(false)
      }
    }
    loadMe()
  }, [])

  useEffect(() => {
    if (!loadingUser && isAdmin) {
      loadSettings()
    }
  }, [loadingUser, isAdmin])

  const loadSettings = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await apiGet<SystemMarketplaceSettings[]>(
        '/api/v1/admin/system-marketplaces'
      )
      setSettings(data)
    } catch (e: any) {
      const err = e as ApiError
      if (err.status === 401 || err.status === 403) {
        setError('Недостаточно прав (требуется admin/superuser).')
      } else {
        setError(err.detail || 'Не удалось загрузить настройки.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleToggleEnabled = async (code: string, currentValue: boolean) => {
    await saveSetting(code, { is_globally_enabled: !currentValue })
  }

  const handleToggleVisible = async (code: string, currentValue: boolean) => {
    await saveSetting(code, { is_visible: !currentValue })
  }

  const handleSortOrderChange = async (code: string, value: number) => {
    await saveSetting(code, { sort_order: value })
  }

  const handleEditJson = (code: string) => {
    const setting = settings.find(s => s.marketplace_code === code)
    if (setting) {
      setEditingJson({
        ...editingJson,
        [code]: {
          open: true,
          value: JSON.stringify(setting.settings_json, null, 2),
        },
      })
    }
  }

  const handleSaveJson = async (code: string) => {
    const editState = editingJson[code]
    if (!editState) return

    try {
      const parsed = JSON.parse(editState.value)
      await saveSetting(code, { settings_json: parsed })
      setEditingJson({
        ...editingJson,
        [code]: { ...editState, open: false },
      })
    } catch (e: any) {
      alert(`Ошибка парсинга JSON: ${e.message}`)
    }
  }

  const handleCancelJson = (code: string) => {
    setEditingJson({
      ...editingJson,
      [code]: { ...editingJson[code], open: false },
    })
  }

  const saveSetting = async (code: string, update: Partial<SystemMarketplaceSettings>) => {
    setSaving({ ...saving, [code]: true })
    setError(null)
    try {
      const { data } = await apiPut<SystemMarketplaceSettings>(
        `/api/v1/admin/system-marketplaces/${code}`,
        update
      )
      // Update local state
      setSettings(settings.map(s => s.marketplace_code === code ? data : s))
    } catch (e: any) {
      const err = e as ApiError
      setError(err.detail || `Не удалось сохранить настройки для ${code}`)
      alert(err.detail || `Не удалось сохранить настройки для ${code}`)
    } finally {
      setSaving({ ...saving, [code]: false })
    }
  }

  if (loadingUser) {
    return (
      <div className="container">
        <h1>System Marketplaces (Admin)</h1>
        <p>Загрузка информации о пользователе...</p>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="container">
        <h1>System Marketplaces (Admin)</h1>
        <p>Недостаточно прав для просмотра этого раздела. Требуются admin/superuser права.</p>
      </div>
    )
  }

  return (
    <div className="container">
      <h1>System Marketplaces (Admin)</h1>
      <p style={{ marginBottom: '16px', color: '#666' }}>
        Глобальные системные настройки маркетплейсов. Эти настройки применяются ко всем проектам.
      </p>

      {error && (
        <div style={{ 
          padding: '12px', 
          marginBottom: '16px', 
          backgroundColor: '#f8d7da', 
          color: '#721c24', 
          borderRadius: '4px' 
        }}>
          <strong>Ошибка:</strong> {error}
        </div>
      )}

      <div className="card" style={{ marginTop: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 style={{ margin: 0 }}>Настройки маркетплейсов</h2>
          <button onClick={loadSettings} disabled={loading}>
            {loading ? 'Загрузка...' : 'Обновить'}
          </button>
        </div>

        {loading && <p>Загрузка настроек...</p>}

        {!loading && settings.length === 0 && (
          <p>Нет маркетплейсов для настройки.</p>
        )}

        {!loading && settings.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '8px' }}>Marketplace</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Globally Enabled</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Visible</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Sort Order</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Settings JSON</th>
                <th style={{ textAlign: 'left', padding: '8px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {settings.map((setting) => {
                const isSaving = saving[setting.marketplace_code] || false
                const jsonEdit = editingJson[setting.marketplace_code]

                return (
                  <tr key={setting.marketplace_code}>
                    <td style={{ padding: '8px' }}>
                      <strong>{setting.display_name || setting.marketplace_code}</strong>
                      <br />
                      <small style={{ color: '#666' }}>{setting.marketplace_code}</small>
                    </td>
                    <td style={{ padding: '8px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="checkbox"
                          checked={setting.is_globally_enabled}
                          onChange={() => handleToggleEnabled(setting.marketplace_code, setting.is_globally_enabled)}
                          disabled={isSaving}
                        />
                        <span>{setting.is_globally_enabled ? 'Enabled' : 'Disabled'}</span>
                      </label>
                    </td>
                    <td style={{ padding: '8px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="checkbox"
                          checked={setting.is_visible}
                          onChange={() => handleToggleVisible(setting.marketplace_code, setting.is_visible)}
                          disabled={isSaving}
                        />
                        <span>{setting.is_visible ? 'Visible' : 'Hidden'}</span>
                      </label>
                    </td>
                    <td style={{ padding: '8px' }}>
                      <input
                        type="number"
                        value={setting.sort_order}
                        onChange={(e) => {
                          const val = parseInt(e.target.value, 10)
                          if (!isNaN(val)) {
                            handleSortOrderChange(setting.marketplace_code, val)
                          }
                        }}
                        disabled={isSaving}
                        style={{ width: '80px', padding: '4px' }}
                      />
                    </td>
                    <td style={{ padding: '8px' }}>
                      {jsonEdit?.open ? (
                        <div>
                          <textarea
                            value={jsonEdit.value}
                            onChange={(e) => {
                              setEditingJson({
                                ...editingJson,
                                [setting.marketplace_code]: {
                                  ...jsonEdit,
                                  value: e.target.value,
                                },
                              })
                            }}
                            rows={4}
                            style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px' }}
                          />
                          <div style={{ marginTop: '4px', display: 'flex', gap: '4px' }}>
                            <button
                              onClick={() => handleSaveJson(setting.marketplace_code)}
                              disabled={isSaving}
                              style={{ fontSize: '12px', padding: '4px 8px' }}
                            >
                              Save
                            </button>
                            <button
                              onClick={() => handleCancelJson(setting.marketplace_code)}
                              disabled={isSaving}
                              style={{ fontSize: '12px', padding: '4px 8px' }}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={() => handleEditJson(setting.marketplace_code)}
                          disabled={isSaving}
                          style={{ fontSize: '12px', padding: '4px 8px' }}
                        >
                          Edit JSON
                        </button>
                      )}
                    </td>
                    <td style={{ padding: '8px' }}>
                      {isSaving ? (
                        <span style={{ color: '#666' }}>Saving...</span>
                      ) : setting.has_record ? (
                        <span style={{ color: '#28a745' }}>✓ Saved</span>
                      ) : (
                        <span style={{ color: '#ffc107' }}>Default</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
