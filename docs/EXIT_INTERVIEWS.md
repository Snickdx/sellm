# Exit interviews (text + video + STT)

Exit interviews are hosted inside **sellm** at `/course/`. Stakeholder chat stays at `/`.

The flow is **student self-service**. Instructors are only needed later to finalize provisional scores if desired.

## Dry-run checklist (students)

1. Sign in at `/course/login` with a cohort username.
2. Open **Create / join team** (`/course/admin/teams`):
   - create a team (you are auto-added), share the invite code, **or**
   - join with a teammate’s invite code / add usernames.
3. Open the team’s **repository** page: submit `fixture://demo` with SHA from `tests/fixtures/repos/demo/.fixture-sha` (or a real GitHub URL + commit). Wait until index status is `ready`.
4. Open **Exit interview**: create a session (select repo + participants).
5. Each participant **gives consent**, then anyone can **Start**.
6. Answer by **text**, or join LiveKit and use **browser STT** / paste, then **Commit answer**.
7. Any participant can **Start/Stop recording** (requires LiveKit). Playback: `/api/exit-sessions/<id>/recording`.
8. Anyone on the team can **Finish & score** → provisional reports. Admins may later finalize via `POST /api/admin/assessments/<id>/review`.

## Environment

```bash
# Optional GitHub (public repos work without a token)
GITHUB_TOKEN=ghp_...

# LiveKit (video room + real egress)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...

# Local recording sink (EasyPanel: mount under /app/storage)
STORAGE_RECORDINGS_DIR=./storage/recordings

# Optional S3-compatible sink for LiveKit Cloud egress
# RECORDINGS_S3_BUCKET=...
# RECORDINGS_S3_ACCESS_KEY=...
# RECORDINGS_S3_SECRET_KEY=...
# RECORDINGS_S3_REGION=...
# RECORDINGS_S3_ENDPOINT=...   # MinIO / R2

# When LiveKit is unset
# VOICE_EXTERNAL_FALLBACK_URL=https://meet.jit.si/sellm-fallback
```

## Build the SPA

```bash
cd frontend
npm ci
npm run build
```

FastAPI serves `frontend/dist` at `/course/`.

## Scoring policy

Provisional scores use **answer text only**. Accent, appearance, and vocal confidence are never accepted or graded.

## Offline fixture

`fixture://demo` maps to `tests/fixtures/repos/demo`. Useful for CI and classroom dry-runs without GitHub.
