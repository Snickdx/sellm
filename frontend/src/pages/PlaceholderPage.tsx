import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { createTeam } from '../api/client'
import { useAuth } from '../auth'
import { CourseShell } from '../components/CourseShell'

export function AdminTeamsPage() {
  const { user, loading } = useAuth()
  const [name, setName] = useState('')
  const [scenarioSlug, setScenarioSlug] = useState('')
  const [createdTeamId, setCreatedTeamId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />

  async function onCreateTeam(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const team = await createTeam(name.trim(), scenarioSlug.trim() || undefined)
      setCreatedTeamId(team.id)
      setMessage(`Created “${team.name}”. Share this cohort login — teammates type names at exit.`)
      setName('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create team')
    } finally {
      setBusy(false)
    }
  }

  return (
    <CourseShell title="Create team" subtitle="Shared login owns the team · no invites">
      <div className="stack">
        <div className="toolbar">
          <p className="lede">
            Teammates use the same requirements-chat credentials. Names are collected when the exit
            interview starts.
          </p>
        </div>

        {error && <p className="error">{error}</p>}
        {message && (
          <div className="surface">
            <p className="hint" style={{ margin: 0 }}>
              {message}
            </p>
            {createdTeamId ? (
              <span className="team-actions" style={{ marginTop: 10 }}>
                <Link to={`/admin/teams/${createdTeamId}/repository`}>Freeze repo</Link>
                <Link to={`/teams/${createdTeamId}/exit`}>Exit interview</Link>
              </span>
            ) : null}
          </div>
        )}

        <section className="surface">
          <h2>New team</h2>
          <form className="auth-form" onSubmit={onCreateTeam}>
            <div className="form-grid two">
              <label>
                Team name
                <input value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
              <label>
                Scenario slug (optional)
                <input
                  value={scenarioSlug}
                  onChange={(e) => setScenarioSlug(e.target.value)}
                  placeholder="e.g. uwi-connect"
                />
              </label>
            </div>
            <button type="submit" disabled={busy}>
              {busy ? 'Working…' : 'Create team'}
            </button>
          </form>
        </section>
      </div>
    </CourseShell>
  )
}
