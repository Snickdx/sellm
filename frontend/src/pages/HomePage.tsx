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
  const mine = admin ? teams : teams.slice(0, 1)

  // One assigned team → go straight to the interview.
  if (!admin && mine.length === 1) {
    return <Navigate to={`/teams/${mine[0].id}/exit`} replace />
  }

  return (
    <CourseShell subtitle="Your assigned exit interview">
      <div className="stack">
        <p className="lede">
          {admin
            ? 'Teams, repos, scenarios, and member names are managed in Admin. Students open their assigned interview from here.'
            : 'Your instructor assigns a team in Admin. Open the interview when it appears below.'}
        </p>

        {admin ? (
          <p>
            <a className="btn-primary" href="/admin?view=teams">
              Open Admin → Teams
            </a>
          </p>
        ) : null}

        {error && <p className="error">{error}</p>}

        {mine.length === 0 ? (
          <section className="surface">
            <h2>No team assigned</h2>
            <p className="hint">
              {admin
                ? 'Create a team under Admin → Teams (group name, scenario, repo, member names, cohort login).'
                : 'Ask your instructor to assign this login to a team.'}
            </p>
          </section>
        ) : (
          <ul className="team-list">
            {mine.map((team) => (
              <li key={team.id}>
                <strong>{team.name}</strong>
                <span>{team.scenario_slug ?? 'no scenario'}</span>
                <span className="team-actions">
                  <Link to={`/teams/${team.id}/exit`}>Open interview</Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </CourseShell>
  )
}
