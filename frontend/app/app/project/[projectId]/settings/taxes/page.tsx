'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { apiGetData } from '../../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../../hooks/usePageTitle'

interface TaxProfile {
  project_id: number
  model_code: string
  params_json: Record<string, unknown>
  updated_at: string
}

export default function TaxesSettingsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Налоги', projectId)

  const [profile, setProfile] = useState<TaxProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const loadProfile = async () => {
      try {
        setLoading(true)
        setError(null)
        const data = await apiGetData<TaxProfile>(`/api/v1/projects/${projectId}/taxes/profile`)
        setProfile(data)
      } catch (e: any) {
        if (e?.status === 404) {
          // Profile not found is OK - means no profile exists yet
          setProfile(null)
        } else {
          setError(e?.detail || 'Не удалось загрузить профиль налогов')
        }
      } finally {
        setLoading(false)
      }
    }

    loadProfile()
  }, [projectId])

  const handleCreateProfile = () => {
    // TODO: Implement create profile modal/form
    alert('Создание профиля налогов будет реализовано позже')
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Налоги</h1>
        <Link href={`/app/project/${projectId}/settings`}>← Настройки проекта</Link>
      </div>

      <div className="card" style={{ padding: '20px', marginTop: '20px' }}>
        <p style={{ color: '#666', marginBottom: '20px' }}>
          Настройка профилей налогов и запуск расчёта по периодам.
        </p>

        <div style={{ marginTop: '24px' }}>
          <h2 style={{ marginTop: 0, marginBottom: '16px', fontSize: '1.2rem' }}>
            Профили налогов
          </h2>

          {loading ? (
            <p style={{ color: '#666' }}>Загрузка...</p>
          ) : error ? (
            <div style={{ 
              padding: '12px', 
              backgroundColor: '#fee', 
              border: '1px solid #fcc',
              borderRadius: '4px',
              color: '#c33'
            }}>
              <p style={{ margin: 0 }}>{error}</p>
            </div>
          ) : !profile ? (
            <div style={{ 
              padding: '20px', 
              backgroundColor: '#f9f9f9', 
              border: '1px solid #ddd',
              borderRadius: '4px',
              textAlign: 'center'
            }}>
              <p style={{ margin: 0, color: '#666', marginBottom: '16px' }}>
                Профилей пока нет
              </p>
              <button onClick={handleCreateProfile}>
                Создать профиль
              </button>
            </div>
          ) : (
            <div>
              <div style={{ 
                padding: '16px', 
                backgroundColor: '#f9f9f9', 
                border: '1px solid #ddd',
                borderRadius: '4px',
                marginBottom: '16px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                  <div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '4px' }}>
                      {profile.model_code === 'profit_tax' ? 'Налог на прибыль' : 
                       profile.model_code === 'turnover_tax' ? 'Налог с оборота' : 
                       profile.model_code}
                    </div>
                    <div style={{ fontSize: '0.9rem', color: '#666' }}>
                      Модель: {profile.model_code}
                    </div>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#999' }}>
                    Обновлено: {new Date(profile.updated_at).toLocaleString('ru-RU')}
                  </div>
                </div>
                
                {profile.params_json && Object.keys(profile.params_json).length > 0 && (
                  <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #ddd' }}>
                    <div style={{ fontSize: '0.9rem', color: '#666', marginBottom: '8px' }}>
                      Параметры:
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#555', fontFamily: 'monospace' }}>
                      {JSON.stringify(profile.params_json, null, 2)}
                    </div>
                  </div>
                )}
              </div>

              <div>
                <button onClick={handleCreateProfile} style={{ marginRight: '8px' }}>
                  Редактировать профиль
                </button>
                <Link href={`/app/project/${projectId}/settings`}>
                  <button>Назад к настройкам</button>
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
