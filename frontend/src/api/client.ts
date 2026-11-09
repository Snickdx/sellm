const API_BASE =
  import.meta.env.VITE_API_BASE !== undefined && import.meta.env.VITE_API_BASE !== null
    ? String(import.meta.env.VITE_API_BASE).replace(/\/$/, '')
    : ''

export type UserRole = 'admin' | 'tester' | 'student'

export interface MeResponse {
  user_id: number
  username: string
  is_admin: boolean
  role: UserRole
}

/** Normalized view for UI code ported from seproject (`id`, `display_name`). */
export interface User extends MeResponse {
  id: number
  display_name: string
}

export function isInstructor(user: User | null | undefined): boolean {
  return !!user && user.role === 'admin'
}

export interface Team {
  id: string
  name: string
  scenario_slug: string | null
  scenario_version: string | null
  invite_code: string
  created_at: string
}

/** Same key as sellm chat / admin (`app/web/static/components/chat.js`). */
export const AUTH_TOKEN_KEY = 'auth_token'

function authHeaders(): HeadersInit {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function url(path: string): string {
  const normalized = path.startsWith('/api') ? path : `/api${path.startsWith('/') ? path : `/${path}`}`
  return `${API_BASE}${normalized}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail != null) detail = JSON.stringify(body.detail)
    } catch {
      // ignore parse errors
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

function mapUser(raw: MeResponse): User {
  return {
    ...raw,
    id: raw.user_id,
    display_name: raw.username,
  }
}

export async function login(username: string, password: string): Promise<string> {
  const data = await request<{ token: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  return data.token
}

export async function fetchMe(): Promise<User> {
  const raw = await request<MeResponse>('/api/auth/me')
  return mapUser(raw)
}

export async function fetchMyTeams(): Promise<Team[]> {
  return request<Team[]>('/api/me/teams')
}

export async function createTeam(name: string, scenario_slug?: string): Promise<Team> {
  return request<Team>('/api/teams', {
    method: 'POST',
    body: JSON.stringify({ name, scenario_slug: scenario_slug || null }),
  })
}

export async function joinTeam(invite_code: string): Promise<Team> {
  return request<Team>('/api/teams/join', {
    method: 'POST',
    body: JSON.stringify({ invite_code }),
  })
}

export async function addTeamMembers(teamId: string, usernames: string[]): Promise<void> {
  await request(`/api/teams/${teamId}/members`, {
    method: 'POST',
    body: JSON.stringify({ usernames }),
  })
}

export interface TeamMember {
  user_id: number
  display_name: string
  username?: string
  role: UserRole
}

export async function fetchTeamDetail(teamId: string): Promise<Team & { members: TeamMember[] }> {
  return request(`/api/teams/${teamId}`)
}

export interface RepositorySubmission {
  id: string
  team_id: string
  github_url: string
  owner: string
  repo: string
  branch: string | null
  commit_sha: string
  index_status: string
  index_error: string | null
  attempt_count: number
  summary: Record<string, unknown> | null
}

export interface SearchHit {
  path: string
  line: number
  line_range: [number, number]
  sha: string
  excerpt: string
}

export async function listTeamRepositories(teamId: string): Promise<RepositorySubmission[]> {
  return request(`/api/admin/teams/${teamId}/repositories`)
}

export async function submitRepository(
  teamId: string,
  body: { github_url: string; commit_sha: string; branch?: string; analyze_now?: boolean },
): Promise<RepositorySubmission> {
  return request(`/api/admin/teams/${teamId}/repository`, {
    method: 'POST',
    body: JSON.stringify({ analyze_now: true, ...body }),
  })
}

export async function analyzeRepository(repoId: string): Promise<RepositorySubmission> {
  return request(`/api/admin/repositories/${repoId}/analyze`, { method: 'POST' })
}

export async function fetchRepositoryStatus(repoId: string): Promise<RepositorySubmission> {
  return request(`/api/admin/repositories/${repoId}/status`)
}

export async function searchRepository(repoId: string, query: string): Promise<SearchHit[]> {
  return request<SearchHit[]>(`/api/admin/repositories/${repoId}/search`, {
    method: 'POST',
    body: JSON.stringify({ query }),
  })
}

export interface ExitQuestion {
  id: string
  sequence: number
  target_user_id: number
  competency: string
  difficulty: string
  prompt: string
  code_refs: Record<string, unknown>
  expected_concepts: string[]
  rubric: string
  follow_ups: string[]
  hypothetical: boolean
  status: string
  answers: Array<{
    id: string
    user_id: number
    text: string
    is_probe: boolean
    modality: string
    created_at: string | null
  }>
}

export interface ExitSession {
  id: string
  team_id: string
  repository_submission_id: string
  status: string
  consent_status: string
  target_duration_minutes: number
  current_participant_user_id: number | null
  current_question_id: string | null
  plan: Record<string, unknown> | null
  participants: Array<{
    user_id: number
    display_name: string | null
    consent_status: string
    turn_order: number
  }>
  questions: ExitQuestion[]
  unanswered_question_ids: string[]
  probe_prompt?: string | null
}

export async function listTeamExitSessions(
  teamId: string,
): Promise<Array<{ id: string; status: string; consent_status: string }>> {
  return request(`/api/teams/${teamId}/exit-sessions`)
}

export async function fetchExitSession(sessionId: string): Promise<ExitSession> {
  return request(`/api/exit-sessions/${sessionId}`)
}

export async function createExitSession(
  teamId: string,
  body: {
    repository_submission_id: string
    participant_user_ids: number[]
    target_duration_minutes?: number
    questions_per_student?: number
  },
): Promise<ExitSession> {
  return request(`/api/admin/teams/${teamId}/exit-session`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function consentExitSession(sessionId: string, granted = true): Promise<ExitSession> {
  return request(`/api/exit-sessions/${sessionId}/consent`, {
    method: 'POST',
    body: JSON.stringify({ granted }),
  })
}

export async function startExitSession(sessionId: string): Promise<ExitSession> {
  return request(`/api/exit-sessions/${sessionId}/start`, { method: 'POST' })
}

export async function nextExitQuestion(sessionId: string): Promise<ExitSession> {
  return request(`/api/exit-sessions/${sessionId}/next`, { method: 'POST' })
}

export async function submitExitAnswer(
  sessionId: string,
  text: string,
  request_probe = false,
): Promise<ExitSession> {
  return request(`/api/exit-sessions/${sessionId}/answers`, {
    method: 'POST',
    body: JSON.stringify({ text, request_probe }),
  })
}

export async function submitProbeAnswer(sessionId: string, text: string): Promise<ExitSession> {
  return request(`/api/exit-sessions/${sessionId}/answers/probe`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export async function finishExitSession(
  sessionId: string,
): Promise<{ session: ExitSession; reports: unknown }> {
  return request(`/api/exit-sessions/${sessionId}/finish`, { method: 'POST' })
}

export async function fetchExitReport(sessionId: string): Promise<unknown> {
  return request(`/api/admin/exit-sessions/${sessionId}/report`)
}

export interface PolicyDoc {
  version: string
  consent: { title: string; summary: string; bullets: string[] }
  retention: {
    transcript_days: number
    recording_days: number
    summary: string
    deletion: string
  }
  accessibility: { text_only_supported: boolean; low_bandwidth: string; notes: string[] }
  quotas: {
    team_chat_messages_per_day: number
    team_llm_tokens_per_day: number
    llm_budget_alert_usd: number
  }
}

export async function fetchPolicy(): Promise<PolicyDoc> {
  return request<PolicyDoc>('/api/policy')
}

export interface VoiceStatus {
  livekit_configured: boolean
  text_fallback: boolean
  external_fallback_url: string
  grading_uses_audio_cues: boolean
  room_name: string | null
  room_status: string | null
  recording_status: string | null
  recording_indicator: boolean
  playback_url: string | null
  consent_required: boolean
}

export interface VoiceToken {
  url: string
  token: string
  room_name: string
  identity: string
  recording_indicator: boolean
  text_fallback: boolean
}

export async function fetchVoiceStatus(sessionId: string): Promise<VoiceStatus> {
  return request(`/api/exit-sessions/${sessionId}/voice`)
}

export async function fetchVoiceToken(sessionId: string): Promise<VoiceToken> {
  return request(`/api/exit-sessions/${sessionId}/voice/token`, { method: 'POST' })
}

export async function leaveVoiceRoom(sessionId: string): Promise<void> {
  await request(`/api/exit-sessions/${sessionId}/voice/leave`, { method: 'POST' })
}

export async function startVoiceRecording(sessionId: string): Promise<{
  recording_indicator: boolean
  recording_status: string
}> {
  return request(`/api/exit-sessions/${sessionId}/voice/recording/start`, { method: 'POST' })
}

export async function stopVoiceRecording(sessionId: string): Promise<{
  recording_indicator: boolean
  playback_url?: string
}> {
  return request(`/api/exit-sessions/${sessionId}/voice/recording/stop`, { method: 'POST' })
}

export async function postVoiceUtterance(
  sessionId: string,
  text: string,
): Promise<{ id: string; user_id: number; text: string }> {
  return request(`/api/exit-sessions/${sessionId}/voice/utterances`, {
    method: 'POST',
    body: JSON.stringify({ text, is_final: true }),
  })
}

export async function listVoiceUtterances(sessionId: string): Promise<
  Array<{ id: string; user_id: number; text: string; corrected_text: string | null }>
> {
  return request(`/api/exit-sessions/${sessionId}/voice/utterances`)
}

export async function commitVoiceUtterance(
  sessionId: string,
  utteranceId: string,
): Promise<{ answer_id: string; text: string }> {
  return request(`/api/exit-sessions/${sessionId}/voice/utterances/${utteranceId}/commit-answer`, {
    method: 'POST',
  })
}
