# Depth-update (fine-tune) workflow

Use when an existing `scenarios/<slug>/` package is approved or drafted but **thin**: shallow briefs, title-only personas, happy-path-only workflows, or interviewees who clearly operate the system but are modeled as passive domain voices.

## Goals

1. Enrich context students can elicit without fabricating transcript quotes.
2. Correct understated **system-admin / operator** authority.
3. Fill critical holes via instructor-approved `assumed` / `clarified` facts.
4. Preserve provenance: never re-label unsupported content as `confirmed`.

## Procedure

### A. Load and inventory

Read, in order:

1. `scenario.yaml` (version, status, brief)
2. All `personas/*.yaml`
3. `knowledge/*.yaml` + `gaps.yaml` + `evaluation.yaml`
4. `normalized/cues.jsonl` (or re-parse VTTs if missing/stale)

Produce a short inventory: persona count, fact counts by status, open gaps, and which personas look like system operators.

### B. Depth audit

Run the depth checklist in `SKILL.md`. For each thin/missing area, draft a gap candidate with:

- evidence from cues **or** explicit “no coverage”
- impact on student elicitation / persona realism
- 2–4 alternatives
- a **suggested assumption** ready for accept

Prioritize:

1. Mis-modeled system authority (critical)
2. Missing approve/publish/override/audit powers (critical)
3. Exception paths and state transitions (important)
4. Cross-role visibility / privacy (important)
5. NFR polish and optional colour (optional)

### C. Instructor batches (≤ 5)

Ask only the highest-leverage undecided gaps. Prefer questions that unlock many downstream fact/persona edits.

After each batch, persist decisions in `gaps.yaml` before the next batch.

### D. Patch package

For each accepted decision:

1. Add or revise knowledge records (`clarified` / `assumed`, `origin: instructor`, decision provenance on assumptions).
2. Enrich persona `role`, `system_role`, `admin_capabilities`, priorities, `known_fact_ids`, referral rules.
3. Extend workflows with exception/override steps when approved.
4. Adjust `evaluation.yaml` oracle expectations if admin-aware elicitation is now in scope.
5. Update `scenario.yaml` brief/`source_notes`; **bump `version`**; set `status: draft` until re-approval unless instructor keeps approval.

Do **not**:

- Rewrite `confirmed` transcript statements to say something the cue does not support
- Rename display titles to generic “Admin” solely for convenience
- Auto-apply suggested assumptions without an instructor action

### E. Validate, reindex, and report

Run validate (or **scenario-validator**). Then **reindex** so vector, graph, and yaml/direct preprompt modes match the patched YAML:

- `POST /api/admin/scenarios/reindex` when the sellm server is running, or
- `python scripts/reindex_scenarios.py`

Emit the readiness report with mode `depth-update`, checklist summary, reindex counts, and approval state.

## Multi-scenario fine-tune

When the instructor asks to deepen **all** scenarios:

1. Process **one slug at a time**.
2. Start each slug with a one-paragraph audit + first gap batch (≤ 5).
3. Do not patch YAML for a slug until that slug’s current batch is decided (or the instructor says “apply recommended defaults for this batch”).
4. Carry forward only **pattern-level** lessons (e.g. “coordinators are usually operators”) — still confirm per package with citations or assumptions.

## Suggested-assumption hygiene

A good suggested assumption is:

- Single decision, testable in chat
- Named actors and system verbs (approve, publish, assign, reject…)
- Explicit about what remains for student elicitation
- Labeled ready for `status: assumed` + decision provenance if accepted
