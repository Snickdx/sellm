# Depth-update (fine-tune) workflow

Use when an existing `scenarios/<slug>/` package is approved or drafted but **thin**: shallow briefs, title-only personas, happy-path-only workflows, or interviewees who clearly operate the system but are modeled as passive domain voices.

## Goals

1. Enrich context students can elicit without fabricating transcript quotes.
2. Correct understated **system-admin / operator** authority.
3. **Prescribe** reasonably inferable SRS / depth scaffolding by default; open a verify/change path.
4. Close **IEEE / 29148 SRS-shaped** holes (Features, Goals, Assumptions, Interfaces, Data, Use cases, Quality, Verification) using [ieee-srs-coverage.md](ieee-srs-coverage.md).
5. Preserve provenance: never re-label unsupported content as `confirmed`.

## Procedure

### A. Load and inventory

Read, in order:

1. `scenario.yaml` (version, status, brief)
2. All `personas/*.yaml`
3. `knowledge/*.yaml` + `gaps.yaml` + `evaluation.yaml`
4. `normalized/cues.jsonl` (or re-parse VTTs if missing/stale)

Produce a short inventory: persona count, fact counts by status, open gaps, open `srs_prescription` items, and which personas look like system operators.

### B. Depth audit

Run the depth checklist in `SKILL.md`. For each thin/missing area, decide:

- **Prescribe now** if an LLM can reasonably infer it from brief + cues + existing facts (Features, Goals, remaps, interfaces/data, trace links, light quality/verification).
- **Ask-first** only for non-inferable policy (numeric SLAs, who-wins conflicts, elicitation boundaries).

Prioritize:

1. Mis-modeled system authority (critical — often ask-first if ambiguous; else prescribe `system_role` / capabilities with verify)
2. Missing approve/publish/override/audit powers (critical)
3. Missing Goals / Features / FR→Feature `satisfies_ids` (**prescribe by default**)
4. Exception paths and state transitions (important — prescribe when cues imply; else ask-first)
5. Interfaces, data entities, dependencies (**prescribe by default** when obvious)
6. `ASM-*` still tagged `constraint` instead of `assumption` (**prescribe remap**)
7. Cross-role visibility / privacy / security NFRs (important — prescribe lightly when cues support)
8. Use-case shaping of workflows; verification methods (prescribe when clear)
9. NFR polish and optional colour (optional)

### C. Prescribe, then verify batch (≤ 5)

1. Patch knowledge/personas with prescriptions (`clarified`, `origin: instructor`, rationale starts with `Prescribed during authoring;`).
2. Open/refresh `gaps.yaml` clusters with `theme: srs_prescription` covering what you wrote.
3. Present the Prescription review (verify_accept / modify / reject / defer). Honor “verify all prescriptions”.
4. Only then (or in parallel if room in the batch) ask ask-first gaps for non-inferable items.

After each batch, persist decisions in `gaps.yaml` before the next batch.

### D. Patch package (from verify / ask-first outcomes)

For each accepted or modified decision:

1. Keep, rewrite, or remove prescribed knowledge records; on `verify_accept` of pure world-assumptions, upgrade to `assumed` + decision provenance.
2. Prefer dedicated categories/prefixes from ieee-srs-coverage (`FEAT`, `GOAL`, `ASM`+`assumption`, `DEP`, `IF`, `DATA`, `UC`, quality/verification).
3. Wire / repair trace links: `satisfies_ids`, `derives_from_ids`, `depends_on_ids`.
4. Enrich persona `role`, `system_role`, `admin_capabilities`, priorities, `known_fact_ids` (include new GOAL/FEAT/IF/DATA ids), referral rules.
5. Extend workflows / use cases with exception/override steps when prescribed or approved.
6. Adjust `evaluation.yaml` oracle expectations if admin-aware or SRS-shaped elicitation is now in scope.
7. Update `scenario.yaml` brief/`source_notes` (purpose, scope, primary users); **bump `version`**; set `status: draft` until re-approval unless instructor keeps approval.

Do **not**:

- Rewrite `confirmed` transcript statements to say something the cue does not support
- Rename display titles to generic “Admin” solely for convenience
- Hold inferable Features/Goals/Interfaces for a pre-write interview
- Auto-apply **ask-first** `recommended_default` without an instructor action (verify shortcuts for prescriptions are OK)

### E. Validate, reindex, and report

Run validate (or **scenario-validator**). Then **reindex** so vector, graph, and yaml/direct preprompt modes match the patched YAML:

- `POST /api/admin/scenarios/reindex` when the sellm server is running, or
- `python scripts/reindex_scenarios.py`

Emit the readiness report with mode `depth-update`, prescription/verify counts, checklist summary, reindex counts, and approval state.

## Multi-scenario fine-tune

When the instructor asks to deepen **all** scenarios:

1. Process **one slug at a time**.
2. Start each slug with a one-paragraph audit, prescribe inferable SRS, then first verify/ask batch (≤ 5).
3. Do not leave a slug without prescriptions written when they are reasonably inferable — verify can follow in the same turn.
4. Carry forward only **pattern-level** lessons (e.g. “coordinators are usually operators”) — still ground per package with citations or prescriptions + verify.

## Suggested-assumption hygiene

A good suggested assumption (and a good prescription statement) is:

- Single decision, testable in chat
- Named actors and system verbs (approve, publish, assign, reject…)
- Explicit about what remains for student elicitation
- For prescriptions already in YAML: matches the live statement so verify_accept is a no-op edit
- Labeled ready for `status: assumed` + decision provenance if the instructor upgrades it on verify
