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

  if (loading) return <main className="page"><p>Loading…</p></main>
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

  return (
    <main className="page">
      <p className="eyebrow">Team</p>
      <h1>Repository snapshot</h1>
      <p className="lede">
        Freeze a GitHub URL + immutable commit SHA for team <code>{teamId}</code>. Use{' '}
        <code>fixture://demo</code> offline.
      </p>
      <Link to="/">Back</Link>
      {error && <p className="error">{error}</p>}

      <section className="panel">
        <h2>Submit</h2>
        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            GitHub URL
            <input value={url} onChange={(e) => setUrl(e.target.value)} required />
          </label>
          <label>
            Commit SHA
            <input value={sha} onChange={(e) => setSha(e.target.value)} required />
          </label>
          <label>
            Branch (optional)
            <input value={branch} onChange={(e) => setBranch(e.target.value)} />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? 'Working…' : 'Submit & analyze'}
          </button>
        </form>
      </section>

      <div className="interview-layout">
        <aside className="panel session-rail">
          <h2>Snapshots</h2>
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
            <div className="export-row">
              <button type="button" className="ghost" disabled={busy} onClick={() => void onAnalyze()}>
                Retry analyze
              </button>
              <button type="button" className="ghost" onClick={() => void onRefreshStatus()}>
                Refresh
              </button>
            </div>
          )}
        </aside>

        <section className="panel">
          <h2>Summary</h2>
          {!active ? (
            <p className="hint">Submit a repository to inspect citations.</p>
          ) : (
            <>
              <p>
                <code>{active.github_url}</code> · <code>{active.commit_sha}</code> ·{' '}
                {active.index_status}
              </p>
              {active.summary && (
                <>
                  <h3>Citations</h3>
                  <ul>
                    {(active.summary.citations as Array<Record<string, unknown>> | undefined)?.map(
                      (c, i) => (
                        <li key={i}>
                          {String(c.kind)} · <code>{String(c.path)}</code> · sha{' '}
                          <code>{String(c.sha).slice(0, 7)}</code>
                        </li>
                      ),
                    )}
                  </ul>
                </>
              )}
              {active.index_status === 'ready' && (
                <form className="inline-form" onSubmit={onSearch}>
                  <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="search code" />
                  <button type="submit" disabled={busy}>
                    Search
                  </button>
                </form>
              )}
              {hits.length > 0 && (
                <ul className="team-list">
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
    </main>
  )
}
