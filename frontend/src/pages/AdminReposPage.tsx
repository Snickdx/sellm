import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import {
  analyzeRepository,
  fetchRepositoryStatus,
  listTeamRepositories,
  searchRepository,
  submitRepository,
  type RepositorySubmission,
  type SearchHit,
} from '../api/client'
import { CourseShell } from '../components/CourseShell'
import { useAuth } from '../auth'

export function AdminReposPage() {
  const { teamId } = useParams()
  const { user, loading } = useAuth()
  const [rows, setRows] = useState<RepositorySubmission[]>([])
  const [active, setActive] = useState<RepositorySubmission | null>(null)
  const [url, setUrl] = useState('fixture://demo')
  const [sha, setSha] = useState('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
  const [branch, setBranch] = useState('main')
  const [query, setQuery] = useState('BookingService')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function refresh() {
    if (!teamId) return
    const list = await listTeamRepositories(teamId)
    setRows(list)
    if (active) {
      const latest = list.find((r) => r.id === active.id)
      if (latest) setActive(latest)
    } else if (list[0]) {
      setActive(list[0])
    }
  }

  useEffect(() => {
    if (!user || !teamId) return
    void refresh().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : 'Failed to load repositories'),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, teamId])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />
  if (!teamId) return <Navigate to="/" replace />

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const row = await submitRepository(teamId!, {
        github_url: url,
        commit_sha: sha,
        branch: branch || undefined,
      })
      setActive(row)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submit failed')
    } finally {
      setBusy(false)
    }
  }

  async function onAnalyze() {
    if (!active) return
    setBusy(true)
    setError(null)
    try {
      const row = await analyzeRepository(active.id)
      setActive(row)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analyze failed')
    } finally {
      setBusy(false)
    }
  }

  async function onRefreshStatus() {
    if (!active) return
    const row = await fetchRepositoryStatus(active.id)
    setActive(row)
    await refresh()
  }

  async function onSearch(event: FormEvent) {
    event.preventDefault()
    if (!active || active.index_status !== 'ready') return
    setBusy(true)
    setError(null)
    try {
      setHits(await searchRepository(active.id, query))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setBusy(false)
    }
  }

  const aside = (
    <>
      <h2 style={{ margin: '0 0 8px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#475569' }}>
        Snapshots
      </h2>
      <ul className="session-list">
        {rows.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              className={active?.id === row.id ? 'active ghost' : 'ghost'}
              onClick={() => setActive(row)}
            >
              {row.repo}@{row.commit_sha.slice(0, 7)}
              <span>
                {row.index_status}
                {row.index_error ? ` · ${row.index_error}` : ''}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {active && (
        <div className="export-row" style={{ marginTop: 10 }}>
          <button type="button" className="ghost" disabled={busy} onClick={() => void onAnalyze()}>
            Retry
          </button>
          <button type="button" className="ghost" onClick={() => void onRefreshStatus()}>
            Refresh
          </button>
        </div>
      )}
      <p className="hint" style={{ marginTop: 12 }}>
        <Link to={`/teams/${teamId}/exit`}>Exit interview</Link>
      </p>
    </>
  )

  return (
    <CourseShell
      title="Repository snapshot"
      subtitle={`Team ${teamId.slice(0, 8)} · freeze GitHub or fixture://demo`}
      aside={aside}
    >
      <div className="stack">
        {error && <p className="error">{error}</p>}

        <section className="surface">
          <h2>Submit</h2>
          <form className="auth-form" onSubmit={onSubmit}>
            <div className="form-grid two">
              <label>
                GitHub URL
                <input value={url} onChange={(e) => setUrl(e.target.value)} required />
              </label>
              <label>
                Commit SHA
                <input value={sha} onChange={(e) => setSha(e.target.value)} required />
              </label>
            </div>
            <label>
              Branch (optional)
              <input value={branch} onChange={(e) => setBranch(e.target.value)} />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? 'Working…' : 'Submit & analyze'}
            </button>
          </form>
        </section>

        <section className="surface">
          <h2>Summary</h2>
          {!active ? (
            <p className="hint">Submit a repository to inspect citations.</p>
          ) : (
            <>
              <p className="muted-row">
                <code>{active.github_url}</code>
                <code>{active.commit_sha.slice(0, 12)}</code>
                <span>{active.index_status}</span>
              </p>
              {active.summary && (
                <ul className="team-list" style={{ marginTop: 12 }}>
                  {(active.summary.citations as Array<Record<string, unknown>> | undefined)?.map(
                    (c, i) => (
                      <li key={i}>
                        <strong>{String(c.kind)}</strong>
                        <span>
                          <code>{String(c.path)}</code> · sha{' '}
                          <code>{String(c.sha).slice(0, 7)}</code>
                        </span>
                      </li>
                    ),
                  )}
                </ul>
              )}
              {active.index_status === 'ready' && (
                <form
                  className="form-grid two"
                  onSubmit={onSearch}
                  style={{ marginTop: 12, alignItems: 'end' }}
                >
                  <label>
                    Search code
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="BookingService"
                    />
                  </label>
                  <button type="submit" disabled={busy}>
                    Search
                  </button>
                </form>
              )}
              {hits.length > 0 && (
                <ul className="team-list" style={{ marginTop: 12 }}>
                  {hits.map((hit, i) => (
                    <li key={`${hit.path}-${hit.line}-${i}`}>
                      <strong>
                        {hit.path}:{hit.line}
                      </strong>
                      <pre className="code-excerpt">{hit.excerpt}</pre>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      </div>
    </CourseShell>
  )
}
