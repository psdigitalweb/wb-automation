'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { apiGet, apiPut, apiPost } from '../../../../../../../lib/apiClient'
import styles from './marketplace-settings.module.css'

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
  storefront_configured: boolean
  storefront_brand_ids: number[]
  storefront_seller_url: string | null
  storefront_seller_id: number | null
  updated_at: string
}

interface WBStorefrontResolution {
  verified: boolean
  seller_url: string
  seller_id: number
  seller_name: string | null
  proxy_configured: boolean
  http_status: number | null
  storefront_products_count: number
  cabinet_products_count: number
  matched_products_count: number
  coverage_percent: number
  sample_products: Array<{
    nm_id: number
    title: string | null
    brand: string | null
  }>
  error_code: string | null
  message: string | null
  verification_source: 'live' | 'cached_snapshot' | null
  verified_at: string | null
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
  const [savingCabinet, setSavingCabinet] = useState(false)
  const [savingStorefront, setSavingStorefront] = useState(false)
  const [resolvingStorefront, setResolvingStorefront] = useState(false)
  const [jsonSettings, setJsonSettings] = useState('{}')
  const [wbStatus, setWbStatus] = useState<WBStatusV2 | null>(null)
  const [wbToken, setWbToken] = useState('')
  const [sellerUrl, setSellerUrl] = useState('')
  const [storefrontResolution, setStorefrontResolution] = useState<WBStorefrontResolution | null>(null)

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
          setSellerUrl(status.storefront_seller_url || '')
          setStorefrontResolution(null)
        } catch (e) {
          console.warn('[WB_DEBUG] Failed to load WB status v2', e)
          setWbStatus(null)
        }
      } else {
        setWbStatus(null)
        setSellerUrl('')
        setStorefrontResolution(null)
      }
      setLoading(false)
    } catch (error) {
      console.error('Failed to load data:', error)
      setLoading(false)
    }
  }

  const handleSaveCabinet = async () => {
    const token = wbToken.trim()
    if (!token) return

    try {
      setSavingCabinet(true)
      await apiPut(`/api/v1/projects/${projectId}/marketplaces/wildberries`, {
        is_enabled: true,
        api_token: token,
      })
      setWbToken('')
      alert('Кабинет Wildberries подключён')
      await loadData()
    } catch (error: any) {
      alert(error.detail || 'Не удалось сохранить API token')
    } finally {
      setSavingCabinet(false)
    }
  }

  const handleSaveStorefront = async () => {
    const normalizedSellerUrl = sellerUrl.trim()
    if (!normalizedSellerUrl) {
      alert('Вставьте ссылку на продавца Wildberries')
      return
    }
    if (!storefrontResolution?.verified || storefrontResolution.seller_url !== normalizedSellerUrl) {
      alert('Сначала проверьте ссылку на продавца')
      return
    }
    try {
      setSavingStorefront(true)
      const { data: status } = await apiPut<WBStatusV2>(
        `/api/v1/projects/${projectId}/marketplaces/wildberries/storefront`,
        {
          seller_url: normalizedSellerUrl,
        },
      )
      setWbStatus(status)
      setSellerUrl(status.storefront_seller_url || normalizedSellerUrl)
      let ingestStarted = false
      let ingestWarning = ''
      try {
        await apiPost(`/api/v1/projects/${projectId}/ingest/run`, {
          domain: 'frontend_prices',
        })
        ingestStarted = true
      } catch (ingestError: any) {
        if (ingestError.status === 409) {
          ingestStarted = true
        } else {
          ingestWarning = ingestError.detail || 'Не удалось запустить загрузку витрины'
        }
      }
      alert(
        ingestStarted
          ? 'Витрина подключена. Загрузка товаров запущена.'
          : `Витрина подключена, но загрузка не запущена: ${ingestWarning}`,
      )
      await loadData()
    } catch (error: any) {
      alert(error.detail || 'Не удалось сохранить настройки витрины')
    } finally {
      setSavingStorefront(false)
    }
  }

  const handleResolveStorefront = async () => {
    const normalizedSellerUrl = sellerUrl.trim()
    if (!normalizedSellerUrl) {
      alert('Вставьте ссылку на продавца Wildberries')
      return
    }
    try {
      setResolvingStorefront(true)
      setStorefrontResolution(null)
      const { data: resolution } = await apiPost<WBStorefrontResolution>(
        `/api/v1/projects/${projectId}/marketplaces/wildberries/storefront/resolve`,
        { seller_url: normalizedSellerUrl },
      )
      setStorefrontResolution(resolution)
      setSellerUrl(resolution.seller_url)
    } catch (error: any) {
      alert(error.detail || 'Не удалось проверить ссылку на продавца')
    } finally {
      setResolvingStorefront(false)
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      let settingsToSave: Record<string, any> = {}

      try {
        settingsToSave = JSON.parse(jsonSettings)
      } catch {
        alert('Invalid JSON')
        return
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

  if (loading || !marketplace || !projectMp) {
    return (
      <div className="container ec-settings-page">
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
  const cabinetConnected = Boolean(wbStatus?.is_configured)
  const storefrontConfigured = Boolean(wbStatus?.storefront_seller_id)

  return (
    <div className="container ec-settings-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Настройки {marketplace.name}</h1>
        <Link href={`/app/project/${projectId}/marketplaces`}>← К маркетплейсам</Link>
      </div>

      {slug === 'wildberries' ? (
        <div className={styles.sections}>
          <section className={`card ${styles.sectionCard}`}>
            <div className={styles.sectionHeader}>
              <div>
                <h2>Кабинет Wildberries</h2>
                <p>Основное подключение для каталога, цен, остатков, финансов и других API-данных.</p>
              </div>
              <span className={`${styles.statusBadge} ${cabinetConnected ? styles.success : styles.warning}`}>
                {cabinetConnected ? 'Подключён' : 'Не подключён'}
              </span>
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
                    : 'Для подключения нужен только API token. Brand ID не требуется.'}
                </div>
              </div>
            </div>
            <div className={styles.actions}>
              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveCabinet}
                disabled={savingCabinet || !wbToken.trim()}
              >
                {savingCabinet ? 'Подключение…' : cabinetConnected ? 'Обновить token' : 'Подключить кабинет'}
              </button>
            </div>
          </section>

          <section className={`card ${styles.sectionCard}`}>
            <div className={styles.sectionHeader}>
              <div>
                <h2>Витрина Wildberries</h2>
                <p>Необязательный источник витринных цен и СПП. Настраивается независимо от кабинета.</p>
              </div>
              <span className={`${styles.statusBadge} ${storefrontConfigured ? styles.success : styles.neutral}`}>
                {storefrontConfigured ? 'Настроена' : 'Не настроена'}
              </span>
            </div>

            <div className={styles.storefrontForm}>
              <div style={formFieldStyle}>
                <label style={formLabelStyle} htmlFor="wb-seller-url">Ссылка на продавца</label>
                <input
                  id="wb-seller-url"
                  type="url"
                  value={sellerUrl}
                  onChange={(event) => {
                    setSellerUrl(event.target.value)
                    setStorefrontResolution(null)
                  }}
                  placeholder="https://www.wildberries.ru/seller/4058267"
                  autoComplete="url"
                  style={formInputStyle}
                />
                <div className={styles.fieldHint}>
                  Откройте страницу продавца на Wildberries и скопируйте адрес из браузера. ID продавца определится автоматически.
                </div>
              </div>

              {storefrontConfigured ? (
                <div className={styles.sellerSummary}>
                  <div>
                    <span>Продавец</span>
                    <strong>#{wbStatus?.storefront_seller_id}</strong>
                  </div>
                  <a href={wbStatus?.storefront_seller_url || sellerUrl} target="_blank" rel="noreferrer">
                    Открыть на Wildberries ↗
                  </a>
                </div>
              ) : null}

              {storefrontResolution ? (
                <div
                  className={`${styles.verificationCard} ${
                    storefrontResolution.verified ? styles.verificationSuccess : styles.verificationError
                  }`}
                >
                  <div className={styles.verificationHeader}>
                    <div>
                      <span>{storefrontResolution.verified ? 'Продавец найден' : 'Проверка не пройдена'}</span>
                      <strong>
                        {storefrontResolution.seller_name || `Продавец #${storefrontResolution.seller_id}`}
                      </strong>
                    </div>
                    <span className={`${styles.statusBadge} ${
                      storefrontResolution.verified ? styles.success : styles.danger
                    }`}>
                      {storefrontResolution.verified ? 'Проверено' : 'Ошибка'}
                    </span>
                  </div>

                  <p className={styles.verificationMessage}>{storefrontResolution.message}</p>
                  {storefrontResolution.verification_source === 'cached_snapshot' ? (
                    <div className={styles.verificationMeta}>
                      Источник: последний успешный снимок
                      {storefrontResolution.verified_at
                        ? ` · ${new Date(storefrontResolution.verified_at).toLocaleString('ru-RU')}`
                        : ''}
                    </div>
                  ) : null}

                  {storefrontResolution.verified ? (
                    <>
                      <div className={styles.verificationMetrics}>
                        <div>
                          <span>Найдено при проверке</span>
                          <strong>{storefrontResolution.storefront_products_count}</strong>
                        </div>
                        <div>
                          <span>В каталоге кабинета</span>
                          <strong>{storefrontResolution.cabinet_products_count}</strong>
                        </div>
                        <div>
                          <span>Совпало</span>
                          <strong>{storefrontResolution.matched_products_count}</strong>
                        </div>
                        <div>
                          <span>Покрытие кабинета</span>
                          <strong>{storefrontResolution.coverage_percent}%</strong>
                        </div>
                      </div>
                      {storefrontResolution.sample_products.length ? (
                        <div className={styles.productSamples}>
                          <span>Примеры товаров</span>
                          <div>
                            {storefrontResolution.sample_products.map((product) => (
                              <span key={product.nm_id}>
                                {product.title || `Товар ${product.nm_id}`} · {product.nm_id}
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className={styles.verificationMeta}>
                      Прокси: {storefrontResolution.proxy_configured ? 'подключён' : 'не подключён'}
                      {storefrontResolution.http_status ? ` · HTTP ${storefrontResolution.http_status}` : ''}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
            <div className={styles.actions}>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleResolveStorefront}
                disabled={resolvingStorefront || savingStorefront || !sellerUrl.trim()}
              >
                {resolvingStorefront ? 'Проверяем…' : 'Проверить ссылку'}
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleSaveStorefront}
                disabled={
                  savingStorefront ||
                  resolvingStorefront ||
                  !storefrontResolution?.verified ||
                  storefrontResolution.seller_url !== sellerUrl.trim()
                }
              >
                {savingStorefront ? 'Подключение…' : storefrontConfigured ? 'Обновить витрину' : 'Подключить витрину'}
              </button>
            </div>
          </section>
        </div>
      ) : (
        <div className="card" style={{ padding: 20, marginTop: 20 }}>
          <h2 style={{ marginBottom: 16 }}>Конфигурация</h2>
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
        </div>
      )}
    </div>
  )
}

