import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { fetchMyTeams, isInstructor, type Team } from '../api/client'
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

  const admin = isInstructor(user)

  return (
    <CourseShell subtitle="Assigned teams for this cohort login">
      <div className="stack">
        <div className="toolbar">
          <p className="lede">
            {admin
              ? 'Admins assign teams to cohort credentials in Admin → Teams. Students share that login and type names at the interview.'
              : 'Your instructor assigns a team to this login. Share the account with teammates and enter real names when you start the exit interview.'}
          </p>
          {admin ? (
            <a
              className="btn-primary"
              href="/admin"
              style={{
                display: 'inline-block',
                padding: '0.55rem 0.85rem',
                borderRadius: 10,
                color: '#fff',
                textDecoration: 'none',
                fontWeight: 600,
              }}
            >
              Manage teams
            </a>
          ) : null}
        </div>

        {error && <p className="error">{error}</p>}

        {teams.length === 0 ? (
          <div className="surface">
            <h2>No team yet</h2>
            <p className="hint">
              {admin
                ? 'Open Admin → Teams to create a team and attach a cohort username (e.g. trainee01).'
                : 'Ask your instructor to assign this cohort login to a team.'}
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
