'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { apiGet, apiPost, apiPut } from '../../../../../lib/apiClient'

interface ProjectMember {
  id: number
  user_id: number
  role: string
  username?: string | null
  email?: string | null
}

interface ProjectDetail {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string
  members: ProjectMember[]
}

interface WBMarketplaceStatus {
  is_enabled: boolean
  has_token: boolean
  brand_id: number | null
  connected: boolean
  updated_at: string
}

export default function ProjectSettingsPage({ params }: { params: { projectId: string } }) {
  const projectId = params.projectId
  const [loading, setLoading] = useState(true)
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  
  // WB Marketplace state
  const [wbStatus, setWbStatus] = useState<WBMarketplaceStatus | null>(null)
  const [wbEnabled, setWbEnabled] = useState(false)
  const [wbToken, setWbToken] = useState('')
  const [wbBrandId, setWbBrandId] = useState<string>('')
  const [wbLoading, setWbLoading] = useState(false)
  const [wbError, setWbError] = useState<string | null>(null)
  const [wbSuccess, setWbSuccess] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const [projectData, wbStatusData] = await Promise.all([
          apiGet<ProjectDetail>(`/v1/projects/${projectId}`),
          apiGet<WBMarketplaceStatus>(`/v1/projects/${projectId}/marketplaces/wildberries`).catch(() => null)
        ])
        setProject(projectData.data)
        
        // Load WB status
        if (wbStatusData) {
          setWbStatus(wbStatusData.data)
          setWbEnabled(wbStatusData.data.is_enabled)
          setWbBrandId(wbStatusData.data.brand_id ? String(wbStatusData.data.brand_id) : '')
        } else {
          // Default state if no WB connection exists
          setWbStatus({
            is_enabled: false,
            has_token: false,
            brand_id: null,
            connected: false,
            updated_at: new Date().toISOString()
          })
          setWbEnabled(false)
          setWbBrandId('')
        }
      } catch (e: any) {
        setError(e?.detail || 'Failed to load project')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectId])

  const loadWBStatus = async () => {
    try {
      const { data: wbStatusData } = await apiGet<WBMarketplaceStatus>(`/v1/projects/${projectId}/marketplaces/wildberries`)
      setWbStatus(wbStatusData)
      setWbEnabled(wbStatusData.is_enabled)
      setWbBrandId(wbStatusData.brand_id ? String(wbStatusData.brand_id) : '')
      setWbToken('') // Clear token after save
    } catch (e: any) {
      // Ignore 404 - means no WB connection exists yet
      if (e?.status !== 404) {
        console.error('Failed to load WB status:', e)
      }
    }
  }

  const handleSaveWB = async () => {
    // Validate if enabled
    if (wbEnabled) {
      if (!wbToken.trim() && !wbStatus?.has_token) {
        setWbError('Please enter WB API token')
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
    }

    try {
      setWbLoading(true)
      setWbError(null)
      setWbSuccess(null)
      
      const updateData: any = {
        is_enabled: wbEnabled
      }
      
      // Only include token if provided (to update it)
      if (wbToken.trim()) {
        updateData.api_token = wbToken.trim()
      }
      
      // Only include brand_id if provided or enabled
      if (wbBrandId.trim()) {
        updateData.brand_id = parseInt(wbBrandId)
      }
      
      const { data: updatedStatus } = await apiPut<WBMarketplaceStatus>(
        `/v1/projects/${projectId}/marketplaces/wildberries`,
        updateData
      )
      
      setWbSuccess(wbEnabled ? 'Wildberries settings saved successfully' : 'Wildberries disabled')
      await loadWBStatus()
    } catch (e: any) {
      setWbError(e?.detail || e?.message || 'Failed to save Wildberries settings')
    } finally {
      setWbLoading(false)
    }
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Project Settings</h1>
        <Link href="/app/projects">← Back to projects</Link>
      </div>

      {loading ? (
        <p>Loading...</p>
      ) : error ? (
        <div className="card">
          <p style={{ color: 'crimson' }}>{error}</p>
        </div>
      ) : !project ? (
        <div className="card">
          <p>Project not found</p>
        </div>
      ) : (
        <>
          <div className="card" style={{ padding: '20px' }}>
            <h2 style={{ marginTop: 0 }}>{project.name}</h2>
            {project.description && <p style={{ color: '#666' }}>{project.description}</p>}
            <div style={{ marginTop: '12px', color: '#999', fontSize: '0.9rem' }}>
              <div>Updated: {new Date(project.updated_at).toLocaleString()}</div>
              <div>Members: {project.members?.length ?? 0}</div>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <h2 style={{ marginTop: 0 }}>Quick actions</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              <Link href={`/app/project/${projectId}/dashboard`}>
                <button>Open dashboard</button>
              </Link>
              <Link href={`/app/project/${projectId}/marketplaces`}>
                <button>Marketplaces</button>
              </Link>
              <Link href={`/app/project/${projectId}/members`}>
                <button>Members</button>
              </Link>
            </div>
          </div>

          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
              <h2 style={{ marginTop: 0, marginBottom: 0 }}>Wildberries</h2>
              {wbStatus?.connected && (
                <span style={{
                  padding: '4px 8px',
                  backgroundColor: '#28a745',
                  color: 'white',
                  borderRadius: '4px',
                  fontSize: '0.85rem',
                  fontWeight: 'bold'
                }}>
                  Connected ✅
                </span>
              )}
            </div>
            <p style={{ color: '#666', marginBottom: '15px' }}>
              Configure Wildberries marketplace connection for your project.
            </p>

            {wbError && (
              <div style={{ 
                padding: '12px', 
                marginBottom: '15px', 
                backgroundColor: '#f8d7da', 
                color: '#721c24', 
                borderRadius: '4px',
                border: '1px solid #f5c6cb'
              }}>
                <strong>Error:</strong> {wbError}
              </div>
            )}

            {wbSuccess && (
              <div style={{ 
                padding: '12px', 
                marginBottom: '15px', 
                backgroundColor: '#d4edda', 
                color: '#155724', 
                borderRadius: '4px',
                border: '1px solid #c3e6cb'
              }}>
                <strong>Success:</strong> {wbSuccess}
              </div>
            )}

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={wbEnabled}
                  onChange={(e) => setWbEnabled(e.target.checked)}
                  disabled={wbLoading}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
                <span style={{ fontWeight: '500' }}>Enabled</span>
              </label>
              <small style={{ color: '#666', display: 'block', marginTop: '5px', marginLeft: '28px' }}>
                Enable Wildberries marketplace for this project
              </small>
            </div>

            {wbEnabled && (
              <div>
                <div className="form-group" style={{ marginBottom: '15px' }}>
                  <label htmlFor="wb-token">WB Token</label>
                  <input
                    id="wb-token"
                    type="password"
                    value={wbToken}
                    onChange={(e) => setWbToken(e.target.value)}
                    placeholder={wbStatus?.has_token ? 'Leave empty to keep current token' : 'Enter Wildberries API token'}
                    disabled={wbLoading}
                    style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                  />
                  <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
                    {wbStatus?.has_token 
                      ? 'Token is already set. Enter a new token to update it.' 
                      : 'Get your token from '
                    }
                    {!wbStatus?.has_token && (
                      <a href="https://seller.wildberries.ru/supplies-manager/settings/api-access" target="_blank" rel="noopener noreferrer">
                        WB Seller Account → API Access
                      </a>
                    )}
                  </small>
                </div>

                <div className="form-group" style={{ marginBottom: '20px' }}>
                  <label htmlFor="wb-brand-id">WB Brand ID</label>
                  <input
                    id="wb-brand-id"
                    type="number"
                    value={wbBrandId}
                    onChange={(e) => setWbBrandId(e.target.value)}
                    placeholder="Enter Brand ID (e.g., 41189)"
                    disabled={wbLoading}
                    style={{ width: '100%', padding: '8px', fontSize: '14px' }}
                  />
                  <small style={{ color: '#666', display: 'block', marginTop: '5px' }}>
                    Brand ID must be a number greater than 0
                  </small>
                </div>
              </div>
            )}

            <button 
              onClick={handleSaveWB}
              disabled={wbLoading || (wbEnabled && !wbToken.trim() && !wbStatus?.has_token)}
              style={{ backgroundColor: '#007bff', color: 'white', padding: '10px 20px' }}
            >
              {wbLoading ? 'Saving...' : 'Save'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}



