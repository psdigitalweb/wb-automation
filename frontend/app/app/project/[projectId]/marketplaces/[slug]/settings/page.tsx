'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPut, apiPost, apiDelete } from '../../../../../../../lib/apiClient'

const formFieldStyle = {
  display: 'flex' as const,
  flexDirection: 'column' as const,
  gap: 6,
}
const formLabelStyle = { fontSize: 13, fontWeight: 500 }
const formInputStyle = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 5,
  border: '1px solid #d1d5db',
  fontSize: 14,
  height: 38,
}

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
  type BrandRow = { brand_id: number; enabled: boolean; title?: string }
  const [brands, setBrands] = useState<BrandRow[]>([])
  const [brandInput, setBrandInput] = useState('')
  const [brandInputEnabled, setBrandInputEnabled] = useState(true)

  useEffect(() => {
    loadData()
  }, [projectId, slug])

  const loadData = async () => {
    try {
      setLoading(true)
      const { data: marketplaces } = await apiGet<Marketplace[]>('/api/v1/marketplaces')
      const mp = marketplaces.find(m => m.code === slug)
      if (!mp) {
        alert('Marketplace not found')
        router.back()
        return
      }
      setMarketplace(mp)

      let currentPm: ProjectMarketplace | null = null
      try {
        const { data: pm } = await apiGet<ProjectMarketplace>(`/api/v1/projects/${projectId}/marketplaces/${mp.id}`)
        currentPm = pm
        setProjectMp(pm)
        if (pm.settings_json) {
          setSettings(pm.settings_json)
          if (slug !== 'wildberries') {
            setJsonSettings(JSON.stringify(pm.settings_json, null, 2))
          }
        }
      } catch {
        const { data: newPm } = await apiPost<ProjectMarketplace>(`/api/v1/projects/${projectId}/marketplaces`, {
          marketplace_id: mp.id,
          is_enabled: false,
          settings_json: {}
        })
        currentPm = newPm
        setProjectMp(newPm)
      }

      if (slug === 'wildberries') {
        try {
          const { data: status } = await apiGet<WBStatusV2>(`/api/v1/projects/${projectId}/marketplaces/wb`)
          setWbStatus(status)
        } catch (e) {
          console.warn('[WB_DEBUG] Failed to load WB status v2', e)
          setWbStatus(null)
        }
        const sjson = (currentPm?.settings_json || {}) as Record<string, any>
        const fp = sjson?.frontend_prices
        const brandsList = Array.isArray(fp?.brands) ? fp.brands : []
        if (brandsList.length > 0) {
          setBrands(brandsList.map((b: any) => ({
            brand_id: Number(b.brand_id),
            enabled: b.enabled !== false,
            title: b.title,
          })))
        } else {
          const legacyId = sjson?.brand_id
          if (legacyId != null) {
            const n = Number(legacyId)
            if (Number.isFinite(n)) setBrands([{ brand_id: n, enabled: true }])
            else setBrands([])
          } else setBrands([])
        }
      } else {
        setWbStatus(null)
        setBrands([])
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
        settingsToSave = { ...settings }
        settingsToSave.frontend_prices = { ...(settings.frontend_prices || {}), brands }
        // Validate frontend_prices template: must contain {brand_id} and {page}
        const tpl = (settingsToSave.frontend_prices?.base_url_template ?? '') as string
        if (tpl && tpl.trim()) {
          if (!tpl.includes('{brand_id}')) {
            alert('Base URL template must contain placeholder {brand_id}')
            setSaving(false)
            return
          }
          if (!tpl.includes('{page}') && !/[?&]page=/.test(tpl)) {
            alert('Base URL template must contain placeholder {page} or query parameter page=')
            setSaving(false)
            return
          }
        }
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
        await apiPut(`/api/v1/projects/${projectId}/marketplaces/wildberries`, {
          is_enabled: true,
          api_token: wbToken.trim(),
          ...(Number.isFinite(brandId) && brandId! > 0 ? { brand_id: brandId } : {}),
        })
        setWbToken('')
      }

      await apiPut(`/api/v1/projects/${projectId}/marketplaces/${marketplace!.id}`, {
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

  const updateFrontendPricesSettings = (key: string, value: any) => {
    setSettings((prev) => ({
      ...prev,
      frontend_prices: {
        ...(prev.frontend_prices || {}),
        [key]: value,
      },
    }))
  }

  if (loading || !marketplace || !projectMp) {
    return (
      <div className="container">
        <p style={{ color: '#666' }}>Загрузка…</p>
      </div>
    )
  }

  const formGridStyle = {
    display: 'grid' as const,
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 16,
    alignItems: 'stretch' as const,
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Настройки {marketplace.name}</h1>
        <Link href={`/app/project/${projectId}/marketplaces`}>← К маркетплейсам</Link>
      </div>

      <div className="card" style={{ padding: 20, marginTop: 20 }}>
        <h2 style={{ marginBottom: 16 }}>Конфигурация</h2>
        {slug === 'wildberries' ? (
          <>
            <div style={{ marginBottom: 16, fontSize: 13, color: '#374151' }}>
              Токен: <strong>{wbStatus?.credentials?.api_token ? 'сохранён' : 'не сохранён'}</strong>
            </div>

            <div style={formGridStyle}>
              <div style={{ ...formFieldStyle, gridColumn: '1 / -1' }}>
                <label style={formLabelStyle}>API Token</label>
                <input
                  type="password"
                  value={wbToken}
                  onChange={(e) => setWbToken(e.target.value)}
                  placeholder={wbStatus?.credentials?.api_token ? 'Оставьте пустым, чтобы не менять' : 'Введите API токен'}
                  style={formInputStyle}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  {wbStatus?.credentials?.api_token
                    ? 'Токен сохранён. Введите новый, чтобы сменить.'
                    : 'Введите токен для подключения.'}
                </div>
              </div>
            </div>

            <hr style={{ margin: '24px 0 16px', border: 'none', borderTop: '1px solid #e5e7eb' }} />

            <h3 style={{ marginBottom: 12, fontSize: '1.1rem' }}>Витринные цены (frontend catalog)</h3>
            <div style={formGridStyle}>
              <div style={{ ...formFieldStyle, gridColumn: '1 / -1' }}>
                <label style={formLabelStyle}>Base URL template</label>
                <input
                  type="text"
                  value={(settings.frontend_prices?.base_url_template ?? '') as string}
                  onChange={(e) => updateFrontendPricesSettings('base_url_template', e.target.value)}
                  placeholder="https://catalog.wb.ru/brands/v4/catalog?brand={brand_id}&dest=-1257786&page={page}&limit={limit}&sort=popular..."
                  style={{ ...formInputStyle, height: 'auto', minHeight: 38 }}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  Обязательно: <code>{'{brand_id}'}</code> и <code>{'{page}'}</code>. Можно <code>{'{limit}'}</code> (подставится из поля Limit).
                </div>
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Limit (по умолчанию 50)</label>
                <input
                  type="number"
                  value={(settings.frontend_prices?.limit ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('limit', Number.isFinite(n as any) ? n : undefined)
                  }}
                  placeholder="50"
                  style={formInputStyle}
                />
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Max pages (0 = до пустых)</label>
                <input
                  type="number"
                  value={(settings.frontend_prices?.max_pages ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('max_pages', Number.isFinite(n as any) ? n : undefined)
                  }}
                  placeholder="200"
                  style={formInputStyle}
                />
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Sleep base (ms)</label>
                <input
                  type="number"
                  value={(settings.frontend_prices?.sleep_base_ms ?? settings.frontend_prices?.sleep_ms ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('sleep_base_ms', Number.isFinite(n as any) ? n : undefined)
                  }}
                  placeholder="800"
                  style={formInputStyle}
                />
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Sleep jitter (ms)</label>
                <input
                  type="number"
                  value={(settings.frontend_prices?.sleep_jitter_ms ?? settings.frontend_prices?.sleep_jitter_ms ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('sleep_jitter_ms', Number.isFinite(n as any) ? n : undefined)
                  }}
                  placeholder="400"
                  style={formInputStyle}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  Пауза: base ± jitter (напр. 800 ± 400 ≈ 0.4–1.2 сек).
                </div>
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Минимум попыток запроса (при прокси)</label>
                <input
                  type="number"
                  min={1}
                  value={(settings.frontend_prices?.http_min_retries ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('http_min_retries', Number.isFinite(n as any) && (n as number) >= 1 ? n : undefined)
                  }}
                  placeholder="10"
                  style={formInputStyle}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  При ротации IP каждый запрос повторяется до N раз перед отменой.
                </div>
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Джиттер таймаута (сек)</label>
                <input
                  type="number"
                  min={0}
                  value={(settings.frontend_prices?.http_timeout_jitter_sec ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('http_timeout_jitter_sec', Number.isFinite(n as any) && (n as number) >= 0 ? n : undefined)
                  }}
                  placeholder="10"
                  style={formInputStyle}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  Случайная добавка 0…N сек к таймауту каждой попытки.
                </div>
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Порог покрытия (0–1, 0=отключить)</label>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.1}
                  value={(settings.frontend_prices?.min_coverage_ratio ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseFloat(raw)
                    updateFrontendPricesSettings('min_coverage_ratio', Number.isFinite(n as any) && (n as number) >= 0 ? n : undefined)
                  }}
                  placeholder="0.8"
                  style={formInputStyle}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  0 = принять любой результат. 0.8 = требовать ≥80% товаров.
                </div>
              </div>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>Max runtime (сек)</label>
                <input
                  type="number"
                  min={60}
                  value={(settings.frontend_prices?.max_runtime_seconds ?? '') as any}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? undefined : parseInt(raw)
                    updateFrontendPricesSettings('max_runtime_seconds', Number.isFinite(n as any) && (n as number) >= 60 ? n : undefined)
                  }}
                  placeholder="1200"
                  style={formInputStyle}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  Макс. время одного запуска (по умолчанию 1200 с). Увеличьте, если обрывается по таймауту.
                </div>
              </div>
            </div>

            <h4 style={{ marginTop: 24, marginBottom: 8, fontSize: '1rem' }}>Бренды</h4>
            <p style={{ color: '#6b7280', fontSize: 13, marginBottom: 12 }}>
              Задача «Загрузка цен с витрины» (domain=frontend_prices) обрабатывает все включённые бренды за один запуск. Добавьте brand_id и включите/выключите при необходимости.
            </p>
            <div style={formGridStyle}>
              <div style={formFieldStyle}>
                <label style={formLabelStyle}>brand_id</label>
                <input
                  type="number"
                  value={brandInput}
                  onChange={(e) => setBrandInput(e.target.value)}
                  placeholder="напр. 310688509"
                  style={formInputStyle}
                />
              </div>
              <div style={{ ...formFieldStyle, display: 'flex', alignItems: 'flex-end' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={brandInputEnabled}
                    onChange={(e) => setBrandInputEnabled(e.target.checked)}
                  />
                  Включён
                </label>
              </div>
              <div style={{ ...formFieldStyle, display: 'flex', alignItems: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => {
                    const n = parseInt(brandInput, 10)
                    if (!Number.isFinite(n) || n < 1) {
                      alert('Введите положительный brand_id')
                      return
                    }
                    if (brands.some(b => b.brand_id === n)) {
                      alert('Этот brand_id уже в списке')
                      return
                    }
                    setBrands(prev => [...prev, { brand_id: n, enabled: brandInputEnabled }])
                    setBrandInput('')
                  }}
                >
                  Добавить бренд
                </button>
              </div>
            </div>
            {brands.length > 0 && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: 12,
                  marginTop: 12,
                }}
              >
                {brands.map((b, idx) => (
                  <div
                    key={b.brand_id + '-' + idx}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                      padding: 12,
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      backgroundColor: '#fafafa',
                    }}
                  >
                    <span style={{ fontSize: 14, fontWeight: 500 }}>{b.brand_id}</span>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={b.enabled}
                        onChange={(e) => setBrands(prev => prev.map(x => x.brand_id === b.brand_id ? { ...x, enabled: e.target.checked } : x))}
                      />
                      Включён
                    </label>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setBrands(prev => prev.filter(x => x.brand_id !== b.brand_id))}
                    >
                      Удалить
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
              <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение…' : 'Сохранить'}
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={formFieldStyle}>
              <label style={formLabelStyle}>Settings (JSON)</label>
              <textarea
                value={jsonSettings}
                onChange={(e) => setJsonSettings(e.target.value)}
                rows={15}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 5,
                  border: '1px solid #d1d5db',
                  fontSize: 13,
                  fontFamily: 'monospace',
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
              <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? 'Сохранение…' : 'Сохранить'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

