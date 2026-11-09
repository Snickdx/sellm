import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { login } from '../api/client'
import { useAuth } from '../auth'

export function LoginPage() {
  const { user, loading, setToken } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) return <Navigate to="/" replace />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const token = await login(username.trim(), password)
      setToken(token)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <p className="eyebrow">Course</p>
        <h1>Exit interview platform</h1>
        <p className="lede">Sign in with your cohort username and password.</p>

        <form onSubmit={onSubmit} className="auth-form">
          <label>
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? 'Working…' : 'Log in'}
          </button>
        </form>

        <p className="hint">
          <Link to="/">Back home</Link>
        </p>
      </section>
    </main>
  )
}
