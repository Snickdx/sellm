# Instructor operations checklist

sellm-hosted COMP 3613 pilot ops. Prefer `docs/EXIT_INTERVIEWS.md` for the exit-interview dry-run.

## Before Week 1

- [ ] Deploy sellm (bare-metal `scripts/update` / systemd, or Docker / EasyPanel from this repo).
- [ ] Confirm `/api/health` is OK; scenarios seed from `scenarios/`.
- [ ] Create admin user; seed cohort credentials (`setup/users/`).
- [ ] Create teams in **Admin → Teams**; attach owner cohort usernames + scenario slugs.
- [ ] Configure LLM: Ollama and/or platform OpenAI keys in Admin → Keys; set student default model.
- [ ] Optional: `GITHUB_TOKEN` for private student repos.
- [ ] Optional voice: LiveKit env vars (see `docs/EXIT_INTERVIEWS.md`).
- [ ] Confirm private gold is present: `instructor/private/<slug>/` and `app/course/examiner/knowledge/<slug>.yaml`.

## Daily pilot ops

- [ ] Spot-check Admin → Tokens / Keys when students hit budget.
- [ ] Do **not** expose `gaps.yaml` / `evaluation.yaml` / `instructor/private/` to students.

## Exit interview marking

- [ ] Freeze repo at SHA; wait for index `ready`.
- [ ] Create session; every participant gives consent.
- [ ] After finish, review provisional reports; override when human judgment disagrees.
- [ ] Never grade accent, appearance, or vocal confidence.
- [ ] Use `docs/examiner-calibration.md` for spot calibration.

## Defect / pattern gold

| Asset | Role |
| --- | --- |
| `instructor/private/<slug>/defect-manifest.yaml` | Authoring SoT (defects + intended pattern) |
| `instructor/private/<slug>/tests/` | Hidden regression vs sibling `templates/<slug>/` |
| `app/course/examiner/knowledge/<slug>.yaml` | Runtime judge packs |

After editing a manifest, update the matching knowledge YAML so provisional scoring stays accurate.
