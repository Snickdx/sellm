import { useEffect, useRef, useState } from 'react'
import { Room, RoomEvent } from 'livekit-client'
import {
  commitVoiceUtterance,
  fetchVoiceStatus,
  fetchVoiceToken,
  leaveVoiceRoom,
  listVoiceUtterances,
  postVoiceUtterance,
  startVoiceRecording,
  stopVoiceRecording,
  type VoiceStatus,
} from '../api/client'

type Props = {
  sessionId: string
  canRecord?: boolean
  consentGranted: boolean
}

type UtteranceRow = { id: string; user_id: number; text: string }

type SpeechRecognitionLike = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onerror: ((event: Event) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | undefined {
  if (typeof window === 'undefined') return undefined
  const w = window as Window & {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export function VoiceRoomPanel({ sessionId, canRecord = true, consentGranted }: Props) {
  const [status, setStatus] = useState<VoiceStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [connected, setConnected] = useState(false)
  const [room, setRoom] = useState<Room | null>(null)
  const [sttDraft, setSttDraft] = useState('')
  const [utterances, setUtterances] = useState<UtteranceRow[]>([])
  const [speechActive, setSpeechActive] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)

  async function refresh() {
    const s = await fetchVoiceStatus(sessionId)
    setStatus(s)
    const rows = await listVoiceUtterances(sessionId)
    setUtterances(rows.map((r) => ({ id: r.id, user_id: r.user_id, text: r.text })))
  }

  useEffect(() => {
    void refresh().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : 'Voice status failed'),
    )
    return () => {
      void room?.disconnect()
      recognitionRef.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  useEffect(() => {
    if (!connected) {
      recognitionRef.current?.stop()
      setSpeechActive(false)
      return
    }

    const Ctor = getSpeechRecognitionCtor()
    if (!Ctor) return

    const recognition = new Ctor()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognitionRef.current = recognition

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        const text = result[0]?.transcript ?? ''
        if (result.isFinal) {
          const trimmed = text.trim()
          if (trimmed) {
            void (async () => {
              try {
                await postVoiceUtterance(sessionId, trimmed)
                setSttDraft('')
                await refresh()
              } catch (err) {
                setError(err instanceof Error ? err.message : 'Speech utterance failed')
              }
            })()
          }
        } else {
          interim += text
        }
      }
      if (interim.trim()) setSttDraft(interim.trim())
    }

    recognition.onerror = () => {
      setSpeechActive(false)
    }

    recognition.onend = () => {
      setSpeechActive(false)
      if (connected && recognitionRef.current === recognition) {
        try {
          recognition.start()
          setSpeechActive(true)
        } catch {
          // mic may be unavailable
        }
      }
    }

    try {
      recognition.start()
      setSpeechActive(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start speech recognition')
    }

    return () => {
      recognition.onresult = null
      recognition.onerror = null
      recognition.onend = null
      recognition.stop()
      if (recognitionRef.current === recognition) recognitionRef.current = null
    }
  }, [connected, sessionId])

  async function onJoin() {
    setBusy(true)
    setError(null)
    try {
      const token = await fetchVoiceToken(sessionId)
      const next = new Room()
      next.on(RoomEvent.Disconnected, () => setConnected(false))
      await next.connect(token.url, token.token)
      await next.localParticipant.setMicrophoneEnabled(true)
      setRoom(next)
      setConnected(true)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Join failed')
    } finally {
      setBusy(false)
    }
  }

  async function onLeave() {
    setBusy(true)
    try {
      recognitionRef.current?.stop()
      await room?.disconnect()
      setRoom(null)
      setConnected(false)
      await leaveVoiceRoom(sessionId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Leave failed')
    } finally {
      setBusy(false)
    }
  }

  async function onRecord(start: boolean) {
    setBusy(true)
    setError(null)
    try {
      if (start) await startVoiceRecording(sessionId)
      else await stopVoiceRecording(sessionId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Recording control failed')
    } finally {
      setBusy(false)
    }
  }

  async function onSubmitStt() {
    if (!sttDraft.trim()) return
    setBusy(true)
    try {
      const row = await postVoiceUtterance(sessionId, sttDraft.trim())
      setSttDraft('')
      await refresh()
      try {
        await commitVoiceUtterance(sessionId, row.id)
      } catch {
        // leave as transcript-only if not their turn
      }
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'STT submit failed')
    } finally {
      setBusy(false)
    }
  }

  async function onCommitUtterance(utteranceId: string) {
    setBusy(true)
    setError(null)
    try {
      await commitVoiceUtterance(sessionId, utteranceId)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Commit answer failed')
    } finally {
      setBusy(false)
    }
  }

  const speechAvailable = typeof getSpeechRecognitionCtor() !== 'undefined'

  return (
    <section className="surface" aria-label="Voice interview">
      <h2>Voice / video room</h2>
      <p className="hint">
        Text answers remain the default. Voice is optional. Scoring never uses accent,
        appearance, or vocal confidence — only attributed transcript text.
      </p>
      {error && <p className="error">{error}</p>}
      {status && (
        <>
          <p className="hint">
            LiveKit: {status.livekit_configured ? 'configured' : 'not configured'} · Room:{' '}
            {status.room_name ?? '—'} · Recording: {status.recording_status ?? 'none'}
            {connected && speechAvailable
              ? ` · Browser STT: ${speechActive ? 'listening' : 'paused'}`
              : ''}
          </p>
          {status.recording_indicator && (
            <p className="recording-banner" role="status">
              ● Recording in progress — do not share secrets. Consent already required.
            </p>
          )}
          {!status.livekit_configured && (
            <p className="hint">
              LiveKit credentials are not set. Keep using typed answers, or open the external
              fallback:{' '}
              <a href={status.external_fallback_url} target="_blank" rel="noreferrer">
                {status.external_fallback_url}
              </a>
            </p>
          )}
          <div className="export-row">
            <button
              type="button"
              className="ghost"
              disabled={busy || !consentGranted || !status.livekit_configured || connected}
              onClick={() => void onJoin()}
            >
              Join room
            </button>
            <button
              type="button"
              className="ghost"
              disabled={busy || !connected}
              onClick={() => void onLeave()}
            >
              Leave
            </button>
            {canRecord && (
              <>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy || !consentGranted}
                  onClick={() => void onRecord(true)}
                >
                  Start recording
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy}
                  onClick={() => void onRecord(false)}
                >
                  Stop recording
                </button>
              </>
            )}
          </div>
          <p className="hint">
            Connected: {connected ? 'yes' : 'no'} ·{' '}
            {speechAvailable
              ? 'Speech recognition runs while connected.'
              : 'Paste or type STT below (no browser speech API).'}
          </p>
          <div className="chat-compose">
            <label>
              STT draft {connected && speechAvailable ? '(live + editable)' : '(paste or type)'}
              <textarea
                value={sttDraft}
                onChange={(e) => setSttDraft(e.target.value)}
                rows={3}
                disabled={busy}
                placeholder="Recognized speech appears here; edit before saving…"
              />
            </label>
            <button type="button" disabled={busy || !sttDraft.trim()} onClick={() => void onSubmitStt()}>
              Save attributed utterance
            </button>
          </div>
          {utterances.length > 0 && (
            <ul className="team-list">
              {utterances.map((u) => (
                <li key={u.id}>
                  <strong>user {u.user_id}</strong>
                  <span>{u.text}</span>
                  <button
                    type="button"
                    className="ghost"
                    disabled={busy}
                    onClick={() => void onCommitUtterance(u.id)}
                  >
                    Commit answer
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
