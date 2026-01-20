'use client'

import { useEffect, useState } from 'react'
import { apiGet, apiPost, ApiError } from '../../../../../../lib/apiClient'
import { getUser, User } from '../../../../../../lib/auth'
import '../../../../../globals.css'

interface WBTariffTypeStatus {
  latest_fetched_at?: string | null
  latest_as_of_date?: string | null
  locale?: string | null
}

interface WBTariffsStatusResponse {
  marketplace_code: string
  data_domain: string
  latest_fetched_at?: string | null
  types: Record<string, WBTariffTypeStatus>
}

interface IngestResponse {
  status: string
  days_ahead: number
  task: string
}

export default function WBTariffsAdminPage() {
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [loadingUser, setLoadingUser] = useState<boolean>(true)
  const [status, setStatus] = useState<WBTariffsStatusResponse | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [startingIngest, setStartingIngest] = useState(false)
  const [cooldown, setCooldown] = useState(false)
  const [daysAhead, setDaysAhead] = useState<number>(14)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const localUser = getUser()
  const isAdmin = (currentUser?.is_superuser ?? localUser?.is_superuser) ?? false

  useEffect(() => {
    const loadMe = async () => {
      try {
        setLoadingUser(true)
        const { data } = await apiGet<User>('/v1/auth/me')
        setCurrentUser(data)
      } catch (e) {
        // Если не удалось получить /me (401 и т.п.), считаем, что прав нет
        setCurrentUser(null)
      } finally {
        setLoadingUser(false)
      }
    }
    loadMe()
  }, [])

  useEffect(() => {
    if (!loadingUser && isAdmin) {
      loadStatus()
    }
  }, [loadingUser, isAdmin])

  const loadStatus = async () => {
    setLoadingStatus(true)
    setError(null)
    try {
      const { data } = await apiGet<WBTariffsStatusResponse>(
        '/v1/admin/marketplaces/wildberries/tariffs/status'
      )
      setStatus(data)
    } catch (e: any) {
      const err = e as ApiError
      if (err.status === 401 || err.status === 403) {
        setError('Недостаточно прав (требуется admin/superuser).')
      } else {
        setError(err.detail || 'Не удалось загрузить статус тарифов.')
      }
    } finally {
      setLoadingStatus(false)
    }
  }

  const handleStartIngest = async () => {
    setStartingIngest(true)
    setError(null)
    setInfo(null)
    try {
      const payloadDays = Math.min(30, Math.max(0, daysAhead || 0))
      const { data } = await apiPost<IngestResponse>(
        '/v1/admin/marketplaces/wildberries/tariffs/ingest',
        { days_ahead: payloadDays }
      )
      setInfo(
        `Запущено обновление тарифов (days_ahead=${data.days_ahead}, task_id=${data.task_id || 'n/a'}).`
      )
      // Блокируем кнопку на 10 секунд после запуска
      setCooldown(true)
      setTimeout(() => {
        setCooldown(false)
      }, 10000)
      // Через пару секунд обновим статус
      setTimeout(() => {
        loadStatus()
      }, 2500)
    } catch (e: any) {
      const err = e as ApiError
      if (err.status === 401 || err.status === 403) {
        setError('Недостаточно прав (требуется admin/superuser).')
      } else {
        setError(err.detail || 'Не удалось запустить обновление тарифов.')
      }
    } finally {
      setStartingIngest(false)
    }
  }

  if (loadingUser) {
    return (
      <div className="container">
        <h1>Wildberries — Tariffs (Admin)</h1>
        <p>Загрузка информации о пользователе...</p>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="container">
        <h1>Wildberries — Tariffs (Admin)</h1>
        <p>Недостаточно прав для просмотра этого раздела. Требуются admin/superuser права.</p>
      </div>
    )
  }

  const renderTypeRow = (type: string, data?: WBTariffTypeStatus) => {
    if (!data) return null
    return (
      <tr key={type}>
        <td>{type}</td>
        <td>{data.latest_fetched_at || '—'}</td>
        <td>{data.latest_as_of_date || '—'}</td>
        <td>{data.locale || '—'}</td>
      </tr>
    )
  }

  return (
    <div className="container">
      <h1>Wildberries — Tariffs (Admin, global)</h1>

      <div className="card" style={{ marginTop: '16px' }}>
        <h2>Статус последнего обновления</h2>
        {loadingStatus && <p>Загрузка статуса...</p>}
        {error && (
          <p style={{ color: 'red', marginTop: '8px' }}>
            {error}
          </p>
        )}
        {!loadingStatus && !error && status && (
          <div>
            <p>
              <strong>Последний snapshot (любой тип):</strong>{' '}
              {status.latest_fetched_at || 'нет данных'}
            </p>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '12px' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>Тип</th>
                  <th style={{ textAlign: 'left' }}>Последний fetched_at</th>
                  <th style={{ textAlign: 'left' }}>Последний as_of_date</th>
                  <th style={{ textAlign: 'left' }}>Locale</th>
                </tr>
              </thead>
              <tbody>
                {renderTypeRow('commission', status.types?.commission)}
                {renderTypeRow('acceptance_coefficients', status.types?.acceptance_coefficients)}
                {renderTypeRow('box', status.types?.box)}
                {renderTypeRow('pallet', status.types?.pallet)}
                {renderTypeRow('return', status.types?.return)}
              </tbody>
            </table>
          </div>
        )}
        <button style={{ marginTop: '8px' }} onClick={loadStatus} disabled={loadingStatus}>
          {loadingStatus ? 'Обновляем статус...' : 'Обновить статус'}
        </button>
      </div>

      <div className="card" style={{ marginTop: '24px' }}>
        <h2>Ручной запуск обновления тарифов WB</h2>
        <p style={{ marginBottom: '8px' }}>
          Обновление тарифов выполняется на уровне маркетплейса (для всех проектов). При запуске
          ставится Celery‑задача, выполнение происходит в фоне.
        </p>

        <div className="form-group" style={{ maxWidth: '220px' }}>
          <label>Days ahead (0–30)</label>
          <input
            type="number"
            min={0}
            max={30}
            value={daysAhead}
            onChange={(e) => setDaysAhead(Number(e.target.value))}
          />
        </div>

        <div style={{ marginTop: '12px' }}>
          <button onClick={handleStartIngest} disabled={startingIngest || cooldown}>
            {startingIngest ? 'Запуск...' : cooldown ? 'Подождите...' : 'Обновить тарифы WB'}
          </button>
        </div>

        {info && (
          <p style={{ color: 'green', marginTop: '8px' }}>
            {info}
          </p>
        )}
        {error && (
          <p style={{ color: 'red', marginTop: '8px' }}>
            {error}
          </p>
        )}
      </div>
    </div>
  )
}

