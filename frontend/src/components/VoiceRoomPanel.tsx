import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import {
  fetchVoiceStatus,
  startVoiceRecording,
  stopVoiceRecording,
  uploadVoiceRecording,
} from '../api/client'

export type VoiceRoomHandle = {
  stopAndUpload: () => Promise<void>
}

type Props = {
  sessionId: string
  consentGranted: boolean
  /** When true, request camera+mic and record for the active interview. */
  autoStartVideo?: boolean
  /** Browser speech recognition text — finals and interim for the answer field. */
  onTranscript?: (text: string, isFinal: boolean) => void
}

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

function pickMimeType(): string {
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ]
  for (const type of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
      return type
    }
  }
  return 'video/webm'
}

export const VoiceRoomPanel = forwardRef<VoiceRoomHandle, Props>(function VoiceRoomPanel(
  { sessionId, consentGranted, autoStartVideo = false, onTranscript },
  ref,
) {
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const [cameraReady, setCameraReady] = useState(false)
  const [listening, setListening] = useState(false)

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const mimeRef = useRef('video/webm')
  const startingRef = useRef(false)
  const uploadingRef = useRef(false)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const onTranscriptRef = useRef(onTranscript)
  onTranscriptRef.current = onTranscript
  const sessionIdRef = useRef(sessionId)
  sessionIdRef.current = sessionId

  async function stopTracks() {
    recognitionRef.current?.abort()
    recognitionRef.current = null
    setListening(false)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setCameraReady(false)
  }

  async function flushUpload(sid: string): Promise<boolean> {
    if (uploadingRef.current) return false
    uploadingRef.current = true
    try {
      const recorder = recorderRef.current
      if (recorder && recorder.state !== 'inactive') {
        const done = new Promise<Blob>((resolve) => {
          recorder.onstop = () => {
            resolve(new Blob(chunksRef.current, { type: mimeRef.current }))
          }
        })
        recorder.stop()
        recorderRef.current = null
        setRecording(false)
        const blob = await done
        if (blob.size > 0) {
          await uploadVoiceRecording(sid, blob)
          chunksRef.current = []
          return true
        }
      } else if (chunksRef.current.length > 0) {
        // Recorder already stopped (remount/race) — upload buffered chunks.
        const blob = new Blob(chunksRef.current, { type: mimeRef.current })
        if (blob.size > 0) {
          await uploadVoiceRecording(sid, blob)
          chunksRef.current = []
          return true
        }
      }
      return false
    } finally {
      uploadingRef.current = false
    }
  }

  async function stopAndUpload() {
    const sid = sessionIdRef.current
    try {
      await flushUpload(sid)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Recording upload failed')
      throw err
    } finally {
      await stopTracks()
      try {
        await stopVoiceRecording(sid)
      } catch {
        // browser upload is the source of truth when egress is unavailable
      }
    }
  }

  useImperativeHandle(ref, () => ({ stopAndUpload }), [])

  useEffect(() => {
    if (!autoStartVideo || !consentGranted) return
    if (startingRef.current || recorderRef.current) return

    let cancelled = false
    startingRef.current = true

    void (async () => {
      setError(null)
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user' },
          audio: true,
        })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => undefined)
        }
        setCameraReady(true)

        const mime = pickMimeType()
        mimeRef.current = mime
        chunksRef.current = []
        const recorder = new MediaRecorder(stream, { mimeType: mime })
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunksRef.current.push(event.data)
        }
        recorder.start(1000)
        recorderRef.current = recorder
        setRecording(true)

        try {
          await startVoiceRecording(sessionId)
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Could not mark recording started')
        }

        const Ctor = getSpeechRecognitionCtor()
        if (Ctor && !cancelled) {
          const recognition = new Ctor()
          recognition.continuous = true
          recognition.interimResults = true
          recognition.lang = 'en-US'
          recognitionRef.current = recognition
          recognition.onresult = (event: SpeechRecognitionEvent) => {
            let interim = ''
            for (let i = event.resultIndex; i < event.results.length; i++) {
              const result = event.results[i]
              const text = (result[0]?.transcript ?? '').trim()
              if (!text) continue
              if (result.isFinal) onTranscriptRef.current?.(text, true)
              else interim += (interim ? ' ' : '') + text
            }
            if (interim) onTranscriptRef.current?.(interim, false)
          }
          recognition.onerror = () => setListening(false)
          recognition.onend = () => {
            setListening(false)
            if (!cancelled && recognitionRef.current === recognition) {
              try {
                recognition.start()
                setListening(true)
              } catch {
                // mic may be unavailable
              }
            }
          }
          try {
            recognition.start()
            setListening(true)
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Speech recognition unavailable')
          }
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : 'Camera/microphone permission is required to record the interview',
        )
        setRecording(false)
      } finally {
        startingRef.current = false
      }
    })()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, autoStartVideo, consentGranted])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      // Best-effort flush so remount/close races don't drop the tape.
      const sid = sessionIdRef.current
      const mime = mimeRef.current
      const recorder = recorderRef.current
      const stream = streamRef.current
      recorderRef.current = null
      streamRef.current = null

      const uploadChunks = () => {
        const chunks = chunksRef.current
        chunksRef.current = []
        if (!chunks.length) return
        const blob = new Blob(chunks, { type: mime })
        if (blob.size > 0) {
          void uploadVoiceRecording(sid, blob).catch(() => undefined)
        }
      }

      if (recorder && recorder.state !== 'inactive') {
        recorder.onstop = () => {
          uploadChunks()
          stream?.getTracks().forEach((t) => t.stop())
        }
        try {
          recorder.stop()
        } catch {
          uploadChunks()
          stream?.getTracks().forEach((t) => t.stop())
        }
      } else {
        uploadChunks()
        stream?.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  useEffect(() => {
    void fetchVoiceStatus(sessionId).catch(() => undefined)
  }, [sessionId])

  const speechAvailable = typeof getSpeechRecognitionCtor() !== 'undefined'

  return (
    <div className="video-room compact" aria-label="Video recording">
      <div className="video-preview-wrap">
        <video ref={videoRef} className="video-preview" playsInline muted autoPlay />
        {!cameraReady && <div className="video-preview-empty">Camera</div>}
        {recording ? <span className="video-rec-badge">REC</span> : null}
      </div>
      <p className="hint video-room-meta">
        {listening ? 'Listening…' : cameraReady ? 'Mic ready' : 'Starting…'}
        {!speechAvailable ? ' · speech API unavailable' : ''}
      </p>
      {error && <p className="error">{error}</p>}
    </div>
  )
})
