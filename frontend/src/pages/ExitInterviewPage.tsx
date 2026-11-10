import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import {
  consentExitSession,
  createExitSession,
  fetchExitSession,
  fetchMyTeams,
  fetchPolicy,
  fetchTeamDetail,
  finishExitSession,
  listTeamExitSessions,
  listTeamRepositories,
  nextExitQuestion,
  setupMyGroup,
  startExitSession,
  submitExitAnswer,
  submitProbeAnswer,
  type ExitSession,
  type ExitSessionSummary,
  type PolicyDoc,
  type RepositorySubmission,
  type Team,
} from '../api/client'
import { CourseShell } from '../components/CourseShell'
import { VoiceRoomPanel } from '../components/VoiceRoomPanel'
import { useAuth } from '../auth'

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export function ExitInterviewPage() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const { user, loading } = useAuth()

  const [allTeams, setAllTeams] = useState<Team[]>([])
  const [team, setTeam] = useState<Team | null>(null)
  const [repo, setRepo] = useState<RepositorySubmission | null>(null)
  const [groupName, setGroupName] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [intervieweeName, setIntervieweeName] = useState('')
  const [sessions, setSessions] = useState<ExitSessionSummary[]>([])
  const [session, setSession] = useState<ExitSession | null>(null)
  const [answer, setAnswer] = useState('')
  const [probePrompt, setProbePrompt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<unknown>(null)
  const [policy, setPolicy] = useState<PolicyDoc | null>(null)
  const [settingsHint, setSettingsHint] = useState<string | null>(null)

  const repoReady = repo?.index_status === 'ready'
  const currentQuestion = useMemo(() => {
    if (!session?.current_question_id) return null
    return session.questions.find((q) => q.id === session.current_question_id) ?? null
  }, [session])

  const canAnswer =
    !!session &&
    (session.status === 'question' || session.status === 'optional_probe') &&
    !!session.current_question_id

  async function refreshHub() {
    if (!teamId) return
    const [detail, repos, exitSessions] = await Promise.all([
      fetchTeamDetail(teamId),
      listTeamRepositories(teamId),
      listTeamExitSessions(teamId),
    ])
    setTeam(detail)
    setGroupName(detail.name || '')
    const latest = repos[0] ?? null
    setRepo(latest)
    if (latest) setGithubUrl(latest.github_url)
    setSessions(exitSessions)
  }

  useEffect(() => {
    void fetchPolicy().then(setPolicy).catch(() => setPolicy(null))
  }, [])

  useEffect(() => {
    if (!user) return
    void fetchMyTeams()
      .then(setAllTeams)
      .catch(() => setAllTeams([]))
  }, [user])

  useEffect(() => {
    if (!user || !teamId) return
    setSession(null)
    setReport(null)
    void refreshHub().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : 'Failed to load'),
    )
  }, [user, teamId])

  if (loading) return <main className="page-fallback">Loading…</main>
  if (!user) return <Navigate to="/login" replace />
  if (!teamId) return <Navigate to="/" replace />

  async function onSaveSettings(event: FormEvent) {
    event.preventDefault()
    if (!teamId || !groupName.trim() || !githubUrl.trim()) return
    setBusy(true)
    setError(null)
    setSettingsHint(null)
    try {
      const result = await setupMyGroup({
        team_id: teamId,
        name: groupName.trim(),
        github_url: githubUrl.trim(),
        scenario_slug: team?.scenario_slug || undefined,
      })
      setTeam(result.team)
      setRepo(result.repository)
      setSettingsHint(
        result.repository.index_status === 'ready'
          ? 'Group settings saved. Repository is ready.'
          : 'Group settings saved. Repository is indexing…',
      )
      await refreshHub()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function onStartInterview(event: FormEvent) {
    event.preventDefault()
    if (!teamId || !intervieweeName.trim()) return
    setBusy(true)
    setError(null)
    try {
      const created = await createExitSession(teamId, {
        participant_names: [intervieweeName.trim()],
        questions_per_student: 3,
      })
      setSession(created)
      setReport(null)
      setProbePrompt(null)
      setIntervieweeName('')
      await refreshHub()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Start failed')
    } finally {
      setBusy(false)
    }
  }

  async function openPast(id: string) {
    setBusy(true)
    setError(null)
    try {
      setSession(await fetchExitSession(id))
      setReport(null)
      setProbePrompt(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open interview')
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
      await refreshHub()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Finish failed')
    } finally {
      setBusy(false)
    }
  }

  const hub = (
    <div className="stack">
      {allTeams.length > 1 ? (
        <label className="auth-form" style={{ marginBottom: 0 }}>
          Group
          <select
            value={teamId}
            onChange={(e) => {
              navigate(`/teams/${e.target.value}/exit`)
            }}
          >
            {allTeams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <section className="surface">
        <h2>Group settings</h2>
        <p className="hint" style={{ marginBottom: 12 }}>
          Set the group name and repository URL. No commit hash needed.
        </p>
        <form className="auth-form" onSubmit={onSaveSettings}>
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
          {repo ? (
            <p className="muted-row">
              <span>
                {repo.repo}
                {repo.commit_sha ? `@${repo.commit_sha.slice(0, 7)}` : ''}
              </span>
              <span>{repo.index_status}</span>
              {repo.index_error ? <span className="error">{repo.index_error}</span> : null}
            </p>
          ) : null}
          {settingsHint ? <p className="hint">{settingsHint}</p> : null}
          <button type="submit" disabled={busy || !groupName.trim() || !githubUrl.trim()}>
            {busy ? 'Saving…' : 'Save group settings'}
          </button>
        </form>
      </section>

      <section className="surface">
        <h2>New interview</h2>
        <p className="hint" style={{ marginBottom: 12 }}>
          Enter the interviewee’s group member name, then start.
        </p>
        <form className="auth-form" onSubmit={onStartInterview}>
          <label>
            Interviewee name
            <input
              value={intervieweeName}
              onChange={(e) => setIntervieweeName(e.target.value)}
              placeholder="Alex Rivera"
              required
            />
          </label>
          <button type="submit" disabled={busy || !repoReady || !intervieweeName.trim()}>
            {busy ? 'Starting…' : 'Start new interview'}
          </button>
          {!repoReady ? (
            <p className="hint">Save group settings and wait until the repository is ready.</p>
          ) : null}
        </form>
      </section>

      <section className="surface">
        <h2>Past interviews</h2>
        {sessions.length === 0 ? (
          <p className="hint">No interviews yet.</p>
        ) : (
          <ul className="team-list">
            {sessions.map((s) => (
              <li key={s.id}>
                <strong>{(s.participant_names || []).join(', ') || s.id.slice(0, 8)}</strong>
                <span>
                  {s.status}
                  {s.created_at ? ` · ${formatWhen(s.created_at)}` : ''}
                </span>
                <span className="team-actions">
                  <button type="button" className="ghost" disabled={busy} onClick={() => void openPast(s.id)}>
                    Open
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )

  const live = session ? (
    <section className="surface">
      <div className="export-row" style={{ marginBottom: 12 }}>
        <button type="button" className="ghost" onClick={() => setSession(null)}>
          ← Back to group
        </button>
      </div>
      <h2>Live interview</h2>
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
        <span>Interviewee: {session.current_participant_name ?? session.participants[0]?.display_name ?? '—'}</span>
        <span>{session.status}</span>
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
  ) : null

  return (
    <CourseShell
      title="Exit interviews"
      subtitle={
        team?.name
          ? `${team.name}${repoReady ? '' : ' · repo not ready'}`
          : 'Group settings, start interview, past sessions'
      }
    >
      <div className="stack">
        {error && <p className="error">{error}</p>}
        {session ? live : hub}
      </div>
    </CourseShell>
  )
}
