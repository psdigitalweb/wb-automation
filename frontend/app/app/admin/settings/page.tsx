'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { getUser, User } from '../../../../lib/auth'
import { apiGet, ApiError } from '../../../../lib/apiClient'

export default function AdminSettingsPage() {
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [loadingUser, setLoadingUser] = useState<boolean>(true)

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

  if (loadingUser) {
    return (
      <div className="container">
        <h1>Admin Settings</h1>
        <p>Загрузка информации о пользователе...</p>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="container">
        <h1>Admin Settings</h1>
        <p>Недостаточно прав для просмотра этого раздела. Требуются admin/superuser права.</p>
      </div>
    )
  }

  return (
    <div className="container">
      <h1>Admin Settings</h1>
      <p style={{ marginBottom: '24px', color: '#666' }}>
        Глобальные системные настройки приложения.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px', marginTop: '24px' }}>
        <Link href="/app/admin/users" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="card" style={{ cursor: 'pointer', transition: 'transform 0.2s', height: '100%' }}>
            <h2 style={{ marginTop: 0 }}>Пользователи</h2>
            <p style={{ color: '#666', marginBottom: 0 }}>
              Управление пользователями системы: создание, удаление, просмотр списка пользователей.
            </p>
          </div>
        </Link>

        <Link href="/app/admin/settings/marketplaces" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="card" style={{ cursor: 'pointer', transition: 'transform 0.2s', height: '100%' }}>
            <h2 style={{ marginTop: 0 }}>Marketplace Settings</h2>
            <p style={{ color: '#666', marginBottom: 0 }}>
              Глобальные настройки маркетплейсов: включение/отключение, видимость, порядок сортировки, системные параметры.
            </p>
          </div>
        </Link>

        <Link href="/app/admin/settings/wb-tariffs" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="card" style={{ cursor: 'pointer', transition: 'transform 0.2s', height: '100%' }}>
            <h2 style={{ marginTop: 0 }}>WB Tariffs</h2>
            <p style={{ color: '#666', marginBottom: 0 }}>
              Управление тарифами Wildberries: статус обновлений, ручной запуск синхронизации тарифов.
            </p>
          </div>
        </Link>
      </div>
    </div>
  )
}
