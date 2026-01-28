'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { apiPostData, apiGetData } from '../lib/apiClient'
import { saveTokens, saveUser, isAuthenticated } from '../lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated()) {
      router.push('/app/projects')
    }
  }, [router])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('handleLogin called', { username: username ? '***' : '', password: password ? '***' : '' })
    setError(null)
    
    // Validate inputs
    if (!username.trim() || !password.trim()) {
      setError('Username and password are required')
      return
    }
    
    setLoading(true)

    try {
      console.log('Attempting login with username:', username)
      const loginPayload = { username: username.trim(), password }
      console.log('Sending POST to /api/v1/auth/login with payload:', { username: loginPayload.username, password: '***' })
      // Login
      const tokens = await apiPostData<{ access_token: string; refresh_token: string; token_type: string }>(
        '/api/v1/auth/login',
        loginPayload
      )
      console.log('Login successful, tokens received')
      saveTokens(tokens)

      // Get user info
      const user = await apiGetData<any>('/api/v1/auth/me')
      saveUser(user)

      // Redirect to projects page
      router.push('/app/projects')
    } catch (err: any) {
      console.error('Login error:', err)
      setError(err?.detail || err?.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-logo">
          <Image
            src="/index_logo.jpg"
            alt="E-com Core"
            width={200}
            height={48}
            priority
            className="login-logo-img"
          />
        </div>
        <h2>Login</h2>
        {error && <div className="error-message">{error}</div>}
        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  )
}
