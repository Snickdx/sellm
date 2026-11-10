import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import {
  fetchMyTeams,
  isInstructor,
  listScenarios,
  listTeamRepositories,
  setupMyGroup,
  type RepositorySubmission,
  type ScenarioListItem,
  type Team,
} from '../api/client'
import { useAuth } from '../auth'
import { CourseShell } from '../components/CourseShell'

export function HomePage() {
  const { user, loading } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [scenarios, setScenarios] = useState<ScenarioListItem[]>([])
  const [repoStatus, setRepoStatus] = useState<RepositorySubmission | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState('')
  const [scenarioSlug, setScenarioSlug] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [savedHint, setSavedHint] = useState<string | null>(null)

  async function refresh() {
    const list = await fetchMyTeams()
    setTeams(list)
    const primary = list[0]
    if (primary) {
      setName(primary.name || '')
      setScenarioSlug(primary.scenario_slug || '')
      try {
        const repos = await listTeamRepositories(primary.id)
        const latest = repos[0] ?? null
        setRepoStatus(latest)
        if (latest) setGithubUrl(latest.github_url)
      } catch {
        setRepoStatus(null)
      }
    }
  }

  useEffect(() => {
    if (!user) return
    void listScenarios()
      .then((rows) => {
        setScenarios(rows)
        if (!scenarioSlug && rows[0]) setScenarioSlug(rows[0].slug)
      })
      .catch(() => setScenarios([]))
    void refresh().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : 'Failed to load teams'),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />

  const admin = isInstructor(user)
  const primary = teams[0] ?? null
  const setupReady =
    !!primary?.scenario_slug &&
    !!repoStatus &&
    (repoStatus.index_status === 'ready' || repoStatus.index_status === 'pending')

  async function onSetup(event: FormEvent) {
    event.preventDefault()
    if (!name.trim() || !scenarioSlug || !githubUrl.trim()) return
    setBusy(true)
    setError(null)
    setSavedHint(null)
    try {
      const result = await setupMyGroup({
        name: name.trim(),
        scenario_slug: scenarioSlug,
        github_url: githubUrl.trim(),
      })
      setTeams([result.team])
      setRepoStatus(result.repository)
      setSavedHint(
        result.repository.index_status === 'ready'
          ? 'Group saved. Repository is ready — start the interview when you are.'
          : 'Group saved. Repository is indexing; you can open the interview once it is ready.',
      )
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <CourseShell subtitle="Exit interviews · group setup then member names">
      <div className="stack">
        <div className="toolbar">
          <p className="lede">
            {admin
              ? 'Students add group details (repo, group name, scenario), then enter member names when starting the interview. Admins can still manage teams in Admin → Teams.'
              : 'Step 1: add your group details (repository URL, group name, scenario). Step 2: open the interview and enter group member names.'}
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
        {savedHint && <p className="hint">{savedHint}</p>}

        <section className="surface">
          <h2>Group details</h2>
          <p className="hint" style={{ marginBottom: 12 }}>
            No commit hash needed — the current default branch tip is used.
          </p>
          <form className="auth-form" onSubmit={onSetup}>
            <label>
              Group name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Team Alpha"
                required
              />
            </label>
            <label>
              Scenario
              <select
                value={scenarioSlug}
                onChange={(e) => setScenarioSlug(e.target.value)}
                required
              >
                <option value="">Select…</option>
                {scenarios.map((s) => (
                  <option key={s.slug} value={s.slug}>
                    {s.title || s.slug}
                  </option>
                ))}
              </select>
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
            {repoStatus ? (
              <p className="muted-row">
                <span>
                  {repoStatus.repo}
                  {repoStatus.commit_sha ? `@${repoStatus.commit_sha.slice(0, 7)}` : ''}
                </span>
                <span>{repoStatus.index_status}</span>
                {repoStatus.index_error ? <span className="error">{repoStatus.index_error}</span> : null}
              </p>
            ) : null}
            <button type="submit" disabled={busy || !name.trim() || !scenarioSlug || !githubUrl.trim()}>
              {busy ? 'Saving…' : primary ? 'Update group details' : 'Save group details'}
            </button>
          </form>
        </section>

        {primary ? (
          <section className="surface">
            <h2>{primary.name}</h2>
            <p className="hint">
              Scenario: {primary.scenario_slug ?? '—'}
              {repoStatus ? ` · Repo ${repoStatus.index_status}` : ' · No repo yet'}
            </p>
            <div className="export-row" style={{ marginTop: 12 }}>
              <Link className="btn-primary" to={`/teams/${primary.id}/exit`}>
                {setupReady ? 'Start exit interview' : 'Open interview'}
              </Link>
              {admin ? (
                <Link to={`/admin/teams/${primary.id}/repository`}>Repository tools</Link>
              ) : null}
            </div>
          </section>
        ) : null}

        {admin && teams.length > 1 ? (
          <section className="surface">
            <h2>All teams</h2>
            <ul className="team-list">
              {teams.map((team) => (
                <li key={team.id}>
                  <strong>{team.name}</strong>
                  <span>{team.scenario_slug ?? 'no scenario'}</span>
                  <span className="team-actions">
                    <Link to={`/teams/${team.id}/exit`}>Exit interview</Link>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </CourseShell>
  )
}
