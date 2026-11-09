import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { fetchMyTeams, type Team } from '../api/client'
import { useAuth } from '../auth'

export function HomePage() {
  const { user, loading, logout } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    void fetchMyTeams()
      .then(setTeams)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load teams'))
  }, [user])

  if (loading) return <main className="page"><p>Loading…</p></main>
  if (!user) return <Navigate to="/login" replace />

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Course</p>
          <h1>Exit interviews</h1>
        </div>
        <div className="user-meta">
          <span>
            {user.display_name} · {user.role}
          </span>
          <button type="button" className="ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      <section className="panel">
        <h2>Your teams</h2>
        <p className="lede">Self-service: create or join a team, freeze your repo, then run the exit interview.</p>
        <p>
          <Link to="/policy">Consent &amp; retention policy</Link>
          {' · '}
          <Link to="/admin/teams">Create / join team</Link>
        </p>
        {error && <p className="error">{error}</p>}
        {teams.length === 0 ? (
          <p>
            No teams yet. <Link to="/admin/teams">Create one or join with an invite code</Link>.
          </p>
        ) : (
          <ul className="team-list">
            {teams.map((team) => (
              <li key={team.id}>
                <strong>{team.name}</strong>
                <span>
                  {team.scenario_slug ?? 'unassigned'} · invite <code>{team.invite_code}</code>
                </span>
                <span className="team-actions">
                  <Link to={`/admin/teams/${team.id}/repository`}>Repository</Link>
                  <Link to={`/teams/${team.id}/exit`}>Exit interview</Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
