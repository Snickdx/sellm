# Critique — requirements chat run 2026-06-03T16:45:53Z

Transcript: `requirements_chat_20260603T164929Z.md` / `.json`

## Summary

| Turn | Mode requested | Mode used | Verdict |
|------|----------------|-----------|---------|
| 1 | vector | vector | Partial — on-topic but breaks role-play |
| 2 | vector | **coach** | **Fail** — wrong mode; not a stakeholder answer |
| 3 | vector | vector | Partial — repetitive; mislabels Employees |
| 4 | vector | vector | Partial — plausible but likely invented process |
| 5 | vector | vector | OK — reasonable concerns; repetitive |
| 6 | hybrid | coach | OK — correct auto-coach for "define" |
| 7 | coach | coach | OK — clear domain coaching |

## Turn-by-turn issues

### Turn 1 — Who's involved?

**Not helpful / unrealistic**

- Mentions "the person interviewing me" — breaks stakeholder role-play (meta, fourth wall).
- Says team members exist but "not really sure who they are" despite project materials in RAG.
- Calls **Employees** an "Employees department"; in this project Employees is a **user type** (people paid), not an org unit like Courts or Tax.

**What was OK**

- Names external parties (Courts, Tax, NI, Employer) consistent with the domain.

### Turn 2 — What are we trying to accomplish overall?

**Not helpful / unrealistic (critical)**

- Requested **vector** (stakeholder practice) but response used **coach** with Goal IDs (G3, G9, G13, G17) and interviewer bullet prompts — wrong persona and wrong mode.
- Root cause: coach detector treats `What are we…` like `What are the…` (regex matched `we` as the noun).

### Turn 3 — any other user types?

**Not helpful / unrealistic**

- Re-lists the same departments as Turn 1 without adding much (interviewer already heard this).
- Repeats "Employees department" mistake.

### Turn 4 — new admin user signs up

**Not helpful / unrealistic**

- Describes generic SaaS onboarding (welcome email, support portal, training demo) without grounding in project workbook — likely **hallucinated** if not in source docs.
- Stakeholder should stick to known project flows or say they are unsure of exact steps.

### Turn 5 — what worries you most?

**Mostly OK**

- Cost and legislation themes fit the materials.
- Still repeats full department list and ends with formulaic "Does that help?" (same as every turn).

### Turns 6–7 — coach queries

**OK** — appropriate coach voice and content; minor note that coach follow-ups mention KPIs (acceptable for coach mode).

## Changes to apply

1. **coach.py** — Narrow `what are` pattern; treat interviewer "we/our" goal questions as stakeholder practice, not coach.
2. **llm_wrapper.py** — Strengthen stakeholder prompt: stay in character, use project facts confidently, correct user-type naming, avoid inventing processes, vary closings.
3. **stakeholder_tone.py** / **behavior_tweaks.json** — Strip Goal `G\d+` labels from stakeholder output; block fourth-wall phrases; optional dedupe of repetitive department boilerplate.

## Re-test after fixes

Re-run: `requirements_chat_20260603T170156Z.md`

| Check | Result |
|-------|--------|
| Turn 2 uses vector (not coach) | Fixed |
| No Goal G codes / interviewer meta | Fixed |
| Turn 1 stakeholder role-play | Improved (Admin/HR/Employee naming) |
| Turn 5 worries question | **Still weak** — model pasted project intro instead of concerns; added prompt rule to answer risks directly |

Re-run again after server reload if Turn 5 still misbehaves.
