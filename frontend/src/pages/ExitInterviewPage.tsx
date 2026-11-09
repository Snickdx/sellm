import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import {
  consentExitSession,
  createExitSession,
  fetchExitSession,
  fetchPolicy,
  fetchTeamDetail,
  finishExitSession,
  listTeamExitSessions,
  listTeamRepositories,
  nextExitQuestion,
  startExitSession,
  submitExitAnswer,
  submitProbeAnswer,
  type ExitSession,
  type PolicyDoc,
  type RepositorySubmission,
} from '../api/client'
import { VoiceRoomPanel } from '../components/VoiceRoomPanel'
import { useAuth } from '../auth'

function formatUserId(id: number): string {
  return String(id)
}

export function ExitInterviewPage() {
  const { teamId } = useParams()
  const { user, loading } = useAuth()
  const [session, setSession] = useState<ExitSession | null>(null)
  const [sessions, setSessions] = useState<Array<{ id: string; status: string }>>([])
  const [repos, setRepos] = useState<RepositorySubmission[]>([])
  const [members, setMembers] = useState<Array<{ id: number; display_name: string }>>([])
  const [selectedRepoId, setSelectedRepoId] = useState('')
  const [selectedMemberIds, setSelectedMemberIds] = useState<number[]>([])
  const [answer, setAnswer] = useState('')
  const [probePrompt, setProbePrompt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<unknown>(null)
  const [policy, setPolicy] = useState<PolicyDoc | null>(null)

  const currentQuestion = useMemo(() => {
    if (!session?.current_question_id) return null
    return session.questions.find((q) => q.id === session.current_question_id) ?? null
  }, [session])

  const isMyTurn =
    !!user &&
    !!session &&
    session.current_participant_user_id === user.id &&
    (session.status === 'question' || session.status === 'optional_probe')

  async function refreshList() {
    if (!teamId) return
    const rows = await listTeamExitSessions(teamId)
    setSessions(rows)
  }

  useEffect(() => {
    void fetchPolicy().then(setPolicy).catch(() => setPolicy(null))
  }, [])

  useEffect(() => {
    if (!user || !teamId) return
    void (async () => {
      try {
        const [team, exitSessions] = await Promise.all([
          fetchTeamDetail(teamId),
          listTeamExitSessions(teamId),
        ])
        setMembers(
          team.members.map((m) => ({
            id: m.user_id,
            display_name: m.display_name || m.username || String(m.user_id),
          })),
        )
        setSelectedMemberIds(team.members.map((m) => m.user_id))
        setSessions(exitSessions)
        if (exitSessions[0]) {
          setSession(await fetchExitSession(exitSessions[0].id))
        }
        const r = await listTeamRepositories(teamId)
        setRepos(r.filter((x) => x.index_status === 'ready'))
        if (r[0]) setSelectedRepoId(r[0].id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load')
      }
    })()
  }, [user, teamId])

  if (loading) return <main className="page"><p>Loading…</p></main>
  if (!user) return <Navigate to="/login" replace />
  if (!teamId) return <Navigate to="/" replace />

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    if (!teamId || !selectedRepoId || selectedMemberIds.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const created = await createExitSession(teamId, {
        repository_submission_id: selectedRepoId,
        participant_user_ids: selectedMemberIds,
        questions_per_student: 3,
      })
      setSession(created)
      await refreshList()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  async function onConsent() {
    if (!session) return
    setBusy(true)
    try {
      setSession(await consentExitSession(session.id, true))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Consent failed')
    } finally {
      setBusy(false)
    }
  }

  async function onStart() {
    if (!session) return
    setBusy(true)
    try {
      setSession(await startExitSession(session.id))
      setProbePrompt(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Start failed')
    } finally {
      setBusy(false)
    }
  }

  async function onNext() {
    if (!session) return
    setBusy(true)
    try {
      setSession(await nextExitQuestion(session.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Next failed')
    } finally {
      setBusy(false)
    }
  }

  async function onAnswer(event: FormEvent) {
    event.preventDefault()
    if (!session || !answer.trim()) return
    setBusy(true)
    setError(null)
    try {
      if (session.status === 'optional_probe') {
        setSession(await submitProbeAnswer(session.id, answer.trim()))
        setProbePrompt(null)
      } else {
        const result = await submitExitAnswer(session.id, answer.trim(), false)
        setSession(result)
        setProbePrompt(result.probe_prompt ?? null)
      }
      setAnswer('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Answer failed')
    } finally {
      setBusy(false)
    }
  }

  async function onFinish() {
    if (!session) return
    setBusy(true)
    try {
      const result = await finishExitSession(session.id)
      setSession(result.session)
      setReport(result.reports)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Finish failed')
    } finally {
      setBusy(false)
    }
  }

  function toggleMember(id: number) {
    setSelectedMemberIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  return (
    <main className="page interview-page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Exit interview</p>
          <h1>Technical examiner</h1>
          <p className="lede">
            Team <code>{teamId}</code>
            {session ? ` · ${session.status}` : ''}
          </p>
        </div>
        <Link to="/">Back</Link>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="panel">
        <h2>Create session</h2>
        <p className="hint">
          Freeze a repo first on the{' '}
          <Link to={`/admin/teams/${teamId}/repository`}>repository page</Link>, then start here.
        </p>
        <form className="auth-form" onSubmit={onCreate}>
          <label>
            Frozen repository
            <select
              value={selectedRepoId}
              onChange={(e) => setSelectedRepoId(e.target.value)}
              required
            >
              <option value="">Select…</option>
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.repo}@{r.commit_sha.slice(0, 7)}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Participants</legend>
            {members.map((m) => (
              <label key={m.id} className="check-row">
                <input
                  type="checkbox"
                  checked={selectedMemberIds.includes(m.id)}
                  onChange={() => toggleMember(m.id)}
                />{' '}
                {m.display_name}
              </label>
            ))}
          </fieldset>
          <button type="submit" disabled={busy || !selectedRepoId || selectedMemberIds.length === 0}>
            Create exit interview
          </button>
        </form>
      </section>

      <div className="interview-layout">
        <aside className="panel session-rail">
          <h2>Sessions</h2>
          <ul className="session-list">
            {sessions.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={session?.id === s.id ? 'active ghost' : 'ghost'}
                  onClick={() => {
                    void fetchExitSession(s.id).then(setSession)
                    setReport(null)
                  }}
                >
                  {s.id.slice(0, 8)}
                  <span>{s.status}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="panel chat-panel">
          {!session ? (
            <p className="hint">No exit session selected.</p>
          ) : (
            <>
              <h2>Session controls</h2>
              {policy && (
                <aside className="hint consent-box">
                  <strong>{policy.consent.title}</strong>
                  <p>{policy.consent.summary}</p>
                  <p>
                    Retention: transcripts ≈ {policy.retention.transcript_days} days; recordings ≈{' '}
                    {policy.retention.recording_days} days. <Link to="/policy">Full policy</Link>
                  </p>
                </aside>
              )}
              <div className="export-row">
                <button type="button" className="ghost" disabled={busy} onClick={() => void onConsent()}>
                  Give consent
                </button>
                <button type="button" className="ghost" disabled={busy} onClick={() => void onStart()}>
                  Start
                </button>
                <button type="button" className="ghost" disabled={busy} onClick={() => void onNext()}>
                  Next question
                </button>
                <button type="button" disabled={busy} onClick={() => void onFinish()}>
                  Finish &amp; score
                </button>
              </div>

              <p className="hint">
                Consent: {session.consent_status} · Current student:{' '}
                {session.current_participant_user_id != null
                  ? formatUserId(session.current_participant_user_id)
                  : '—'}
              </p>

              {currentQuestion && (
                <article className="bubble persona">
                  <header>
                    {currentQuestion.competency} · {currentQuestion.difficulty}
                    {currentQuestion.hypothetical ? ' · hypothetical' : ''}
                  </header>
                  <p>{currentQuestion.prompt}</p>
                  {currentQuestion.code_refs?.path ? (
                    <footer>
                      {String(currentQuestion.code_refs.path)}
                      {Array.isArray(currentQuestion.code_refs.line_range)
                        ? `:${String(currentQuestion.code_refs.line_range[0])}-${String(currentQuestion.code_refs.line_range[1])}`
                        : ''}{' '}
                      @ {String(currentQuestion.code_refs.sha || '').slice(0, 7)}
                    </footer>
                  ) : null}
                </article>
              )}

              {probePrompt && <p className="hint">Probe: {probePrompt}</p>}

              {isMyTurn && (
                <form className="chat-compose" onSubmit={onAnswer}>
                  <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    rows={4}
                    placeholder="Type your answer…"
                    required
                    disabled={busy}
                  />
                  <button type="submit" disabled={busy || !answer.trim()}>
                    {session.status === 'optional_probe' ? 'Submit probe' : 'Submit answer'}
                  </button>
                </form>
              )}

              <VoiceRoomPanel
                sessionId={session.id}
                canRecord
                consentGranted={session.consent_status === 'granted'}
              />

              {!isMyTurn && session.status === 'question' && (
                <p className="hint">Waiting for the assigned student to answer.</p>
              )}

              <h3>Plan coverage</h3>
              <ul className="team-list">
                {session.participants.map((p) => (
                  <li key={p.user_id}>
                    <strong>{p.display_name ?? formatUserId(p.user_id)}</strong>
                    <span>
                      consent {p.consent_status} · turn {p.turn_order}
                    </span>
                  </li>
                ))}
              </ul>

              {report != null && (
                <>
                  <h3>Provisional reports</h3>
                  <pre className="code-excerpt">{JSON.stringify(report, null, 2)}</pre>
                </>
              )}
            </>
          )}
        </section>
      </div>
    </main>
  )
}
