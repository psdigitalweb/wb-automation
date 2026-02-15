'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPatch, apiPost, apiPut, ApiError } from '../../../../../lib/apiClient'
import { User } from '../../../../../lib/auth'

interface Marketplace {
  id: number
  code: string
  name: string
  description: string | null
  is_active: boolean
}

interface ProjectMarketplace {
  id: number
  marketplace_id: number
  is_enabled: boolean
  marketplace_code: string
  marketplace_name: string
  marketplace_description: string | null
}

interface WBMarketplaceStatus {
  is_enabled: boolean
  is_configured: boolean
  credentials: { api_token: boolean }
  settings: { brand_id?: number | null }
  updated_at: string
}

interface SystemMarketplacePublicStatus {
  marketplace_code: string
  is_globally_enabled: boolean
  is_visible: boolean
  sort_order: number
}

export default function ProjectMarketplacesPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [allMarketplaces, setAllMarketplaces] = useState<Marketplace[]>([])
  const [projectMarketplaces, setProjectMarketplaces] = useState<ProjectMarketplace[]>([])
  const [loading, setLoading] = useState(true)
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [loadingUser, setLoadingUser] = useState(true)

  // Admin WB tariffs state (global, marketplace-level)
  const [wbTariffsStatus, setWbTariffsStatus] = useState<any | null>(null)
  const [wbTariffsLoading, setWbTariffsLoading] = useState(false)
  const [wbTariffsIngesting, setWbTariffsIngesting] = useState(false)
  const [wbTariffsCooldown, setWbTariffsCooldown] = useState(false)
  const [wbTariffsDaysAhead, setWbTariffsDaysAhead] = useState<number>(14)
  const [wbTariffsError, setWbTariffsError] = useState<string | null>(null)

  
  // WB-specific state
  const [wbStatus, setWbStatus] = useState<WBMarketplaceStatus | null>(null)
  const [wbShowForm, setWbShowForm] = useState(false)
  const [wbToken, setWbToken] = useState('')
  const [wbLoading, setWbLoading] = useState(false)
  const [wbError, setWbError] = useState<string | null>(null)

  // System marketplace settings (global status)
  const [systemMarketplaceStatuses, setSystemMarketplaceStatuses] = useState<Record<string, SystemMarketplacePublicStatus>>({})
  const [systemStatusLoading, setSystemStatusLoading] = useState(false)

  useEffect(() => {
    loadData()
    loadSystemMarketplaceStatuses()
  }, [projectId])

  const loadSystemMarketplaceStatuses = async () => {
    setSystemStatusLoading(true)
    try {
      const { data } = await apiGet<SystemMarketplacePublicStatus[]>('/api/v1/system/marketplaces')
      // Convert array to map by marketplace_code
      const statusMap: Record<string, SystemMarketplacePublicStatus> = {}
      data.forEach(status => {
        statusMap[status.marketplace_code] = status
      })
      setSystemMarketplaceStatuses(statusMap)
    } catch (error) {
      // Fail-safe: if endpoint fails, ignore and continue (backward compatibility)
      console.warn('Failed to load system marketplace statuses:', error)
      setSystemMarketplaceStatuses({})
    } finally {
      setSystemStatusLoading(false)
    }
  }

  const loadData = async () => {
    try {
      setLoading(true)
      const [marketplacesRes, projectMpsRes] = await Promise.all([
        apiGet<Marketplace[]>('/api/v1/marketplaces?active_only=true'),
        apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
      ])
      setAllMarketplaces(marketplacesRes.data)
      setProjectMarketplaces(projectMpsRes.data)
      
      // Load WB status separately
      try {
        const wbStatusRes = await apiGet<WBMarketplaceStatus>(`/api/v1/projects/${projectId}/marketplaces/wb`)
        const wbStatusData = wbStatusRes.data
        setWbStatus(wbStatusData)
        // Show form if enabled but not configured (token missing)
        setWbShowForm(wbStatusData.is_enabled && !wbStatusData.is_configured)
      } catch (e: any) {
        // If WB status endpoint fails (e.g. backend not restarted yet), keep wbStatus null.
        // UI will fall back to project marketplace list for enabled/disabled state.
        console.warn('[WB_DEBUG] Failed to load WB status', e)
        setWbStatus(null)
        setWbShowForm(false)
      }
      
      setLoading(false)
    } catch (error) {
      console.error('Failed to load data:', error)
      setLoading(false)
    }
  }

  useEffect(() => {
    const loadMe = async () => {
      try {
        setLoadingUser(true)
        const { data } = await apiGet<User>('/api/v1/auth/me')
        setCurrentUser(data)
      } catch {
        setCurrentUser(null)
      } finally {
        setLoadingUser(false)
      }
    }
    loadMe()
  }, [])

  const isAdmin = currentUser?.is_superuser ?? false

  const loadWBTariffsStatus = async () => {
    if (!isAdmin) return
    setWbTariffsLoading(true)
    setWbTariffsError(null)
    try {
      const { data } = await apiGet<any>('/api/v1/admin/marketplaces/wildberries/tariffs/status')
      setWbTariffsStatus(data)
    } catch (e: any) {
      const err = e as ApiError
      if (err.status === 401 || err.status === 403) {
        setWbTariffsError('Недостаточно прав (требуется admin/superuser).')
      } else {
        setWbTariffsError(err.detail || 'Не удалось загрузить статус тарифов.')
      }
    } finally {
      setWbTariffsLoading(false)
    }
  }

  useEffect(() => {
    if (!loadingUser && isAdmin) {
      loadWBTariffsStatus()
    }
  }, [loadingUser, isAdmin])

  const handleWBTariffsIngest = async () => {
    if (!isAdmin) return
    setWbTariffsIngesting(true)
    setWbTariffsError(null)
    try {
      const payloadDays = Math.min(30, Math.max(0, wbTariffsDaysAhead || 0))
      await apiPost<any>(
        '/api/v1/admin/marketplaces/wildberries/tariffs/ingest',
        { days_ahead: payloadDays }
      )
      setWbTariffsCooldown(true)
      setTimeout(() => setWbTariffsCooldown(false), 10000)
      setTimeout(() => {
        loadWBTariffsStatus()
      }, 2500)
    } catch (e: any) {
      const err = e as ApiError
      if (err.status === 401 || err.status === 403) {
        setWbTariffsError('Недостаточно прав (требуется admin/superuser).')
      } else {
        setWbTariffsError(err.detail || 'Не удалось запустить обновление тарифов.')
      }
    } finally {
      setWbTariffsIngesting(false)
    }
  }

  const handleToggle = async (marketplaceId: number, marketplaceCode: string, currentEnabled: boolean) => {
    console.log('[WB_DEBUG] handleToggle called', { 
      marketplaceId, 
      marketplaceCode, 
      marketplaceCodeType: typeof marketplaceCode,
      marketplaceCodeLength: marketplaceCode?.length,
      currentEnabled 
    })
    
    // Special handling for Wildberries - check both code and ID (WB usually has ID=1)
    const isWildberries = marketplaceCode === 'wildberries' || marketplaceCode?.toLowerCase() === 'wildberries' || marketplaceId === 1
    
    if (isWildberries) {
      console.log('[WB_DEBUG] Routing to handleWBToggle for wildberries', { marketplaceCode, marketplaceId })
      await handleWBToggle(!currentEnabled)
      return
    }
    
    // Regular toggle for other marketplaces
    const url = `/api/v1/projects/${projectId}/marketplaces/${marketplaceId}/toggle`
    console.log('[WB_DEBUG] Regular toggle', { url, is_enabled: !currentEnabled })
    try {
      const { data: response } = await apiPatch(url, {
        is_enabled: !currentEnabled
      })
      console.log('[WB_DEBUG] Toggle success', response)
      await loadData()
    } catch (error: any) {
      console.error('[WB_DEBUG] Toggle error:', {
        url,
        status: error.status,
        detail: error.detail,
        message: error.message,
        fullError: error
      })
      alert(error.detail || 'Failed to toggle marketplace')
    }
  }

  const handleWBToggle = async (enabled: boolean) => {
    const url = `/api/v1/projects/${projectId}/marketplaces/wildberries`
    console.log('[WB_DEBUG] handleWBToggle called', { url, enabled })
    
    try {
      setWbLoading(true)
      setWbError(null)
      
      const { data: updatedStatus } = await apiPut<WBMarketplaceStatus>(
        url,
        { is_enabled: enabled }
      )
      
      console.log('[WB_DEBUG] WB toggle success', updatedStatus)
      
      setWbStatus(updatedStatus)
      setWbShowForm(enabled && !updatedStatus.is_configured)
      
      // Reload marketplaces list
      const { data: projectMps } = await apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
      setProjectMarketplaces(projectMps)
    } catch (error: any) {
      console.error('[WB_DEBUG] WB toggle error:', {
        url,
        status: error.status,
        detail: error.detail,
        message: error.message,
        fullError: error
      })
      setWbError(error.detail || 'Failed to toggle Wildberries')
      alert(error.detail || 'Failed to toggle Wildberries')
    } finally {
      setWbLoading(false)
    }
  }

  const handleWBSave = async () => {
    if (!wbToken.trim() && !wbStatus?.credentials?.api_token) {
      setWbError('Введите WB Token')
      return
    }

    try {
      setWbLoading(true)
      setWbError(null)
      const updateData: { is_enabled: boolean; api_token?: string } = { is_enabled: true }
      if (wbToken.trim()) updateData.api_token = wbToken.trim()
      
      const { data: updatedStatus } = await apiPut<WBMarketplaceStatus>(
        `/api/v1/projects/${projectId}/marketplaces/wildberries`,
        updateData
      )
      
      setWbStatus(updatedStatus)
      setWbToken('')
      setWbShowForm(false)
      
      // Reload marketplaces list
      const { data: projectMps } = await apiGet<ProjectMarketplace[]>(`/api/v1/projects/${projectId}/marketplaces`)
      setProjectMarketplaces(projectMps)
    } catch (error: any) {
      setWbError(error.detail || 'Failed to save Wildberries settings')
      alert(error.detail || 'Failed to save Wildberries settings')
    } finally {
      setWbLoading(false)
    }
  }

  const handleConfigure = (marketplaceCode: string) => {
    router.push(`/app/project/${projectId}/marketplaces/${marketplaceCode}/settings`)
  }

  // Create a map of project marketplaces by marketplace_id
  const projectMpMap = new Map(projectMarketplaces.map(pm => [pm.marketplace_id, pm]))

  return (
    <div className="container">
      <h1>Marketplaces</h1>

      <div className="card">
        <h2>Available Marketplaces</h2>
        {loading ? (
          <p>Loading...</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {allMarketplaces.map((mp) => {
                const projectMp = projectMpMap.get(mp.id)
                const isEnabled = projectMp?.is_enabled || false
                
                // Get system marketplace status (global settings)
                const systemStatus = systemMarketplaceStatuses[mp.code]
                const isGloballyEnabled = systemStatus?.is_globally_enabled ?? true // Default: enabled
                const isGloballyVisible = systemStatus?.is_visible ?? true // Default: visible
                
                // Special handling for Wildberries
                const isWB = mp.code === 'wildberries'
                // Use wbStatus if available, fallback to projectMp for backward compatibility
                const wbEnabled = isWB ? (wbStatus?.is_enabled ?? projectMp?.is_enabled ?? false) : false
                const wbConnected = wbStatus?.is_configured ?? false
                
                // If globally hidden and not connected in project, skip rendering
                // But if already connected, show it with disabled state
                if (!isGloballyVisible && !projectMp) {
                  return null // Skip hidden marketplaces that are not connected
                }
                
                // Debug logging for WB
                if (isWB) {
                  console.log('[WB_DEBUG] Render WB row', { 
                    mpCode: mp.code, 
                    mpId: mp.id,
                    wbStatus: wbStatus,
                    projectMp: projectMp,
                    wbEnabled, 
                    wbConnected,
                    shouldShowConfigure: wbEnabled || wbConnected
                  })
                }
                
                let statusText = 'Disabled'
                let statusColor = '#6c757d'
                let statusHint = ''
                
                // Check global status
                if (!isGloballyEnabled) {
                  statusText = 'Disabled (System)'
                  statusColor = '#dc3545'
                  statusHint = 'Отключено администратором системы'
                } else if (isWB && wbConnected) {
                  statusText = 'Connected ✅'
                  statusColor = '#28a745'
                } else if (isWB && wbEnabled) {
                  statusText = 'Enabled'
                  statusColor = '#ffc107'
                } else if (isEnabled) {
                  statusText = 'Enabled'
                  statusColor = '#28a745'
                }
                
                // If globally hidden but connected, add hint
                if (!isGloballyVisible && projectMp) {
                  statusHint = 'Скрыт администратором системы (но подключен в проекте)'
                }
                
                return (
                  <React.Fragment key={mp.id}>
                    <tr>
                      <td><strong>{mp.name}</strong></td>
                      <td>{mp.description || '-'}</td>
                      <td>
                        <span style={{ 
                          color: statusColor,
                          fontWeight: 'bold'
                        }}>
                          {statusText}
                        </span>
                        {statusHint && (
                          <div style={{ 
                            fontSize: '12px', 
                            color: '#666', 
                            marginTop: '4px',
                            fontStyle: 'italic'
                          }}>
                            {statusHint}
                          </div>
                        )}
                      </td>
                      <td>
                        <button
                          onClick={() => handleToggle(mp.id, mp.code, isWB ? wbEnabled : isEnabled)}
                          disabled={wbLoading || !isGloballyEnabled}
                          style={{ 
                            backgroundColor: (isWB ? wbEnabled : isEnabled) ? '#dc3545' : '#28a745',
                            marginRight: '10px',
                            opacity: !isGloballyEnabled ? 0.5 : 1,
                            cursor: !isGloballyEnabled ? 'not-allowed' : 'pointer'
                          }}
                          title={!isGloballyEnabled ? 'Отключено администратором системы' : ''}
                        >
                          {wbLoading ? 'Loading...' : ((isWB ? wbEnabled : isEnabled) ? 'Disable' : 'Enable')}
                        </button>
                        {isWB && wbEnabled && (
                          <>
                            <button
                              onClick={() => {
                                console.log('[WB_DEBUG] Configure button clicked', { wbShowForm, wbEnabled, wbConnected })
                                setWbShowForm(!wbShowForm)
                              }}
                              style={{ backgroundColor: '#0070f3', marginRight: '10px' }}
                            >
                              {wbShowForm ? 'Hide' : 'Configure'}
                            </button>
                            <button
                              onClick={() => handleConfigure('wildberries')}
                              style={{ backgroundColor: '#6c757d', marginRight: '10px' }}
                              title="Настройки маркетплейса: витринные цены, пагинация и др."
                            >
                              Настройки
                            </button>
                          </>
                        )}
                        {!isWB && isEnabled && (
                          <button
                            onClick={() => handleConfigure(mp.code)}
                            style={{ backgroundColor: '#0070f3' }}
                          >
                            Configure
                          </button>
                        )}
                      </td>
                    </tr>
                    {isWB && wbShowForm && (
                      <tr>
                        <td colSpan={4} style={{ padding: '20px', backgroundColor: '#f8f9fa' }}>
                          <div style={{ maxWidth: '600px' }}>
                            <h3 style={{ marginTop: 0, marginBottom: '15px' }}>Configure Wildberries</h3>
                            
                            {wbError && (
                              <div style={{ 
                                padding: '10px', 
                                marginBottom: '15px', 
                                backgroundColor: '#f8d7da', 
                                color: '#721c24', 
                                borderRadius: '4px'
                              }}>
                                <strong>Error:</strong> {wbError}
                              </div>
                            )}
                            
                            <div style={{ marginBottom: '15px' }}>
                              <label htmlFor="wb-token" style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>
                                WB Token
                              </label>
                              <input
                                id="wb-token"
                                type="password"
                                value={wbToken}
                                onChange={(e) => setWbToken(e.target.value)}
                                placeholder={wbStatus?.credentials?.api_token ? 'Оставьте пустым, чтобы не менять' : 'Введите API токен Wildberries'}
                                disabled={wbLoading}
                                style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                              />
                            </div>
                            
                            <p style={{ fontSize: 13, color: '#666', marginBottom: 15 }}>
                              Бренды настраиваются в <strong>Настройки</strong> маркетплейса (кнопка «Настройки»).
                            </p>
                            <div style={{ display: 'flex', gap: '10px' }}>
                              <button
                                onClick={handleWBSave}
                                disabled={wbLoading || (!wbToken.trim() && !wbStatus?.credentials?.api_token)}
                                style={{ backgroundColor: '#007bff', color: 'white', padding: '10px 20px' }}
                              >
                                {wbLoading ? 'Saving...' : 'Save'}
                              </button>
                              <button
                                onClick={() => setWbShowForm(false)}
                                disabled={wbLoading}
                                style={{ backgroundColor: '#6c757d', color: 'white', padding: '10px 20px' }}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {isAdmin && (
        <div className="card" style={{ marginTop: '24px', borderTop: '2px dashed #ccc' }}>
          <h2>🔒 Admin (глобально, для всех проектов)</h2>
          <h3>Wildberries — Tariffs</h3>
          {wbTariffsLoading ? (
            <p>Загрузка статуса тарифов...</p>
          ) : wbTariffsError ? (
            <p style={{ color: 'red' }}>{wbTariffsError}</p>
          ) : (
            <p>
              <strong>Последнее обновление (любой тип):</strong>{' '}
              {wbTariffsStatus?.latest_fetched_at || 'нет данных'}
            </p>
          )}

          <div className="form-group" style={{ maxWidth: '220px', marginTop: '8px' }}>
            <label>Days ahead (0–30)</label>
            <input
              type="number"
              min={0}
              max={30}
              value={wbTariffsDaysAhead}
              onChange={(e) => setWbTariffsDaysAhead(Number(e.target.value))}
            />
          </div>

          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              onClick={handleWBTariffsIngest}
              disabled={wbTariffsIngesting || wbTariffsCooldown}
            >
              {wbTariffsIngesting
                ? 'Запуск...'
                : wbTariffsCooldown
                ? 'Подождите...'
                : 'Обновить тарифы WB'}
            </button>
            <button onClick={loadWBTariffsStatus} disabled={wbTariffsLoading}>
              {wbTariffsLoading ? 'Обновляем статус...' : 'Обновить статус'}
            </button>
          </div>

          {wbTariffsStatus && (
            <p style={{ marginTop: '8px', color: '#555' }}>
              Admin (глобально): эти тарифы используются всеми проектами с подключённым Wildberries.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

