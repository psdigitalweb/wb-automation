'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPatch, apiPost, apiPut, ApiError } from '../../../../../lib/apiClient'
import { User } from '../../../../../lib/auth'
import '../../../../globals.css'

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
  settings: { brand_id: number | null }
  updated_at: string
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
  const [wbBrandId, setWbBrandId] = useState<string>('')
  const [wbLoading, setWbLoading] = useState(false)
  const [wbError, setWbError] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [projectId])

  const loadData = async () => {
    try {
      setLoading(true)
      const [marketplacesRes, projectMpsRes] = await Promise.all([
        apiGet<Marketplace[]>('/v1/marketplaces?active_only=true'),
        apiGet<ProjectMarketplace[]>(`/v1/projects/${projectId}/marketplaces`)
      ])
      setAllMarketplaces(marketplacesRes.data)
      setProjectMarketplaces(projectMpsRes.data)
      
      // Load WB status separately
      try {
        const wbStatusRes = await apiGet<WBMarketplaceStatus>(`/v1/projects/${projectId}/marketplaces/wb`)
        const wbStatusData = wbStatusRes.data
        setWbStatus(wbStatusData)
        const brandId = wbStatusData.settings?.brand_id
        setWbBrandId(brandId ? String(brandId) : '')
        // Show form if enabled but not configured
        setWbShowForm(wbStatusData.is_enabled && !wbStatusData.is_configured)
      } catch (e: any) {
        // If WB status endpoint fails (e.g. backend not restarted yet), keep wbStatus null.
        // UI will fall back to project marketplace list for enabled/disabled state.
        console.warn('[WB_DEBUG] Failed to load WB status', e)
        setWbStatus(null)
        setWbBrandId('')
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
        const { data } = await apiGet<User>('/v1/auth/me')
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
      const { data } = await apiGet<any>('/v1/admin/marketplaces/wildberries/tariffs/status')
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
        '/v1/admin/marketplaces/wildberries/tariffs/ingest',
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
    const url = `/v1/projects/${projectId}/marketplaces/${marketplaceId}/toggle`
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
    const url = `/v1/projects/${projectId}/marketplaces/wildberries`
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
      const { data: projectMps } = await apiGet<ProjectMarketplace[]>(`/v1/projects/${projectId}/marketplaces`)
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
      setWbError('Please enter WB Token')
      return
    }
    if (!wbBrandId.trim()) {
      setWbError('Please enter Brand ID')
      return
    }
    const brandIdNum = parseInt(wbBrandId)
    if (isNaN(brandIdNum) || brandIdNum <= 0) {
      setWbError('Brand ID must be a number greater than 0')
      return
    }

    try {
      setWbLoading(true)
      setWbError(null)
      
      const updateData: any = {
        is_enabled: true
      }
      
      // Only include brand_id if valid
      if (brandIdNum > 0) {
        updateData.brand_id = brandIdNum
      }
      
      // Only include api_token if provided
      if (wbToken.trim()) {
        updateData.api_token = wbToken.trim()
      }
      
      console.log('[WB_DEBUG] Sending updateData', updateData)
      
      const { data: updatedStatus } = await apiPut<WBMarketplaceStatus>(
        `/v1/projects/${projectId}/marketplaces/wildberries`,
        updateData
      )
      
      setWbStatus(updatedStatus)
      setWbToken('')
      setWbShowForm(false)
      
      // Reload marketplaces list
      const { data: projectMps } = await apiGet<ProjectMarketplace[]>(`/v1/projects/${projectId}/marketplaces`)
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
                
                // Special handling for Wildberries
                const isWB = mp.code === 'wildberries'
                // Use wbStatus if available, fallback to projectMp for backward compatibility
                const wbEnabled = isWB ? (wbStatus?.is_enabled ?? projectMp?.is_enabled ?? false) : false
                const wbConnected = wbStatus?.is_configured ?? false
                
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
                if (isWB && wbConnected) {
                  statusText = 'Connected ✅'
                  statusColor = '#28a745'
                } else if (isWB && wbEnabled) {
                  statusText = 'Enabled'
                  statusColor = '#ffc107'
                } else if (isEnabled) {
                  statusText = 'Enabled'
                  statusColor = '#28a745'
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
                      </td>
                      <td>
                        <button
                          onClick={() => handleToggle(mp.id, mp.code, isWB ? wbEnabled : isEnabled)}
                          disabled={wbLoading}
                          style={{ 
                            backgroundColor: (isWB ? wbEnabled : isEnabled) ? '#dc3545' : '#28a745',
                            marginRight: '10px'
                          }}
                        >
                          {wbLoading ? 'Loading...' : ((isWB ? wbEnabled : isEnabled) ? 'Disable' : 'Enable')}
                        </button>
                        {isWB && wbEnabled && (
                          <button
                            onClick={() => {
                              console.log('[WB_DEBUG] Configure button clicked', { wbShowForm, wbEnabled, wbConnected })
                              setWbShowForm(!wbShowForm)
                            }}
                            style={{ backgroundColor: '#0070f3', marginRight: '10px' }}
                          >
                            {wbShowForm ? 'Hide' : 'Configure'}
                          </button>
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
                                placeholder={wbStatus?.has_token ? 'Leave empty to keep current token' : 'Enter Wildberries API token'}
                                disabled={wbLoading}
                                style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                              />
                            </div>
                            
                            <div style={{ marginBottom: '20px' }}>
                              <label htmlFor="wb-brand-id" style={{ display: 'block', marginBottom: '5px', fontWeight: '500' }}>
                                WB Brand ID
                              </label>
                              <input
                                id="wb-brand-id"
                                type="number"
                                value={wbBrandId}
                                onChange={(e) => setWbBrandId(e.target.value)}
                                placeholder="Enter Brand ID (e.g., 41189)"
                                disabled={wbLoading}
                                style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                              />
                            </div>
                            
                            <div style={{ display: 'flex', gap: '10px' }}>
                              <button
                                onClick={handleWBSave}
                                disabled={wbLoading || (!wbToken.trim() && !wbStatus?.has_token)}
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

