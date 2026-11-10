import { useEffect, useState } from 'react'
import { fetchPolicy, type PolicyDoc } from '../api/client'
import { CourseShell } from '../components/CourseShell'
import { useAuth } from '../auth'
import { Navigate } from 'react-router-dom'

export function PolicyPage() {
  const { user, loading } = useAuth()
  const [policy, setPolicy] = useState<PolicyDoc | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void fetchPolicy()
      .then(setPolicy)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load policy'))
  }, [])

  if (loading) return <main className="page-fallback">Loading…</main>
  // Policy is readable without auth, but keep shell consistent when signed in.
  if (!user && !loading && !policy && !error) return <Navigate to="/login" replace />

  const body = (
    <div className="stack">
      {error && <p className="error">{error}</p>}
      {!policy && !error && <p className="hint">Loading…</p>}
      {policy && (
        <>
          <section className="surface">
            <h2>{policy.consent.title}</h2>
            <p className="lede">{policy.consent.summary}</p>
            <ul>
              {policy.consent.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </section>
          <section className="surface">
            <h2>Retention</h2>
            <p>{policy.retention.summary}</p>
            <p className="hint">{policy.retention.deletion}</p>
            <p className="hint">
              Transcripts ≈ {policy.retention.transcript_days} days · Recordings ≈{' '}
              {policy.retention.recording_days} days
            </p>
          </section>
          <section className="surface">
            <h2>Accessibility &amp; low bandwidth</h2>
            <p>{policy.accessibility.low_bandwidth}</p>
            <ul>
              {policy.accessibility.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </section>
          <section className="surface">
            <h2>Team quotas (pilot)</h2>
            <ul>
              <li>Chat messages / day: {policy.quotas.team_chat_messages_per_day}</li>
              <li>LLM tokens / day: {policy.quotas.team_llm_tokens_per_day}</li>
              <li>Budget alert (USD estimate): ${policy.quotas.llm_budget_alert_usd}</li>
            </ul>
            <p className="hint">Policy version {policy.version}</p>
          </section>
        </>
      )}
    </div>
  )

  if (!user) {
    return <main className="auth-shell"><div className="auth-panel" style={{ maxWidth: 640 }}>{body}</div></main>
  }

  return (
    <CourseShell title="Consent & retention" subtitle="Policy for exit interviews and recordings">
      {body}
    </CourseShell>
  )
}
