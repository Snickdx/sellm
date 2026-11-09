import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { addTeamMembers, createTeam, joinTeam } from '../api/client'
import { useAuth } from '../auth'

export function AdminTeamsPage() {
  const { user, loading } = useAuth()
  const [name, setName] = useState('')
  const [scenarioSlug, setScenarioSlug] = useState('')
  const [createdTeamId, setCreatedTeamId] = useState<string | null>(null)
  const [memberUsernames, setMemberUsernames] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (loading) return <main className="page"><p>Loading…</p></main>
  if (!user) return <Navigate to="/login" replace />

  async function onCreateTeam(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const team = await createTeam(name.trim(), scenarioSlug.trim() || undefined)
      setCreatedTeamId(team.id)
      setMessage(`Created team “${team.name}” (invite ${team.invite_code}). You are a member.`)
      setName('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create team')
    } finally {
      setBusy(false)
    }
  }

  async function onJoin(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const team = await joinTeam(inviteCode.trim())
      setCreatedTeamId(team.id)
      setMessage(`Joined “${team.name}”.`)
      setInviteCode('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not join team')
    } finally {
      setBusy(false)
    }
  }

  async function onAddMembers(event: FormEvent) {
    event.preventDefault()
    if (!createdTeamId) {
      setError('Create or join a team first, or paste a team id below.')
      return
    }
    const usernames = memberUsernames
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (usernames.length === 0) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await addTeamMembers(createdTeamId, usernames)
      setMessage(`Added ${usernames.length} member(s) to team ${createdTeamId}.`)
      setMemberUsernames('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add members')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <p className="eyebrow">Teams</p>
      <h1>Create or join</h1>
      <p className="lede">Students manage their own teams — no instructor step required.</p>
      <Link to="/">Back</Link>
      {error && <p className="error">{error}</p>}
      {message && <p className="hint">{message}</p>}

      <section className="panel">
        <h2>Create team</h2>
        <form className="auth-form" onSubmit={onCreateTeam}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Scenario slug (optional)
            <input
              value={scenarioSlug}
              onChange={(e) => setScenarioSlug(e.target.value)}
              placeholder="e.g. uwi-connect"
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? 'Working…' : 'Create team'}
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>Join with invite code</h2>
        <form className="auth-form" onSubmit={onJoin}>
          <label>
            Invite code
            <input
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
              placeholder="ABCD1234"
            />
          </label>
          <button type="submit" disabled={busy || !inviteCode.trim()}>
            {busy ? 'Working…' : 'Join team'}
          </button>
        </form>
      </section>

      <section className="panel">
        <h2>Add teammates</h2>
        <form className="auth-form" onSubmit={onAddMembers}>
          <label>
            Team id
            <input
              value={createdTeamId ?? ''}
              onChange={(e) => setCreatedTeamId(e.target.value || null)}
              placeholder="From create/join step or home"
            />
          </label>
          <label>
            Usernames (comma or space separated)
            <textarea
              value={memberUsernames}
              onChange={(e) => setMemberUsernames(e.target.value)}
              rows={3}
              placeholder="student1, student2"
            />
          </label>
          <button type="submit" disabled={busy || !createdTeamId}>
            {busy ? 'Working…' : 'Add members'}
          </button>
        </form>
      </section>
    </main>
  )
}
