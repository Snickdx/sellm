import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import {
  claimGroup,
  searchRoster,
  type ClaimResult,
  type PublicStudent,
} from '../api/client'
import { useAuth } from '../auth'

const MIN = 3
const MAX = 4

export function ClaimGroupPage() {
  const { user, loading } = useAuth()
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<PublicStudent[]>([])
  const [selected, setSelected] = useState<PublicStudent[]>([])
  const [groupName, setGroupName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ClaimResult | null>(null)

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
    setError(null)
  }

  function removeStudent(id: string) {
    setSelected((prev) => prev.filter((s) => s.id !== id))
  }

  async function onClaim(event: FormEvent) {
    event.preventDefault()
    if (selected.length < MIN || selected.length > MAX) {
      setError(`Select ${MIN}–${MAX} classmates (you + 2 or 3 others).`)
      return
    }
    if (!groupName.trim()) {
      setError('Enter a group name.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const claimed = await claimGroup({
        group_name: groupName.trim(),
        member_ids: selected.map((s) => s.id),
      })
      setResult(claimed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Claim failed')
    } finally {
      setBusy(false)
    }
  }

  if (result) {
    return (
      <main className="auth-shell">
        <section className="auth-panel" style={{ maxWidth: 520 }}>
          <p className="eyebrow">sellm · course</p>
          <h1>Group claimed</h1>
          <p className="lede">
            Save these credentials now. The password is shown only once. Everyone in the group
            shares this login for exit interviews.
          </p>
          <div className="surface" style={{ padding: 14, marginBottom: 14 }}>
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
          <Link className="btn-link-block" to="/login">
            Continue to sign in
          </Link>
        </section>
      </main>
    )
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" style={{ maxWidth: 560 }}>
        <p className="eyebrow">sellm · course</p>
        <h1>Form a group</h1>
        <p className="lede">
          Search classmates by name, pick yourself plus 2 or 3 others, choose a group name, then
          claim a shared login. Student IDs are never shown here.
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
                  <button type="button" className="ghost claim-hit" onClick={() => addStudent(row)}>
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
                    <button type="button" className="ghost danger" onClick={() => removeStudent(row.id)}>
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

          {error ? <p className="error">{error}</p> : null}

          <button
            type="submit"
            disabled={busy || selected.length < MIN || selected.length > MAX || !groupName.trim()}
          >
            {busy ? 'Claiming…' : 'Claim shared credentials'}
          </button>
        </form>

        <p className="hint" style={{ marginTop: 14 }}>
          Already have credentials? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  )
}
