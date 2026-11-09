import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchPolicy, type PolicyDoc } from '../api/client'

export function PolicyPage() {
  const [policy, setPolicy] = useState<PolicyDoc | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void fetchPolicy()
      .then(setPolicy)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load policy'))
  }, [])

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">Course</p>
          <h1>Consent, retention &amp; access</h1>
        </div>
        <Link to="/">Home</Link>
      </header>

      {error && <p className="error">{error}</p>}
      {!policy && !error && <p>Loading…</p>}

      {policy && (
        <>
          <section className="panel">
            <h2>{policy.consent.title}</h2>
            <p className="lede">{policy.consent.summary}</p>
            <ul>
              {policy.consent.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </section>

          <section className="panel">
            <h2>Retention</h2>
            <p>{policy.retention.summary}</p>
            <p className="hint">{policy.retention.deletion}</p>
            <p className="hint">
              Transcripts ≈ {policy.retention.transcript_days} days · Recordings ≈{' '}
              {policy.retention.recording_days} days
            </p>
          </section>

          <section className="panel">
            <h2>Accessibility &amp; low bandwidth</h2>
            <p>{policy.accessibility.low_bandwidth}</p>
            <ul>
              {policy.accessibility.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </section>

          <section className="panel">
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
    </main>
  )
}
