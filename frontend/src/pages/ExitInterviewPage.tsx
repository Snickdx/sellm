import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import {
  canDeleteExitSession,
  consentExitSession,
  createExitSession,
  deleteExitSession,
  fetchExitReport,
  fetchExitSession,
  fetchMyTeams,
  fetchPolicy,
  fetchRecordingObjectUrl,
  fetchTeamDetail,
  fetchVoiceStatus,
  finishExitSession,
  listTeamExitSessions,
  listTeamRepositories,
  nextExitQuestion,
  setupMyGroup,
  startExitSession,
  submitExitAnswer,
  submitProbeAnswer,
  type CompetencyScore,
  type ExitReport,
  type ExitSession,
  type ExitSessionSummary,
  type PolicyDoc,
  type RepositorySubmission,
  type Team,
} from '../api/client'
import { CourseShell } from '../components/CourseShell'
import { VoiceRoomPanel, type VoiceRoomHandle } from '../components/VoiceRoomPanel'
import { useAuth } from '../auth'

type ExitTab = 'group' | 'hub' | 'live'

/** Scored / moderated — full review UI. */
const SCORED_STATUSES = new Set(['lecturer_review', 'finalized'])
/** Questions done; provisional audit not finished yet. */
const WRAP_STATUSES = new Set(['closing', 'processing'])

const STATUS_LABELS: Record<string, string> = {
  scheduled: 'Scheduled',
  consent: 'Awaiting consent',
  introductions: 'Starting',
  student_turn: 'In progress',
  question: 'In progress',
  optional_probe: 'In progress',
  response: 'In progress',
  evidence_recorded: 'In progress',
  next_student: 'In progress',
  closing: 'Closing — audit pending',
  processing: 'Audit in progress',
  lecturer_review: 'Completed',
  finalized: 'Finalized',
  paused: 'Paused',
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function formatStatus(status: string | undefined): string {
  if (!status) return '—'
  return STATUS_LABELS[status] ?? status.replace(/_/g, ' ')
}

function isInterviewScored(status: string | undefined): boolean {
  return !!status && SCORED_STATUSES.has(status)
}

function isWrappingUp(status: string | undefined): boolean {
  return !!status && WRAP_STATUSES.has(status)
}

/** Hub “past / viewable” — wrapping or scored. */
function isInterviewDone(status: string | undefined): boolean {
  return isInterviewScored(status) || isWrappingUp(status)
}

/** Spoken navigation command — do not append to the answer draft. */
function isNextCommand(text: string): boolean {
  const t = text.trim().toLowerCase().replace(/[.!,?]+$/g, '')
  return t === 'next' || t === 'next question' || t === 'go next'
}

const COMPETENCY_LABELS: Record<string, string> = {
  special_feature_pattern: 'Special-feature pattern',
  design_to_code: 'Design to code',
  feature_ownership: 'Feature ownership',
  testing: 'Testing',
  verification: 'Verification',
  // legacy plans
  requirements: 'Requirements',
  architecture: 'Architecture',
  code: 'Code',
  ai_engineering: 'AI engineering',
}

function formatCompetency(name: string): string {
  return COMPETENCY_LABELS[name] ?? name.replace(/_/g, ' ')
}

function competencyLine(scores: CompetencyScore[] | undefined): string {
  if (!scores?.length) return 'No scores yet'
  return scores
    .map((c) => `${formatCompetency(c.name)}: ${c.score == null ? '—' : `${c.score}/${c.max_score}`}`)
    .join(' · ')
}

function RecordingPlayer({ sessionId }: { sessionId: string }) {
  const [src, setSrc] = useState<string | null>(null)
  const [msg, setMsg] = useState('Loading recording…')

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    setSrc(null)
    setMsg('Loading recording…')

    void (async () => {
      try {
        const status = await fetchVoiceStatus(sessionId).catch(() => null)
        if (cancelled) return
        if (status?.recording_status === 'processing') {
          setMsg('Recording still processing — refresh in a moment.')
        }
        try {
          const url = await fetchRecordingObjectUrl(sessionId)
          if (cancelled) {
            URL.revokeObjectURL(url)
            return
          }
          objectUrl = url
          setSrc(url)
          setMsg('')
        } catch (err) {
          if (cancelled) return
          if (status?.recording_status === 'processing') {
            setMsg('Recording still processing — refresh in a moment.')
          } else if (status?.recording_status === 'ready') {
            setMsg('Recording marked ready but the file is missing on the server.')
          } else {
            setMsg(err instanceof Error ? err.message : 'No recording available')
          }
        }
      } catch (err) {
        if (!cancelled) setMsg(err instanceof Error ? err.message : 'No recording available')
      }
    })()

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [sessionId])

  if (!src) return <p className="hint">{msg}</p>
  return <video className="review-video" src={src} controls playsInline />
}

function ReportSummary({ report }: { report: ExitReport }) {
  if (report.assessments.length === 0) {
    return <p className="hint">No provisional assessment stored for this interview.</p>
  }
  return (
    <div className="report-summary">
      {report.assessments.map((a) => {
        const comps = a.provisional_scores?.competencies ?? []
        const warnings = a.evidence?.coverage_warnings ?? []
        return (
          <article key={a.id} className="report-card">
            <header>
              <strong>{a.display_name}</strong>
              <span>{a.provisional ? 'Provisional' : 'Final'} · {a.review_status}</span>
            </header>
            <p className="report-scores">{competencyLine(comps)}</p>
            {warnings.length > 0 ? (
              <ul className="report-warnings">
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}

function FormattedReport({ report }: { report: ExitReport }) {
  return (
    <div className="formatted-report">
      <div className="live-meta" style={{ marginBottom: 10 }}>
        <span>Session {report.session_id.slice(0, 8)}</span>
        <span>{formatStatus(report.status)}</span>
        {report.repository_sha ? <span>Repo @{report.repository_sha.slice(0, 7)}</span> : null}
      </div>
      {report.assessments.map((a) => {
        const comps = a.provisional_scores?.competencies ?? []
        return (
          <section key={a.id} className="report-section">
            <h3>
              {a.display_name}
              <span className="hint"> · {a.provisional ? 'provisional' : 'final'}</span>
            </h3>
            {comps.length === 0 ? <p className="hint">No competency scores.</p> : null}
            {comps.map((c) => (
              <article key={`${a.id}-${c.name}`} className="competency-block">
                <header>
                  <strong>{formatCompetency(c.name)}</strong>
                  <span>
                    {c.score == null ? 'Not scored' : `${c.score} / ${c.max_score}`}
                    {' · '}
                    {c.evidence_sufficiency}
                    {c.follow_up_recommended ? ' · follow-up recommended' : ''}
                  </span>
                </header>
                {c.rationale ? <p className="hint">{c.rationale}</p> : null}
                {c.evidence?.length ? (
                  <ul className="evidence-list">
                    {c.evidence.map((e) => (
                      <li key={e.answer_id}>
                        {e.repository_path ? (
                          <span className="hint">
                            {e.repository_path}
                            {Array.isArray(e.line_range)
                              ? `:${e.line_range[0]}-${e.line_range[1]}`
                              : ''}
                            {' — '}
                          </span>
                        ) : null}
                        {e.answer_excerpt || e.prompt || 'Evidence'}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
            {(a.evidence?.coverage_warnings ?? []).length > 0 ? (
              <ul className="report-warnings">
                {(a.evidence?.coverage_warnings ?? []).map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
            {a.reviewer_notes ? <p className="past-answer">Reviewer notes: {a.reviewer_notes}</p> : null}
          </section>
        )
      })}
    </div>
  )
}

export function ExitInterviewPage() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const { user, loading } = useAuth()

  const [tab, setTab] = useState<ExitTab>('hub')
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
  const [report, setReport] = useState<ExitReport | null>(null)
  const [hubReport, setHubReport] = useState<ExitReport | null>(null)
  const [policy, setPolicy] = useState<PolicyDoc | null>(null)
  const [settingsHint, setSettingsHint] = useState<string | null>(null)
  const [startModalOpen, setStartModalOpen] = useState(false)
  const [consentModalOpen, setConsentModalOpen] = useState(false)
  const [consentChecked, setConsentChecked] = useState(false)
  const [pendingSession, setPendingSession] = useState<ExitSession | null>(null)
  const [selectedPastId, setSelectedPastId] = useState<string | null>(null)
  const [pastDetail, setPastDetail] = useState<ExitSession | null>(null)
  const [viewIndex, setViewIndex] = useState(0)
  const videoRoomRef = useRef<VoiceRoomHandle | null>(null)
  const sttBaseRef = useRef('')
  const advancingRef = useRef(false)
  const finishingRef = useRef(false)

  const repoReady = repo?.index_status === 'ready'
  const interviewScored = isInterviewScored(session?.status)
  const wrappingUp = isWrappingUp(session?.status)
  const interviewDone = isInterviewDone(session?.status)
  const orderedQuestions = useMemo(() => {
    if (!session) return []
    return [...session.questions].sort((a, b) => a.sequence - b.sequence)
  }, [session])

  const currentQuestion = useMemo(() => {
    if (!session?.current_question_id) return null
    return session.questions.find((q) => q.id === session.current_question_id) ?? null
  }, [session])

  const viewedQuestion = orderedQuestions[viewIndex] ?? null
  const viewingCurrent =
    !!viewedQuestion && !!session?.current_question_id && viewedQuestion.id === session.current_question_id

  const canAnswer =
    !!session &&
    !interviewDone &&
    viewingCurrent &&
    (session.status === 'question' || session.status === 'optional_probe') &&
    !!session.current_question_id

  useEffect(() => {
    if (!session?.current_question_id || orderedQuestions.length === 0) return
    const idx = orderedQuestions.findIndex((q) => q.id === session.current_question_id)
    if (idx >= 0) setViewIndex(idx)
  }, [session?.current_question_id, orderedQuestions])

  async function refreshHub(preferSessionId?: string | null) {
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
    setSelectedPastId((current) => {
      const prefer = preferSessionId !== undefined ? preferSessionId : current
      if (exitSessions.length === 0) return null
      if (prefer && exitSessions.some((s) => s.id === prefer)) return prefer
      return exitSessions[0].id
    })
    if (exitSessions.length === 0) setPastDetail(null)
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
    setHubReport(null)
    setPastDetail(null)
    setSelectedPastId(null)
    setStartModalOpen(false)
    setConsentModalOpen(false)
    setConsentChecked(false)
    setPendingSession(null)
    setTab('hub')
    void refreshHub().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : 'Failed to load'),
    )
  }, [user, teamId])

  useEffect(() => {
    if (!selectedPastId) {
      setPastDetail(null)
      setHubReport(null)
      return
    }
    let cancelled = false
    setPastDetail(null)
    setHubReport(null)
    void fetchExitSession(selectedPastId)
      .then(async (detail) => {
        if (cancelled) return
        setPastDetail(detail)
        if (isInterviewScored(detail.status)) {
          try {
            const scored = await fetchExitReport(detail.id)
            if (!cancelled) setHubReport(scored)
          } catch {
            if (!cancelled) setHubReport(null)
          }
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load interview')
      })
    return () => {
      cancelled = true
    }
  }, [selectedPastId])

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

  function openConsentFor(detail: ExitSession) {
    setPendingSession(detail)
    setConsentChecked(detail.consent_status === 'granted')
    setConsentModalOpen(true)
    setReport(null)
    setProbePrompt(null)
  }

  async function beginLiveSession(detail: ExitSession) {
    let next = detail
    if (next.consent_status !== 'granted') {
      next = await consentExitSession(next.id, true)
    }
    if (
      !isInterviewDone(next.status) &&
      next.status !== 'question' &&
      next.status !== 'optional_probe'
    ) {
      next = await startExitSession(next.id)
    }
    setSession(next)
    setPastDetail(next)
    setSelectedPastId(next.id)
    setProbePrompt(null)
    setConsentModalOpen(false)
    setPendingSession(null)
    setConsentChecked(false)
    setTab('live')
    await refreshHub(next.id)
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
      setIntervieweeName('')
      setStartModalOpen(false)
      openConsentFor(created)
      await refreshHub(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Start failed')
    } finally {
      setBusy(false)
    }
  }

  async function openLive(id: string) {
    setBusy(true)
    setError(null)
    try {
      const detail = await fetchExitSession(id)
      setPastDetail(detail)
      setSelectedPastId(id)
      if (isInterviewScored(detail.status)) {
        setSession(detail)
        setViewIndex(0)
        try {
          setReport(await fetchExitReport(detail.id))
        } catch {
          setReport(null)
        }
        setTab('live')
        return
      }
      if (isWrappingUp(detail.status)) {
        setSession(detail)
        setReport(null)
        setViewIndex(0)
        setTab('live')
        return
      }
      if (detail.consent_status !== 'granted') {
        openConsentFor(detail)
        return
      }
      await beginLiveSession(detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open interview')
    } finally {
      setBusy(false)
    }
  }

  async function onConfirmConsent() {
    if (!pendingSession || !consentChecked) return
    setBusy(true)
    setError(null)
    try {
      await beginLiveSession(pendingSession)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start interview')
    } finally {
      setBusy(false)
    }
  }

  function onTranscript(text: string, isFinal: boolean) {
    if (isFinal && isNextCommand(text)) {
      // Drop any interim "next" that landed in the draft.
      setAnswer(sttBaseRef.current)
      void onVoiceNext()
      return
    }
    if (!isFinal && isNextCommand(text)) {
      setAnswer(sttBaseRef.current)
      return
    }
    if (isFinal) {
      sttBaseRef.current = `${sttBaseRef.current} ${text}`.trim()
      setAnswer(sttBaseRef.current)
      return
    }
    setAnswer(`${sttBaseRef.current} ${text}`.trim())
  }

  async function onVoiceNext() {
    if (!session || interviewDone || wrappingUp || advancingRef.current) return
    // Browsing a past question → move the view forward first.
    if (!viewingCurrent && viewIndex < orderedQuestions.length - 1) {
      setViewIndex((i) => Math.min(i + 1, orderedQuestions.length - 1))
      return
    }
    advancingRef.current = true
    setBusy(true)
    setError(null)
    try {
      const next = await nextExitQuestion(session.id)
      setSession(next)
      setProbePrompt(null)
      setAnswer('')
      sttBaseRef.current = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not advance')
    } finally {
      advancingRef.current = false
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
        setProbePrompt(null)
      }
      setAnswer('')
      sttBaseRef.current = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Answer failed')
    } finally {
      setBusy(false)
    }
  }

  async function onEndInterview() {
    if (!session || finishingRef.current) return
    finishingRef.current = true
    setBusy(true)
    setError(null)
    try {
      try {
        await videoRoomRef.current?.stopAndUpload()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not save video recording')
      }
      const result = await finishExitSession(session.id)
      try {
        setReport(await fetchExitReport(result.session.id))
      } catch {
        setReport(null)
      }
      setSession(result.session)
      setProbePrompt(null)
      await refreshHub(result.session.id)
      setTab('live')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Finish failed')
    } finally {
      finishingRef.current = false
      setBusy(false)
    }
  }

  // Questions exhausted → closing: run provisional audit automatically.
  useEffect(() => {
    if (!session || session.status !== 'closing' || busy || finishingRef.current) return
    if (tab !== 'live') return
    void onEndInterview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.id, session?.status, tab])

  async function onDeleteInterview(id: string) {
    const label =
      (sessions.find((s) => s.id === id)?.participant_names || []).join(', ') || 'this interview'
    if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return
    setBusy(true)
    setError(null)
    try {
      await deleteExitSession(id)
      if (session?.id === id) {
        setSession(null)
        setReport(null)
        setProbePrompt(null)
        setTab('hub')
      }
      if (selectedPastId === id) {
        setSelectedPastId(null)
        setPastDetail(null)
      }
      await refreshHub(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const tabs = [
    { id: 'group', label: 'Group' },
    { id: 'hub', label: 'Interviews' },
    ...(session ? [{ id: 'live', label: 'Live', disabled: true }] : []),
  ]

  const groupScreen = (
    <section className="surface">
      <h2>Group settings</h2>
      <p className="hint" style={{ marginBottom: 12 }}>
        Name and repository URL. No commit hash needed.
      </p>
      {allTeams.length > 1 ? (
        <label className="auth-form" style={{ marginBottom: 12 }}>
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
      <form className="auth-form" onSubmit={onSaveSettings}>
        <div className="form-grid two">
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
              placeholder="https://github.com/org/repo"
              required
            />
          </label>
        </div>
        {repo ? (
          <p className="muted-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
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
  )

  const selectedSummary = sessions.find((s) => s.id === selectedPastId) ?? null
  const canDeleteSelected = canDeleteExitSession(user, selectedSummary?.created_by_id)

  const hubScreen = (
    <>
      <div className="interview-hub">
        <section className="interview-hub-list" aria-label="Past interviews">
          <div className="interview-hub-list-header">Past interviews</div>
          {sessions.length === 0 ? (
            <p className="hint" style={{ padding: 14, margin: 0 }}>
              No interviews yet. Use Start interview.
            </p>
          ) : (
            sessions.map((s) => {
              const active = s.id === selectedPastId
              const label = (s.participant_names || []).join(', ') || s.id.slice(0, 8)
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`interview-hub-item${active ? ' active' : ''}`}
                  onClick={() => setSelectedPastId(s.id)}
                >
                  <strong>{label}</strong>
                  <span>
                    {formatStatus(s.status)}
                    {s.created_at ? ` · ${formatWhen(s.created_at)}` : ''}
                  </span>
                </button>
              )
            })
          )}
        </section>

        <section className="interview-hub-detail" aria-label="Interview details">
          {!selectedSummary ? (
            <p className="hint">Select an interview, or start a new one.</p>
          ) : (
            <div className="stack" style={{ maxWidth: 'none', gap: 12 }}>
              <div>
                <h2 style={{ marginBottom: 6 }}>
                  {(selectedSummary.participant_names || []).join(', ') || 'Interview'}
                </h2>
                <div className="live-meta">
                  <span>Status: {formatStatus(selectedSummary.status)}</span>
                  <span>Consent: {selectedSummary.consent_status}</span>
                  {selectedSummary.created_at ? (
                    <span>Started: {formatWhen(selectedSummary.created_at)}</span>
                  ) : null}
                </div>
              </div>

              {pastDetail ? (
                <>
                  <p className="hint" style={{ margin: 0 }}>
                    Questions: {pastDetail.questions.length} · Unanswered:{' '}
                    {pastDetail.unanswered_question_ids.length} · Interviewee:{' '}
                    {pastDetail.current_participant_name ??
                      pastDetail.participants[0]?.display_name ??
                      '—'}
                  </p>
                  {pastDetail.participants.length > 0 ? (
                    <ul className="consent-checklist">
                      {pastDetail.participants.map((p) => (
                        <li key={`${p.user_id}-${p.turn_order}`}>
                          {p.display_name || `User ${p.user_id}`} · consent {p.consent_status}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {isWrappingUp(selectedSummary.status) ? (
                    <p className="audit-banner" role="status">
                      Closing — provisional audit pending. Open to finish scoring.
                    </p>
                  ) : null}
                  {isInterviewScored(selectedSummary.status) ? (
                    <div>
                      <h3 style={{ margin: '8px 0 6px', fontSize: '0.95rem' }}>Provisional summary</h3>
                      {hubReport ? (
                        <ReportSummary report={hubReport} />
                      ) : (
                        <p className="hint">Loading report summary…</p>
                      )}
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="hint">Loading details…</p>
              )}

              <div className="live-actions">
                <button
                  type="button"
                  disabled={busy || !selectedPastId}
                  onClick={() => selectedPastId && void openLive(selectedPastId)}
                >
                  {isWrappingUp(selectedSummary.status)
                    ? 'Complete audit'
                    : isInterviewScored(selectedSummary.status)
                      ? 'View interview'
                      : 'Continue interview'}
                </button>
                {canDeleteSelected ? (
                  <button
                    type="button"
                    className="ghost danger"
                    disabled={busy || !selectedPastId}
                    onClick={() => selectedPastId && void onDeleteInterview(selectedPastId)}
                  >
                    Delete interview
                  </button>
                ) : null}
              </div>
            </div>
          )}
        </section>
      </div>

      <button
        type="button"
        className="fab-labeled"
        onClick={() => setStartModalOpen(true)}
      >
        + Start interview
      </button>

      {startModalOpen ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) setStartModalOpen(false)
          }}
        >
          <div
            className="modal-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="startInterviewTitle"
          >
            <div className="modal-header">
              <h3 id="startInterviewTitle">Start interview</h3>
              <button
                type="button"
                className="modal-close"
                aria-label="Close"
                onClick={() => setStartModalOpen(false)}
              >
                ×
              </button>
            </div>
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
                  autoFocus
                />
              </label>
              {!repoReady ? (
                <p className="hint">
                  Save group settings on the <strong>Group</strong> tab and wait until the repository is
                  ready.
                </p>
              ) : null}
              <div className="live-actions">
                <button type="submit" disabled={busy || !repoReady || !intervieweeName.trim()}>
                  {busy ? 'Starting…' : 'Start interview'}
                </button>
                <button type="button" className="ghost" onClick={() => setStartModalOpen(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  )

  const reviewScreen = session && interviewScored ? (
    <section className="surface live-interview review-interview">
      <div className="live-toolbar">
        <div>
          <h2 style={{ marginBottom: 6 }}>Interview review</h2>
          <div className="live-meta">
            <span>{formatStatus(session.status)}</span>
            <span>
              Interviewee:{' '}
              {session.current_participant_name ?? session.participants[0]?.display_name ?? '—'}
            </span>
            <span>
              {orderedQuestions.length} questions · {session.unanswered_question_ids.length} unanswered
            </span>
          </div>
        </div>
      </div>

      <div className="review-layout">
        <section className="review-panel">
          <h3>Recording</h3>
          <RecordingPlayer sessionId={session.id} />
        </section>

        <section className="review-panel">
          <h3>Provisional summary</h3>
          {report ? <ReportSummary report={report} /> : <p className="hint">No report available.</p>}
        </section>

        <section className="review-panel review-transcripts">
          <h3>Question & answer transcript</h3>
          {orderedQuestions.length === 0 ? (
            <p className="hint">No questions in this session.</p>
          ) : (
            orderedQuestions.map((q, idx) => (
              <article key={q.id} className="transcript-item">
                <header>
                  Q{idx + 1}. {formatCompetency(q.competency)} · {q.difficulty} · {q.status}
                </header>
                <p className="transcript-q">{q.prompt}</p>
                {q.code_refs?.path ? (
                  <p className="hint" style={{ margin: '4px 0 0' }}>
                    {String(q.code_refs.path)}
                    {Array.isArray(q.code_refs.line_range)
                      ? `:${String(q.code_refs.line_range[0])}-${String(q.code_refs.line_range[1])}`
                      : ''}
                  </p>
                ) : null}
                {q.answers.length > 0 ? (
                  q.answers.map((a) => (
                    <p key={a.id} className="past-answer">
                      {a.is_probe ? 'Probe: ' : 'Answer: '}
                      {a.text}
                    </p>
                  ))
                ) : (
                  <p className="hint">No answer recorded.</p>
                )}
              </article>
            ))
          )}
        </section>

        <section className="review-panel">
          <h3>Full report</h3>
          {report ? <FormattedReport report={report} /> : <p className="hint">No report available.</p>}
        </section>
      </div>
    </section>
  ) : null

  const liveScreen = session && !interviewScored ? (
    <section className="surface live-interview">
      <div className="live-toolbar">
        <div>
          <h2 style={{ marginBottom: 6 }}>
            {wrappingUp ? 'Closing interview' : 'Live interview'}
          </h2>
          <div className="live-meta">
            <span>Status: {formatStatus(session.status)}</span>
            <span>
              Interviewee:{' '}
              {session.current_participant_name ?? session.participants[0]?.display_name ?? '—'}
            </span>
            {!wrappingUp ? <span className="recording-pill">Recording</span> : null}
            {wrappingUp ? <span className="audit-pill">Audit</span> : null}
          </div>
        </div>
        <button type="button" disabled={busy} onClick={() => void onEndInterview()}>
          {busy || session.status === 'processing'
            ? 'Running audit…'
            : wrappingUp
              ? 'Complete audit'
              : 'End interview'}
        </button>
      </div>

      {wrappingUp ? (
        <p className="audit-banner" role="status">
          {session.status === 'processing'
            ? 'Audit in progress — scoring answers and preparing the provisional report.'
            : 'Closing — questions are done. Provisional audit will run next (save recording, then score).'}
        </p>
      ) : null}

      <div className="live-main">
        <aside className="live-camera">
          <VoiceRoomPanel
            ref={videoRoomRef}
            sessionId={session.id}
            consentGranted={session.consent_status === 'granted'}
            autoStartVideo
            onTranscript={wrappingUp ? undefined : onTranscript}
          />
        </aside>

        <div className="live-work">
          {wrappingUp ? (
            <p className="hint">
              You can still browse prior questions below. Complete the audit to see the provisional
              report and recording playback.
            </p>
          ) : null}
          {orderedQuestions.length > 0 ? (
            <div className="question-nav">
              <button
                type="button"
                className="ghost"
                disabled={busy || viewIndex <= 0}
                onClick={() => setViewIndex((i) => Math.max(0, i - 1))}
              >
                Previous
              </button>
              <span className="question-pos">
                {viewIndex + 1} / {orderedQuestions.length}
              </span>
              <button
                type="button"
                className="ghost"
                disabled={busy || viewIndex >= orderedQuestions.length - 1}
                onClick={() => {
                  if (viewingCurrent) {
                    void onVoiceNext()
                    return
                  }
                  setViewIndex((i) => Math.min(i + 1, orderedQuestions.length - 1))
                }}
              >
                Next
              </button>
              {!viewingCurrent ? (
                <button
                  type="button"
                  className="ghost"
                  disabled={busy || !session.current_question_id}
                  onClick={() => {
                    const idx = orderedQuestions.findIndex((q) => q.id === session.current_question_id)
                    if (idx >= 0) setViewIndex(idx)
                  }}
                >
                  Jump to current
                </button>
              ) : null}
            </div>
          ) : null}

          {viewedQuestion ? (
            <article className="bubble persona">
              <header>
                {formatCompetency(viewedQuestion.competency)} · {viewedQuestion.difficulty}
                {viewedQuestion.hypothetical ? ' · hypothetical' : ''}
                {!viewingCurrent ? ` · ${viewedQuestion.status}` : ''}
              </header>
              <p>{viewedQuestion.prompt}</p>
              {viewedQuestion.code_refs?.path ? (
                <footer>
                  {String(viewedQuestion.code_refs.path)}
                  {Array.isArray(viewedQuestion.code_refs.line_range)
                    ? `:${String(viewedQuestion.code_refs.line_range[0])}-${String(viewedQuestion.code_refs.line_range[1])}`
                    : ''}{' '}
                  @ {String(viewedQuestion.code_refs.sha || '').slice(0, 7)}
                </footer>
              ) : null}
            </article>
          ) : null}

          {probePrompt && viewingCurrent ? <p className="hint">Probe: {probePrompt}</p> : null}

          {canAnswer && (
            <form className="chat-compose live-answer" onSubmit={onAnswer}>
              <textarea
                value={answer}
                onChange={(e) => {
                  setAnswer(e.target.value)
                  sttBaseRef.current = e.target.value
                }}
                rows={5}
                placeholder={
                  session.current_participant_name
                    ? `Speak or type as ${session.current_participant_name}… (say “next” to skip — an alternate may replace it)`
                    : 'Speak or type your answer… (say “next” to skip — an alternate may replace it)'
                }
                required
                disabled={busy}
              />
              <button type="submit" disabled={busy || !answer.trim()}>
                {session.status === 'optional_probe' ? 'Submit probe' : 'Submit answer'}
              </button>
            </form>
          )}

          {viewedQuestion && !viewingCurrent ? (
            viewedQuestion.answers.length > 0 ? (
              <div className="live-actions" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                {viewedQuestion.answers.map((a) => (
                  <p key={a.id} className="past-answer">
                    {a.is_probe ? 'Probe: ' : ''}
                    {a.text}
                  </p>
                ))}
              </div>
            ) : (
              <p className="hint">No answer recorded for this question.</p>
            )
          ) : null}

          {!currentQuestion && orderedQuestions.length === 0 ? (
            <p className="hint">Preparing questions…</p>
          ) : null}
        </div>
      </div>
    </section>
  ) : (
    <section className="surface">
      <p className="hint">Start or continue an interview from the Interviews tab.</p>
      <button type="button" className="ghost" onClick={() => setTab('hub')}>
        Go to Interviews
      </button>
    </section>
  )

  const body =
    tab === 'group' ? groupScreen : tab === 'live' ? reviewScreen ?? liveScreen : hubScreen

  return (
    <CourseShell
      title="Exit interviews"
      subtitle={
        team?.name
          ? `${team.name}${repoReady ? '' : ' · repo not ready'}`
          : 'Start interview and review past sessions'
      }
      tabs={tabs}
      activeTab={tab}
      onTabChange={(id) => {
        // Live is only entered via Interviews → open/view, never by clicking the tab.
        if (id === 'live') return
        if (tab === 'live') {
          setSession(null)
          setReport(null)
          setProbePrompt(null)
        }
        setTab(id as ExitTab)
      }}
    >
      <div
        className={`stack${
          tab === 'hub' ? ' stack-fill' : tab === 'live' ? ' stack-live' : ' stack-wide'
        }`}
      >
        {error && <p className="error">{error}</p>}
        {body}
      </div>

      {consentModalOpen && pendingSession ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) {
              setConsentModalOpen(false)
              setPendingSession(null)
              setConsentChecked(false)
            }
          }}
        >
          <div
            className="modal-panel modal-panel-wide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="consentModalTitle"
          >
            <div className="modal-header">
              <h3 id="consentModalTitle">{policy?.consent.title ?? 'Consent'}</h3>
              <button
                type="button"
                className="modal-close"
                aria-label="Close"
                disabled={busy}
                onClick={() => {
                  setConsentModalOpen(false)
                  setPendingSession(null)
                  setConsentChecked(false)
                }}
              >
                ×
              </button>
            </div>
            <p className="hint" style={{ marginTop: 0 }}>
              {policy?.consent.summary ??
                'Confirm consent before the interview and any recording begin.'}
            </p>
            {policy?.consent.bullets?.length ? (
              <ul className="consent-checklist">
                {policy.consent.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            ) : null}
            <label className="consent-check">
              <input
                type="checkbox"
                checked={consentChecked}
                disabled={busy}
                onChange={(e) => setConsentChecked(e.target.checked)}
              />
              <span>I give consent for this exit interview and any recording.</span>
            </label>
            <div className="live-actions" style={{ marginTop: 14 }}>
              <button
                type="button"
                disabled={busy || !consentChecked}
                onClick={() => void onConfirmConsent()}
              >
                {busy ? 'Starting…' : 'Start interview'}
              </button>
              <button
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() => {
                  setConsentModalOpen(false)
                  setPendingSession(null)
                  setConsentChecked(false)
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </CourseShell>
  )
}
