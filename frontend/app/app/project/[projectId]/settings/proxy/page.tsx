'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  getProjectProxySettings,
  ProjectProxySettings,
  testProjectProxySettings,
  updateProjectProxySettings,
} from '../../../../../../lib/apiClient'
import { usePageTitle } from '../../../../../../hooks/usePageTitle'

export default function ProjectProxySettingsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  usePageTitle('Прокси для витрины WB', projectId)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const [loaded, setLoaded] = useState<ProjectProxySettings | null>(null)

  // Form state
  const [enabled, setEnabled] = useState(false)
  const [scheme, setScheme] = useState<'http' | 'https'>('http')
  const [host, setHost] = useState('')
  const [port, setPort] = useState<number>(0)
  const [username, setUsername] = useState('')
  const [testUrl, setTestUrl] = useState('https://www.wildberries.ru')

  const [changePassword, setChangePassword] = useState(false)
  const [password, setPassword] = useState('')

  const passwordSet = !!loaded?.password_set

  const warningHint = useMemo(() => {
    if (!enabled) return null
    if (!loaded) return 'Прокси включен, но статус проверки не загружен.'
    if (loaded.last_test_ok === true) return null
    if (loaded.last_test_ok === false) return 'Прокси включен, но последняя проверка завершилась ошибкой.'
    return 'Прокси включен, но проверка ещё не выполнялась.'
  }, [enabled, loaded])

  const load = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getProjectProxySettings(projectId)
      setLoaded(data)

      setEnabled(!!data.enabled)
      setScheme((data.scheme === 'https' ? 'https' : 'http') as 'http' | 'https')
      setHost(data.host || '')
      setPort(typeof data.port === 'number' ? data.port : parseInt(String(data.port || 0), 10) || 0)
      setUsername(data.username || '')
      setTestUrl(data.test_url || 'https://www.wildberries.ru')

      // Reset password UI
      setChangePassword(false)
      setPassword('')
    } catch (e: any) {
      setError(e?.detail || 'Не удалось загрузить настройки прокси')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const showToast = (msg: string, ms: number = 3000) => {
    setToast(msg)
    setTimeout(() => setToast(null), ms)
  }

  const validateBeforeSave = (): string | null => {
    if (enabled) {
      if (!host.trim()) return 'Host обязателен при включенном прокси'
      if (!Number.isFinite(port) || port < 1 || port > 65535) return 'Port должен быть в диапазоне 1..65535'
      if (scheme !== 'http' && scheme !== 'https') return 'Scheme должен быть http или https'
    }
    if (!testUrl.trim()) return 'test_url не может быть пустым'
    if (/\s/.test(testUrl)) return 'test_url не должен содержать пробелы'
    return null
  }

  const onSave = async () => {
    const err = validateBeforeSave()
    if (err) {
      showToast(err, 5000)
      return
    }

    setSaving(true)
    try {
      const payload: any = {
        enabled,
        scheme,
        host: host.trim(),
        port,
        username: username, // empty string allowed (explicit clear)
        rotate_mode: 'fixed',
        test_url: testUrl.trim(),
      }
      if (passwordSet) {
        if (changePassword) {
          if (!password.trim()) {
            showToast('Введите новый пароль или снимите “Сменить пароль”', 5000)
            return
          }
          payload.password = password
        }
      } else {
        // password not set yet: send only if provided
        if (password.trim()) payload.password = password
      }

      await updateProjectProxySettings(projectId, payload)
      showToast('Сохранено')
      await load()
    } catch (e: any) {
      showToast(e?.detail || 'Не удалось сохранить настройки', 5000)
    } finally {
      setSaving(false)
    }
  }

  const onTest = async () => {
    const err = validateBeforeSave()
    if (err) {
      showToast(err, 5000)
      return
    }
    setTesting(true)
    try {
      const res = await testProjectProxySettings(projectId)
      if (res.ok) {
        showToast(`Проверка успешна (HTTP ${res.status_code ?? '—'})`)
      } else {
        showToast(`Проверка не прошла: ${res.error || 'unknown_error'}`, 6000)
      }
      await load()
    } catch (e: any) {
      showToast(e?.detail || 'Не удалось выполнить проверку', 6000)
      await load().catch(() => {})
    } finally {
      setTesting(false)
    }
  }

  const fmtDate = (s: string | null | undefined) => {
    if (!s) return '—'
    try {
      return new Date(s).toLocaleString('ru-RU')
    } catch {
      return s
    }
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h1>Прокси для витрины WB</h1>
        <Link href={`/app/project/${projectId}/settings`}>← Настройки проекта</Link>
      </div>

      {toast && <div className="toast">{toast}</div>}

      <div className="card" style={{ padding: 20, marginTop: 20 }}>
        <p style={{ color: '#666', marginBottom: 16 }}>
          Настройка прокси применяется <strong>только</strong> для задачи загрузки витринных цен (frontend_prices).
        </p>

        {loading ? (
          <p style={{ color: '#666' }}>Загрузка…</p>
        ) : error ? (
          <div
            style={{
              padding: 12,
              backgroundColor: '#fee',
              border: '1px solid #fcc',
              borderRadius: 4,
              color: '#c33',
            }}
          >
            {error}
          </div>
        ) : (
          <>
            {warningHint && (
              <div
                style={{
                  padding: 12,
                  marginBottom: 16,
                  backgroundColor: '#fff3cd',
                  border: '1px solid #ffc107',
                  borderRadius: 4,
                  color: '#856404',
                }}
              >
                <strong>Внимание:</strong> {warningHint}
              </div>
            )}

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 16,
                alignItems: 'stretch',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Использовать прокси</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, height: 38 }}>
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) => setEnabled(e.target.checked)}
                    style={{ width: 16, height: 16 }}
                  />
                  <span style={{ color: '#374151', fontSize: 13 }}>{enabled ? 'Включено' : 'Выключено'}</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Scheme</label>
                <select
                  value={scheme}
                  onChange={(e) => setScheme(e.target.value as 'http' | 'https')}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                >
                  <option value="http">http</option>
                  <option value="https">https</option>
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Host</label>
                <input
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="proxy.example.com"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Port</label>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={port}
                  onChange={(e) => setPort(parseInt(e.target.value || '0', 10) || 0)}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Username (optional)</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="user"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Password (optional)</label>
                {passwordSet && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <input
                      type="checkbox"
                      checked={changePassword}
                      onChange={(e) => {
                        setChangePassword(e.target.checked)
                        setPassword('')
                      }}
                      style={{ width: 16, height: 16 }}
                    />
                    <span style={{ fontSize: 13, color: '#374151' }}>Сменить пароль</span>
                  </div>
                )}
                <input
                  type="password"
                  value={passwordSet && !changePassword ? '' : password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={passwordSet && !changePassword ? '••••••' : ''}
                  disabled={passwordSet && !changePassword}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                    backgroundColor: passwordSet && !changePassword ? '#f9fafb' : '#fff',
                  }}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, gridColumn: '1 / -1' }}>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Test URL</label>
                <input
                  type="text"
                  value={testUrl}
                  onChange={(e) => setTestUrl(e.target.value)}
                  placeholder="https://www.wildberries.ru"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: 5,
                    border: '1px solid #d1d5db',
                    fontSize: 14,
                    height: 38,
                  }}
                />
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  По умолчанию: <code>https://www.wildberries.ru</code>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 13, color: '#6b7280' }}>
                <div>
                  <strong>Последняя проверка:</strong> {fmtDate(loaded?.last_test_at)}
                </div>
                <div style={{ marginTop: 2 }}>
                  <strong>Статус:</strong>{' '}
                  {loaded?.last_test_ok === true ? (
                    <span style={{ color: '#166534' }}>OK</span>
                  ) : loaded?.last_test_ok === false ? (
                    <span style={{ color: '#b91c1c' }}>Ошибка</span>
                  ) : (
                    '—'
                  )}
                  {loaded?.last_test_ok === false && loaded?.last_test_error ? (
                    <span style={{ marginLeft: 8, color: '#b91c1c' }}>{loaded.last_test_error}</span>
                  ) : null}
                </div>
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={onTest} disabled={testing || saving || !enabled}>
                  {testing ? 'Проверка…' : 'Проверить'}
                </button>
                <button onClick={onSave} disabled={saving || testing}>
                  {saving ? 'Сохранение…' : 'Сохранить'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

