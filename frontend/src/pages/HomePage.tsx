import { useEffect, useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { fetchMyTeams, setupMyGroup, type Team } from '../api/client'
import { useAuth } from '../auth'
import { CourseShell } from '../components/CourseShell'
import { LandingPage } from './LandingPage'

export function HomePage() {
  const { user, loading } = useAuth()
  const [teams, setTeams] = useState<Team[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [githubUrl, setGithubUrl] = useState('')
  const [createdId, setCreatedId] = useState<string | null>(null)

  useEffect(() => {
    if (!user) {
      setTeams([])
      return
    }
    void fetchMyTeams()
      .then(setTeams)
      .catch((err: unknown) => {
        setTeams([])
        setError(err instanceof Error ? err.message : 'Failed to load teams')
      })
  }, [user])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <LandingPage />
  if (teams === null) return <main className="page-fallback">Loading…</main>
  if (createdId) return <Navigate to={`/teams/${createdId}/exit`} replace />
  if (teams.length > 0) return <Navigate to={`/teams/${teams[0].id}/exit`} replace />

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    if (!user || !githubUrl.trim()) return
    const name = (user.group_name || user.display_name || user.username || 'Group').trim()
    setBusy(true)
    setError(null)
    try {
      const result = await setupMyGroup({
        name,
        github_url: githubUrl.trim(),
        scenario_slug: 'library',
      })
      setCreatedId(result.team.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save repository')
    } finally {
      setBusy(false)
    }
  }

  return (
    <CourseShell subtitle="Add your repository to begin interviews">
      <div className="stack">
        {error && <p className="error">{error}</p>}
        <section className="surface">
          <h2>Repository</h2>
          <p className="hint" style={{ marginBottom: 12 }}>
            Your group is already claimed
            {user?.group_name ? ` (${user.group_name})` : ''}. Paste the GitHub URL (no commit hash).
          </p>
          <form className="auth-form" onSubmit={onCreate}>
            <label>
              Repository URL
              <input
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                placeholder="https://github.com/org/repo or fixture://demo"
                required
              />
            </label>
            <button type="submit" disabled={busy || !githubUrl.trim()}>
              {busy ? 'Saving…' : 'Save & continue'}
            </button>
          </form>
        </section>
      </div>
    </CourseShell>
  )
}
