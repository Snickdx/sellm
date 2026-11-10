---
name: scenario-validator
description: >-
  Validate sellm scenario packages for schema integrity, provenance, persona
  knowledge scopes, duplicate IDs, broken source refs, unapproved assumptions
  labeled authoritative, persona simulation consistency, and multi-mode index
  readiness (yaml/direct, vector, graph). Produces a readiness report. Use when
  validating scenarios, checking persona leakage, or before freezing an
  approved version in sellm.
compatibility: >-
  Requires sellm app modules under app/seproject/scenarios and scenarios/<slug>/.
  Reindex via POST /api/admin/scenarios/reindex or scripts/reindex_scenarios.py.
metadata:
  role: instructor-authoring
  owns: sellm
  mirrors: skill-library/skills/scenario-validator
---

# scenario-validator

Verify that a scenario package under **`sellm/scenarios/<slug>/`** is safe to load and (when intended) freeze for students.

## Absolute rules

1. Reject unapproved assumptions labeled `confirmed` or otherwise authoritative without instructor fields.
2. Reject broken persona `known_fact_ids`, missing source refs for `confirmed` facts, and duplicate IDs.
3. Never claim “approved for classroom” without instructor sign-off **and** a clean validation run.
4. Do not move `evaluation.yaml` / `gaps.yaml` content into student-facing artifacts.
5. Fix failures in **`sellm/`** data or validators; do not weaken checks by editing this skill’s installed copy.
6. After YAML fixes that change personas/facts, require a successful **reindex** so vector/graph/direct modes stay aligned.

## Checks to run

```bash
cd sellm
python -c "from pathlib import Path; from app.seproject.scenarios.loader import load_scenario_package; from app.seproject.scenarios.validator import validate_scenario_package; p=load_scenario_package(Path('scenarios/<slug>')); issues=validate_scenario_package(p); print('\n'.join(f'{i.severity}: {i.code}: {i.message}' for i in issues) or 'OK')"
```

Optional reindex (required before claiming runtime-ready):

```bash
python scripts/reindex_scenarios.py
# or POST /api/admin/scenarios/reindex
```

Manual / agent review (see [references/checklist.md](references/checklist.md)):

- Every `confirmed` fact has ≥1 valid `source_refs` pointing at an existing cue
- `assumed` facts have `decision_id`, `approved_by`, `approved_at`, `rationale`
- Persona IDs are unique; every `known_fact_ids` entry resolves
- `system_role` / `admin_capabilities` present when the persona operates the system
- No student-facing file embeds evaluation rubrics or gap answer keys
- High-impact `unresolved` / `conflicting` items are listed in the readiness report
- Simulation: paraphrases stay consistent; unknowns admit uncertainty; cross-persona private facts stay private
- Indexes refreshed after the latest YAML edit

## Readiness report template

```markdown
# Readiness: <slug> @ <version>

## Automated
- validate_scenario: PASS|FAIL
- reindex: PASS|FAIL|SKIPPED (vector_docs=N, neo4j_edges=M)

## Provenance
- cues: N (ambiguous speakers: M)
- confirmed / clarified / assumed / unresolved / conflicting: …

## Personas
- list + fact counts + system_role + referral rules present?

## Open gaps
- critical: …
- important: …

## Freeze decision
- instructor_approved: yes|no
- notes: …
```

## Out of scope

Do not author new transcript facts here (use **scenario-author**). Do not implement chat UI.
