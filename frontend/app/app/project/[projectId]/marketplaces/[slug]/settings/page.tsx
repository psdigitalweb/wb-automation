'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { apiGet, apiPut, apiPost } from '../../../../../../lib/apiClient'
import '../../../../../globals.css'

interface Marketplace {
  id: number
  code: string
  name: string
}

interface ProjectMarketplace {
  id: number
  marketplace_id: number
  is_enabled: boolean
  settings_json: Record<string, any> | null
  marketplace_code: string
  marketplace_name: string
}

interface WBStatusV2 {
  is_enabled: boolean
  is_configured: boolean
  credentials: { api_token: boolean }
  settings: { brand_id: number | null }
  updated_at: string
}

export default function MarketplaceSettingsPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const slug = params.slug as string
  const [marketplace, setMarketplace] = useState<Marketplace | null>(null)
  const [projectMp, setProjectMp] = useState<ProjectMarketplace | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState<Record<string, any>>({})
  const [jsonSettings, setJsonSettings] = useState('{}')
  const [wbStatus, setWbStatus] = useState<WBStatusV2 | null>(null)
  const [wbToken, setWbToken] = useState('')

  useEffect(() => {
    loadData()
  }, [projectId, slug])

  const loadData = async () => {
    try {
      setLoading(true)
      const { data: marketplaces } = await apiGet<Marketplace[]>('/v1/marketplaces')
      const mp = marketplaces.find(m => m.code === slug)
      if (!mp) {
        alert('Marketplace not found')
        router.back()
        return
      }
      setMarketplace(mp)

      try {
        const { data: pm } = await apiGet<ProjectMarketplace>(`/v1/projects/${projectId}/marketplaces/${mp.id}`)
        setProjectMp(pm)
        if (pm.settings_json) {
          setSettings(pm.settings_json)
          if (slug === 'wildberries') {
            // For WB, settings are already in state
          } else {
            // For others, use JSON editor
            setJsonSettings(JSON.stringify(pm.settings_json, null, 2))
          }
        }
      } catch {
        // Project-marketplace connection doesn't exist yet, create it
        const { data: newPm } = await apiPost<ProjectMarketplace>(`/v1/projects/${projectId}/marketplaces`, {
          marketplace_id: mp.id,
          is_enabled: false,
          settings_json: {}
        })
        setProjectMp(newPm)
      }

      if (slug === 'wildberries') {
        try {
          const { data: status } = await apiGet<WBStatusV2>(`/v1/projects/${projectId}/marketplaces/wb`)
          setWbStatus(status)
        } catch (e) {
          console.warn('[WB_DEBUG] Failed to load WB status v2', e)
          setWbStatus(null)
        }
      } else {
        setWbStatus(null)
      }
      setLoading(false)
    } catch (error) {
      console.error('Failed to load data:', error)
      setLoading(false)
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      let settingsToSave: Record<string, any> = {}

      if (slug === 'wildberries') {
        // For WB, collect form fields
        settingsToSave = { ...settings }
        // Never store token in settings_json (token is stored in api_token_encrypted on backend)
        delete settingsToSave.api_token
        delete settingsToSave.token

        // Don't overwrite masked secrets - remove keys with masked values
        Object.keys(settingsToSave).forEach(key => {
          const value = settingsToSave[key]
          if (value === '***' || value === '******' || (typeof value === 'string' && (value.includes('***') || value.trim() === ''))) {
            delete settingsToSave[key]
          }
        })
      } else {
        // For others, parse JSON
        try {
          settingsToSave = JSON.parse(jsonSettings)
        } catch {
          alert('Invalid JSON')
          setSaving(false)
          return
        }
      }

      // If user typed a new WB token, update it via dedicated WB endpoint (doesn't expose token back)
      if (slug === 'wildberries' && wbToken.trim()) {
        const brandIdRaw = settingsToSave.brand_id
        const brandId = brandIdRaw !== undefined && brandIdRaw !== null ? Number(brandIdRaw) : undefined
        await apiPut(`/v1/projects/${projectId}/marketplaces/wildberries`, {
          is_enabled: true,
          api_token: wbToken.trim(),
          ...(Number.isFinite(brandId) && brandId! > 0 ? { brand_id: brandId } : {}),
        })
        setWbToken('')
      }

      await apiPut(`/v1/projects/${projectId}/marketplaces/${marketplace!.id}`, {
        settings_json: settingsToSave
      })
      alert('Settings saved successfully')
      await loadData()
    } catch (error: any) {
      alert(error.detail || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleFieldChange = (key: string, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  if (loading || !marketplace || !projectMp) {
    return <div className="container"><p>Loading...</p></div>
  }

  return (
    <div className="container">
      <h1>{marketplace.name} Settings</h1>
      <button onClick={() => router.back()} style={{ marginBottom: '20px' }}>
        ← Back
      </button>

      <div className="card">
        <h2>Configuration</h2>
        {slug === 'wildberries' ? (
          <div>
            <div style={{ marginBottom: '12px', color: '#444' }}>
              Token status:{' '}
              <strong>
                {wbStatus?.credentials?.api_token ? 'saved ✅' : 'not saved'}
              </strong>
            </div>
            <div className="form-group">
              <label>API Token</label>
              <input
                type="password"
                value={wbToken}
                onChange={(e) => setWbToken(e.target.value)}
                placeholder={wbStatus?.credentials?.api_token ? 'Leave empty to keep current token' : 'Enter API token'}
              />
              <small style={{ color: '#666' }}>
                {wbStatus?.credentials?.api_token
                  ? 'Token is saved (not shown). Enter new value to rotate.'
                  : 'Enter token to connect.'}
              </small>
            </div>
            <div className="form-group">
              <label>Base URL</label>
              <input
                type="text"
                value={settings.base_url || 'https://content-api.wildberries.ru'}
                onChange={(e) => handleFieldChange('base_url', e.target.value)}
                placeholder="https://content-api.wildberries.ru"
              />
            </div>
            <div className="form-group">
              <label>Timeout (seconds)</label>
              <input
                type="number"
                value={settings.timeout || 30}
                onChange={(e) => handleFieldChange('timeout', parseInt(e.target.value))}
              />
            </div>
          </div>
        ) : (
          <div className="form-group">
            <label>Settings (JSON)</label>
            <textarea
              value={jsonSettings}
              onChange={(e) => setJsonSettings(e.target.value)}
              rows={15}
              style={{ fontFamily: 'monospace', fontSize: '12px' }}
            />
          </div>
        )}

        <div style={{ marginTop: '20px' }}>
          <button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  )
}

