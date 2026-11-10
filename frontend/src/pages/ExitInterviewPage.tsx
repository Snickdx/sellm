import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import {
  consentExitSession,
  createExitSession,
  fetchExitSession,
  fetchPolicy,
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
import { CourseShell } from '../components/CourseShell'
import { VoiceRoomPanel } from '../components/VoiceRoomPanel'
import { useAuth } from '../auth'

function parseNames(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

export function ExitInterviewPage() {
  const { teamId } = useParams()
  const { user, loading } = useAuth()
  const [session, setSession] = useState<ExitSession | null>(null)
  const [sessions, setSessions] = useState<Array<{ id: string; status: string }>>([])
  const [repos, setRepos] = useState<RepositorySubmission[]>([])
  const [selectedRepoId, setSelectedRepoId] = useState('')
  const [participantNames, setParticipantNames] = useState('')
  const [answer, setAnswer] = useState('')
  const [probePrompt, setProbePrompt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<unknown>(null)
  const [policy, setPolicy] = useState<PolicyDoc | null>(null)

  const names = useMemo(() => parseNames(participantNames), [participantNames])

  const currentQuestion = useMemo(() => {
    if (!session?.current_question_id) return null
    return session.questions.find((q) => q.id === session.current_question_id) ?? null
  }, [session])

  const canAnswer =
    !!session &&
    (session.status === 'question' || session.status === 'optional_probe') &&
    !!session.current_question_id

  async function refreshList() {
    if (!teamId) return
    setSessions(await listTeamExitSessions(teamId))
  }

  useEffect(() => {
    void fetchPolicy().then(setPolicy).catch(() => setPolicy(null))
  }, [])

  useEffect(() => {
    if (!user || !teamId) return
    void (async () => {
      try {
        const exitSessions = await listTeamExitSessions(teamId)
        setSessions(exitSessions)
        if (exitSessions[0]) setSession(await fetchExitSession(exitSessions[0].id))
        const r = await listTeamRepositories(teamId)
        setRepos(r.filter((x) => x.index_status === 'ready'))
        if (r[0]) setSelectedRepoId(r[0].id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load')
      }
    })()
  }, [user, teamId])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />
  if (!teamId) return <Navigate to="/" replace />

  async function onCreate(event: FormEvent) {
    event.preventDefault()
    if (!teamId || !selectedRepoId || names.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const created = await createExitSession(teamId, {
        repository_submission_id: selectedRepoId,
        participant_names: names,
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

  const aside = (
    <>
      <h2 style={{ margin: '0 0 8px', fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#475569' }}>
        Sessions
      </h2>
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
      <p className="hint" style={{ marginTop: 12 }}>
        <Link to={`/admin/teams/${teamId}/repository`}>Repository</Link>
      </p>
    </>
  )

  return (
    <CourseShell
      title="Technical examiner"
      subtitle={`Team ${teamId.slice(0, 8)} · shared login${session ? ` · ${session.status}` : ''}`}
      aside={aside}
    >
      <div className="stack">
        {error && <p className="error">{error}</p>}

        <section className="surface">
          <h2>Create session</h2>
          <p className="hint" style={{ marginBottom: 12 }}>
            Freeze a repo first, then type each teammate’s real name (one per line). Same cohort
            login for everyone.
          </p>
          <form className="auth-form" onSubmit={onCreate}>
            <div className="form-grid two">
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
              <label>
                Participant names
                <textarea
                  value={participantNames}
                  onChange={(e) => setParticipantNames(e.target.value)}
                  rows={3}
                  placeholder={'Alex Rivera\nJordan Lee'}
                  required
                />
              </label>
            </div>
            <button type="submit" disabled={busy || !selectedRepoId || names.length === 0}>
              Create exit interview
            </button>
          </form>
        </section>

        {!session ? (
          <p className="hint">Select or create a session to continue.</p>
        ) : (
          <section className="surface">
            <h2>Live session</h2>
            {policy && (
              <aside className="consent-box hint" style={{ marginBottom: 12 }}>
                <strong>{policy.consent.title}</strong>
                <p style={{ margin: '4px 0 0' }}>{policy.consent.summary}</p>
              </aside>
            )}

            <div className="export-row" style={{ marginBottom: 12 }}>
              <button type="button" className="ghost" disabled={busy} onClick={() => void onConsent()}>
                Give consent (all)
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

            <p className="muted-row">
              <span>Consent: {session.consent_status}</span>
              <span>Current: {session.current_participant_name ?? '—'}</span>
            </p>

            {currentQuestion && (
              <article className="bubble persona" style={{ marginTop: 12 }}>
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

            {canAnswer && (
              <form className="chat-compose" onSubmit={onAnswer} style={{ marginTop: 12 }}>
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  rows={4}
                  placeholder={
                    session.current_participant_name
                      ? `Answer as ${session.current_participant_name}…`
                      : 'Type your answer…'
                  }
                  required
                  disabled={busy}
                />
                <button type="submit" disabled={busy || !answer.trim()}>
                  {session.status === 'optional_probe' ? 'Submit probe' : 'Submit answer'}
                </button>
              </form>
            )}

            <div style={{ marginTop: 16 }}>
              <VoiceRoomPanel
                sessionId={session.id}
                canRecord
                consentGranted={session.consent_status === 'granted'}
              />
            </div>

            <h3 style={{ marginTop: 16 }}>Participants</h3>
            <ul className="team-list">
              {session.participants.map((p) => (
                <li key={p.user_id}>
                  <strong>{p.display_name ?? `Participant ${p.turn_order + 1}`}</strong>
                  <span>
                    consent {p.consent_status} · turn {p.turn_order}
                  </span>
                </li>
              ))}
            </ul>

            {report != null && (
              <>
                <h3 style={{ marginTop: 16 }}>Provisional reports</h3>
                <pre className="code-excerpt">{JSON.stringify(report, null, 2)}</pre>
              </>
            )}
          </section>
        )}
      </div>
    </CourseShell>
  )
}
