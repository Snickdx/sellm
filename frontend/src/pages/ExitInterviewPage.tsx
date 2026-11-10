import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Navigate, useParams } from 'react-router-dom'
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
} from '../api/client'
import { CourseShell } from '../components/CourseShell'
import { VoiceRoomPanel } from '../components/VoiceRoomPanel'
import { useAuth } from '../auth'

export function ExitInterviewPage() {
  const { teamId } = useParams()
  const { user, loading } = useAuth()
  const [session, setSession] = useState<ExitSession | null>(null)
  const [sessions, setSessions] = useState<Array<{ id: string; status: string }>>([])
  const [ready, setReady] = useState(false)
  const [setupHint, setSetupHint] = useState('Checking team…')
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
        const repos = await listTeamRepositories(teamId)
        const repo = repos.find((x) => x.index_status === 'ready')
        if (repo) {
          setReady(true)
          setSetupHint('Ready to start')
        } else if (repos.some((x) => x.index_status === 'pending' || x.index_status === 'running')) {
          setReady(false)
          setSetupHint('Repository is still indexing — ask your instructor if this takes too long.')
        } else {
          setReady(false)
          setSetupHint('Team is not ready yet. Instructor must finish setup in Admin → Teams.')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load')
      }
    })()
  }, [user, teamId])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />
  if (!teamId) return <Navigate to="/" replace />

  async function onCreate() {
    if (!teamId) return
    setBusy(true)
    setError(null)
    try {
      const created = await createExitSession(teamId, { questions_per_student: 3 })
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

  const aside =
    sessions.length > 0 ? (
      <>
        <h2
          style={{
            margin: '0 0 8px',
            fontSize: 13,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: '#475569',
          }}
        >
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
      </>
    ) : null

  return (
    <CourseShell
      title="Exit interview"
      subtitle={session ? session.status : setupHint}
      aside={aside}
    >
      <div className="stack">
        {error && <p className="error">{error}</p>}

        {!session ? (
          <section className="surface">
            <h2>Start</h2>
            <p className="hint" style={{ marginBottom: 12 }}>
              Member names and repository come from Admin. Consent, then answer questions for each
              teammate in turn.
            </p>
            <button type="button" disabled={busy || !ready} onClick={() => void onCreate()}>
              {busy ? 'Starting…' : 'Start exit interview'}
            </button>
          </section>
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
                Give consent
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => void onStart()}>
                Begin questions
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
