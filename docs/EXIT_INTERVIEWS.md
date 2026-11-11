# Exit interviews (text + video + STT)

Exit interviews run inside the **unified student shell** at `/exit` (same `index.html` as claim/login and `/req`). Old `/course/*` URLs redirect into these paths.

**Admin** creates teams and attaches them to a cohort credential (shared login), or students **claim a group** from the landing page at `/`. Teammates share that login and type each person’s **real name** when starting an exit session.

## Dry-run checklist

### Admin
1. Sign in as admin → **Admin → Teams** (or seed/claim a group).
2. Create a team, set **Owner cohort username** to e.g. `trainee01` (from cohort credentials), **or** let students claim via roster search on `/`.
3. Optionally edit members to add more cohort usernames.

### Students (shared group login)
1. Sign in at `/` (claim + login landing) with the group username.
2. Sidebar: **Req Interviews** (`/req`) or **Exit interviews** (`/exit`).
3. On Exit interviews: save a **Repository URL** in the toolbar (`fixture://demo` or a real GitHub URL). Wait until status is `ready`.
4. **+ Start interview**, enter the interviewee name, accept consent, then answer by text or browser speech recognition (MediaRecorder upload).
5. End / auto-finish on closing → provisional report + recording playback when available.

## Environment

```bash
# Optional GitHub (public repos work without a token)
GITHUB_TOKEN=ghp_...

# LiveKit (optional multi-party / egress — current student path uses browser MediaRecorder)
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

No separate SPA build step — student UI is static JS under `app/web/static/components/`.

## Scoring policy

Provisional scores use **answer text only**. Accent, appearance, and vocal confidence are never accepted or graded.

Scenario gold (intended patterns, seeded defects, focus paths) lives in:

- `instructor/private/<slug>/defect-manifest.yaml` — authoring SoT
- `app/examiner/knowledge/<slug>.yaml` — runtime judge packs

Do not put defect IDs or intended pattern names into student-facing prompts. See `docs/examiner-calibration.md` and `docs/known-limitations.md`.

## Offline fixture

`fixture://demo` maps to `tests/fixtures/repos/demo`. Useful for CI and classroom dry-runs without GitHub.
