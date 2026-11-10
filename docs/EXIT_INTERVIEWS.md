# Exit interviews (text + video + STT)

Exit interviews are hosted inside **sellm** at `/course/`. Stakeholder chat stays at `/`.

The flow is **student self-service**. Teammates **share one cohort login** (same account used for requirements chat) and type each person’s **real name** when creating the exit session — there is no invite / join workflow.

## Dry-run checklist (students)

1. Sign in at `/course/login` with the shared cohort username.
2. Open **Create team** (`/course/admin/teams`) and create a team (creator owns it).
3. Open the team’s **repository** page: submit `fixture://demo` with SHA from `tests/fixtures/repos/demo/.fixture-sha` (or a real GitHub URL + commit). Wait until index status is `ready`.
4. Open **Exit interview**: pick the frozen repo and enter participant names (one per line).
5. **Give consent (all)**, then **Start**.
6. When a name is shown as the current student, that person answers by **text**, or join LiveKit and use **browser STT** / paste, then **Commit answer**.
7. Anyone on the shared login can **Start/Stop recording** (requires LiveKit). Playback: `/api/exit-sessions/<id>/recording`.
8. **Finish & score** → provisional reports keyed by the typed names. Admins may later finalize via `POST /api/admin/assessments/<id>/review`.

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
