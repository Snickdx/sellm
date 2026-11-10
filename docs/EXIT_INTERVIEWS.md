# Exit interviews (text + video + STT)

Exit interviews are hosted inside **sellm** at `/course/`. Stakeholder chat stays at `/`.

**Admin** creates teams and attaches them to a cohort credential (shared login). Students only see **Chats** and **Exit interviews** in the sidebar. Teammates share that login and type each person’s **real name** when creating the exit session.

## Dry-run checklist

### Admin
1. Sign in as admin → **Admin → Teams**.
2. Create a team, set **Owner cohort username** to e.g. `trainee01` (from cohort credentials).
3. Optionally edit members to add more cohort usernames.

### Students (shared cohort login)
1. Sign in at `/` or `/course/login` with the assigned cohort username.
2. Sidebar: **Chats** (requirements) or **Exit interviews**.
3. On Exit interviews → open the assigned team → **Repository**: submit `fixture://demo` (SHA in `tests/fixtures/repos/demo/.fixture-sha`) or a real GitHub URL + commit. Wait until `ready`.
4. **Exit interview**: pick the frozen repo and enter participant names (one per line).
5. **Give consent (all)**, then **Start**. Answer by text or LiveKit STT.
6. **Finish & score** → provisional reports keyed by typed names.

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

Scenario gold (intended patterns, seeded defects, focus paths) lives in:

- `instructor/private/<slug>/defect-manifest.yaml` — authoring SoT
- `app/examiner/knowledge/<slug>.yaml` — runtime judge packs

Do not put defect IDs or intended pattern names into student-facing prompts. See `docs/examiner-calibration.md` and `docs/known-limitations.md`.

## Offline fixture

`fixture://demo` maps to `tests/fixtures/repos/demo`. Useful for CI and classroom dry-runs without GitHub.
