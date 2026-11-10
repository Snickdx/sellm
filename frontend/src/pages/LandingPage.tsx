import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import {
  claimGroup,
  login,
  searchRoster,
  type ClaimResult,
  type PublicStudent,
} from '../api/client'
import { useAuth } from '../auth'

const MIN = 3
const MAX = 4

export function LandingPage() {
  const { user, loading, setToken } = useAuth()
  const navigate = useNavigate()

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<PublicStudent[]>([])
  const [selected, setSelected] = useState<PublicStudent[]>([])
  const [groupName, setGroupName] = useState('')
  const [claimBusy, setClaimBusy] = useState(false)
  const [claimError, setClaimError] = useState<string | null>(null)
  const [result, setResult] = useState<ClaimResult | null>(null)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loginBusy, setLoginBusy] = useState(false)

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setHits([])
      return
    }
    const handle = window.setTimeout(() => {
      void searchRoster(q)
        .then((rows) => {
          const taken = new Set(selected.map((s) => s.id))
          setHits(rows.filter((r) => !taken.has(r.id)))
        })
        .catch(() => setHits([]))
    }, 200)
    return () => window.clearTimeout(handle)
  }, [query, selected])

  const selectedIds = useMemo(() => new Set(selected.map((s) => s.id)), [selected])

  if (!loading && user) return <Navigate to="/" replace />

  function addStudent(row: PublicStudent) {
    if (selectedIds.has(row.id) || selected.length >= MAX) return
    setSelected((prev) => [...prev, row])
    setQuery('')
    setHits([])
    setClaimError(null)
  }

  function removeStudent(id: string) {
    setSelected((prev) => prev.filter((s) => s.id !== id))
  }

  async function onClaim(event: FormEvent) {
    event.preventDefault()
    if (selected.length < MIN || selected.length > MAX) {
      setClaimError(`Select ${MIN}–${MAX} classmates (you + 2 or 3 others).`)
      return
    }
    if (!groupName.trim()) {
      setClaimError('Enter a group name.')
      return
    }
    setClaimBusy(true)
    setClaimError(null)
    try {
      const claimed = await claimGroup({
        group_name: groupName.trim(),
        member_ids: selected.map((s) => s.id),
      })
      setResult(claimed)
      setUsername(claimed.username)
      setPassword(claimed.password)
    } catch (err) {
      setClaimError(err instanceof Error ? err.message : 'Claim failed')
    } finally {
      setClaimBusy(false)
    }
  }

  async function onLogin(event: FormEvent) {
    event.preventDefault()
    setLoginBusy(true)
    setLoginError(null)
    try {
      const token = await login(username.trim(), password)
      setToken(token)
      navigate('/')
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoginBusy(false)
    }
  }

  return (
    <main className="auth-shell landing-shell">
      <div className="landing-grid">
        <section className="auth-panel landing-panel">
          <p className="eyebrow">sellm · course</p>
          <h1>{result ? 'Group claimed' : 'Form a group'}</h1>
          {result ? (
            <>
              <p className="lede">
                Save these credentials now. The password is shown only once. Sign in on the right
                with the same details.
              </p>
              <div className="surface" style={{ padding: 14 }}>
                <p className="hint" style={{ margin: '0 0 8px' }}>
                  Group · {result.group_name}
                </p>
                <p style={{ margin: '0 0 6px' }}>
                  <strong>Username</strong>
                  <br />
                  <code>{result.username}</code>
                </p>
                <p style={{ margin: '0 0 6px' }}>
                  <strong>Password</strong>
                  <br />
                  <code>{result.password}</code>
                </p>
                <p className="hint" style={{ margin: '10px 0 0' }}>
                  Members: {result.members.join(', ')}
                </p>
              </div>
            </>
          ) : (
            <>
              <p className="lede">
                Search classmates by name, pick yourself plus 2 or 3 others, choose a group name,
                then claim a shared login. Student IDs are never shown here.
              </p>
              <form className="auth-form" onSubmit={onClaim}>
                <label>
                  Search classmates
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Type a first or last name"
                    autoComplete="off"
                    disabled={selected.length >= MAX}
                  />
                </label>

                {hits.length > 0 ? (
                  <ul className="claim-hits">
                    {hits.map((row) => (
                      <li key={row.id}>
                        <button
                          type="button"
                          className="ghost claim-hit"
                          onClick={() => addStudent(row)}
                        >
                          <strong>{row.display_name}</strong>
                          <span className="hint">{row.email}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}

                <div className="claim-selected">
                  <p className="hint" style={{ margin: '0 0 8px' }}>
                    Selected {selected.length}/{MAX} (need {MIN}–{MAX})
                  </p>
                  {selected.length === 0 ? (
                    <p className="hint">No members selected yet.</p>
                  ) : (
                    <ul className="consent-checklist">
                      {selected.map((row) => (
                        <li key={row.id} className="claim-chip">
                          <span>
                            {row.display_name}
                            <span className="hint"> · {row.email}</span>
                          </span>
                          <button
                            type="button"
                            className="ghost danger"
                            onClick={() => removeStudent(row.id)}
                          >
                            Remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <label>
                  Group name
                  <input
                    value={groupName}
                    onChange={(e) => setGroupName(e.target.value)}
                    placeholder="e.g. ByteForce"
                    required
                    minLength={2}
                    maxLength={80}
                  />
                </label>

                {claimError ? <p className="error">{claimError}</p> : null}

                <button
                  type="submit"
                  disabled={
                    claimBusy ||
                    selected.length < MIN ||
                    selected.length > MAX ||
                    !groupName.trim()
                  }
                >
                  {claimBusy ? 'Claiming…' : 'Claim shared credentials'}
                </button>
              </form>
            </>
          )}
        </section>

        <section className="auth-panel landing-panel landing-login">
          <p className="eyebrow">already claimed?</p>
          <h1>Sign in</h1>
          <p className="lede">
            Use your group&apos;s shared username and password to open exit interviews.
          </p>
          <form onSubmit={onLogin} className="auth-form">
            <label>
              Username
              <input
                className="login-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
              />
            </label>
            <label>
              Password
              <input
                className="login-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </label>
            {loginError ? <p className="error">{loginError}</p> : null}
            <button type="submit" disabled={loginBusy}>
              {loginBusy ? 'Signing in…' : 'Log in'}
            </button>
          </form>
          <p className="hint" style={{ marginTop: 14 }}>
            <a href="/req">Requirements chat</a>
          </p>
        </section>
      </div>
    </main>
  )
}
