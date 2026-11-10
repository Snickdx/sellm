import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { fetchMyTeams, type Team } from '../api/client'
import { useAuth } from '../auth'
import { CourseShell } from '../components/CourseShell'

export function HomePage() {
  const { user, loading } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    void fetchMyTeams()
      .then(setTeams)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load teams'))
  }, [user])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />

  return (
    <CourseShell title="Your teams" subtitle="One cohort login · names entered at exit interview">
      <div className="stack">
        <div className="toolbar">
          <p className="lede">
            Share this login with teammates. Create a team, freeze the repo, then start the exit
            interview and type each person’s name.
          </p>
          <Link className="btn-primary" to="/admin/teams" style={{ display: 'inline-block', padding: '0.55rem 0.85rem', borderRadius: 10, color: '#fff', textDecoration: 'none', fontWeight: 600 }}>
            Create team
          </Link>
        </div>

        {error && <p className="error">{error}</p>}

        {teams.length === 0 ? (
          <div className="surface">
            <h2>Empty</h2>
            <p className="hint">No teams yet for this account.</p>
            <p style={{ marginTop: 10 }}>
              <Link to="/admin/teams">Create your first team</Link>
            </p>
          </div>
        ) : (
          <ul className="team-list">
            {teams.map((team) => (
              <li key={team.id}>
                <strong>{team.name}</strong>
                <span>{team.scenario_slug ?? 'no scenario'}</span>
                <span className="team-actions">
                  <Link to={`/admin/teams/${team.id}/repository`}>Repository</Link>
                  <Link to={`/teams/${team.id}/exit`}>Exit interview</Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </CourseShell>
  )
}
