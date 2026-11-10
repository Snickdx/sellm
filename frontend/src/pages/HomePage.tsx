import { useEffect, useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { fetchMyTeams, setupMyGroup, type Team } from '../api/client'
import { useAuth } from '../auth'
import { CourseShell } from '../components/CourseShell'

export function HomePage() {
  const { user, loading } = useAuth()
  const [teams, setTeams] = useState<Team[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [createdId, setCreatedId] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    void fetchMyTeams()
      .then(setTeams)
      .catch((err: unknown) => {
        setTeams([])
        setError(err instanceof Error ? err.message : 'Failed to load teams')
      })
  }, [user])

  if (loading || teams === null) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />
  if (createdId) return <Navigate to={`/teams/${createdId}/exit`} replace />
  if (teams.length > 0) return <Navigate to={`/teams/${teams[0].id}/exit`} replace />

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    if (!groupName.trim() || !githubUrl.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await setupMyGroup({
        name: groupName.trim(),
        github_url: githubUrl.trim(),
        scenario_slug: 'library',
      })
      setCreatedId(result.team.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create group')
    } finally {
      setBusy(false)
    }
  }

  return (
    <CourseShell subtitle="Set up your group to begin">
      <div className="stack">
        {error && <p className="error">{error}</p>}
        <section className="surface">
          <h2>Group settings</h2>
          <p className="hint" style={{ marginBottom: 12 }}>
            Enter a group name and repository URL (no commit hash). Then you can start interviews.
          </p>
          <form className="auth-form" onSubmit={onCreate}>
            <label>
              Group name
              <input
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                placeholder="Team Alpha"
                required
              />
            </label>
            <label>
              Repository URL
              <input
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/org/repo or fixture://demo"
                required
              />
            </label>
            <button type="submit" disabled={busy || !groupName.trim() || !githubUrl.trim()}>
              {busy ? 'Saving…' : 'Save & continue'}
            </button>
          </form>
        </section>
      </div>
    </CourseShell>
  )
}
