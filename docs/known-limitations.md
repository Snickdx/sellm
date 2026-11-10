# Known limitations

Ported into **sellm** so this repo is independent of the old seproject platform monorepo. Defect manifests, examiner knowledge packs, scenarios, and exit-interview runtime all live in **sellm**; do not treat seproject as SoT.
Runtime exit interviews, examiner, and scenario packs live here. Student starters remain
the sibling [comp3613-templates](https://github.com/Snickdx/comp3613-templates) checkout.

## M0

- Auth is local username/password (cohort credentials + admin users), not institutional SSO.
- sellm is a single FastAPI app + optional `/course/` SPA; production is bare-metal systemd or Docker/EasyPanel from this repo.
- Object storage and Redis are not required. LiveKit is optional via env (see M6 / `docs/EXIT_INTERVIEWS.md`).
- Skills under `.agents/skills/` are local to sellm (scenario-author/validator, competency-judge, interview-designer).
- Student starters live in [Snickdx/comp3613-templates](https://github.com/Snickdx/comp3613-templates) (sibling checkout `templates/`), with seven private GitHub submodules (`comp3613-<slug>`). All seven flawed baselines (**0.2.0**) are built on [uwidcit/faststart](https://github.com/uwidcit/faststart) (`96ccfce`): **`job-board`** (State apps), **`library`** (Strategy conflict), **`uwi-connect`** (Observer), **`thesis-tracker`** (Command/audit), **`student-accommodation`** (State listings), **`ta-allocations`** (Strategy auto-alloc), **`career-advising`** (Template Method exploration). Domain APIs live under `/api`; private defect manifests under **`sellm/instructor/private/<slug>/`**, never in student trees. Runtime judge gold: `app/examiner/knowledge/<slug>.yaml`.

## M1

- `scenarios/library` approved package `0.1.0` is still grounded on the **synthetic** pilot; a real library VTT is present but not yet re-authored into facts.
- The other six scenarios are `approved` with real VTTs; re-check `READINESS.md` before treating every fact as classroom-final.
- Gap batches are orchestrated via the `scenario-author` skill + `gaps.yaml` (no dedicated web UI).
- Host-side backend venv should use **Python 3.12** (see `docs/setup.md`); Python 3.14 may fail to install binary wheels (e.g. PyYAML).
- Instructor scenario admin UI is import + preview only (no full CRUD editor).

## M2

- Default chat provider is **heuristic** (keyword overlap over persona-authorized facts). It is grounded but not conversationally rich; set `LLM_PROVIDER=openai` + `OPENAI_API_KEY` for hosted replies.
- Streaming SSE currently chunk-emits an already-generated answer (not token-native model streaming).
- Message limits are per-session env caps (`MAX_MESSAGES_PER_SESSION`); no Redis-backed global rate limiter yet.

## M3

- Draft review is heuristic (contradiction cues + coverage questions), not an LLM critique.
- Review uses **persona-authorized facts only**; evaluation/gaps never enter the prompt or response.
- Five scenarios still have thin/empty package knowledge; their `pilot/review-case.yaml` files include labeled synthetic `facts_for_review` for instructor pilot tests until authored.
- Metrics (factuality / coverage_opportunity / consistency / latency / cost) are stored on `requirements_draft_reviews` and usage ledger; cost is ~0 for heuristic.

## M4

- Symbol extraction is regex-based (Python/JS/TS), not Tree-sitter.
- PR listing is best-effort and not SHA-filtered to “PRs that touched this commit”.
- Background analyze uses FastAPI `BackgroundTasks` (in-process); not a durable worker queue.
- Full file bodies are stored in `index_json` within quota limits — large monorepos will skip files.

## M5

- Provisional scores are heuristic (length + concept overlap), not calibrated human-validated probabilities.
- Probe follow-ups are optional and single-step; no timed auto-advance clock UI yet (pause/resume exists).
- Question plans are deterministic templates over the index — not an LLM interview designer at runtime.
- Voice/video is optional M6; scoring remains text-only even when voice is used.

## M6

- LiveKit join requires `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. Without them, text mode and the configured external conferencing URL remain available.
- No managed LiveKit AI agent / TTS — students paste or correct STT text; utterances commit as ordinary answer text.
- Recording start/stop stores a **stub** egress id and playback path; real LiveKit Egress + object-storage playback is not implemented.
- Multi-party soak (cross-talk, reconnect, muted users) is not automated; API unit tests cover token mint, consent gate, and STT attribution.
- Scorer and utterance ingest reject accent / appearance / vocal-confidence cues.

## M7

- Production target is an **Easypanel App** built from the root `Dockerfile`, with `DATABASE_URL` supplied in env (separate Postgres service). No production Compose stack.
- This repo may still lack a git remote — Easypanel Git/GitHub source needs a reachable repository (or upload).
- Production image serves SPA + API on one service; TLS terminates at the Easypanel domain proxy on port **8000**.
- Usage quotas are daily UTC counters in Postgres; budget USD estimates are approximate (not invoice-grade).
- Retention days are **policy notices** plus checklist guidance; automated purge jobs are not yet scheduled.
- Monitoring counters are in-process (reset on deploy); wire an external APM when the pilot grows.
- Examiner calibration is a human worksheet (`docs/examiner-calibration.md`), not an automated agreement metric.
