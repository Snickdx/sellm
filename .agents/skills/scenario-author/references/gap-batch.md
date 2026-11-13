# Instructor gap batch protocol

## Batch size

Ask **at most five** targeted items per batch (verify clusters and/or ask-first gaps). Persist answers before starting another batch.

Two paths:

| Path | When | Actions |
| --- | --- | --- |
| **Verify / change** | SRS (or depth) content was **already prescribed** into YAML | `verify_accept` / `modify` / `reject` / `defer` |
| **Ask-first** | Non-inferable policy; nothing written yet | `accept` / `modify` / `reject` / `defer` |

## Verify / change shape (default for SRS prescriptions)

Facts are already in `knowledge/*.yaml`. The gap reviews a **cluster**, not a blank slate.

```yaml
id: GAP-LIB-SRS-001
priority: important
theme: srs_prescription
prompt: |
  Verify prescribed Features + FR satisfies links for workshop booking.
citations:
  - file: sources/library-synthetic.vtt
    cue_id: cue-0004
    note: lecturers request bookings; structural Feature clustered from FRs
why_it_matters: Students need named product functions and graph SATISFIES edges.
prescribed_fact_ids: [LIB-FEAT-001, LIB-REQ-001, LIB-REQ-002]
suggested_assumption: |
  (Already in YAML) Workshop booking request and confirmation for lecturers
  is a first-class Feature; LIB-REQ-001/002 satisfy LIB-FEAT-001.
recommended_default: Keep prescribed Feature and satisfies_ids as written.
alternatives:
  - Keep as prescribed
  - Merge into a broader “Scheduling” Feature
  - Reject Feature nodes; leave flat FRs only
  - Defer review; keep prescription in package
actions: [verify_accept, modify, reject, defer]
```

### Verify outcomes

| Action | Effect |
| --- | --- |
| `verify_accept` | Keep facts; close gap. Optionally upgrade pure world-assumptions to `assumed` + decision provenance |
| `modify` | Rewrite statements/links/categories per instructor text; keep IDs when possible |
| `reject` | Remove prescribed facts; repair dangling `satisfies_ids` / `known_fact_ids` / persona refs |
| `defer` | Leave facts and gap open |

Shortcuts (still write one decision per gap):

- “verify all prescriptions” / “accept all SRS prescriptions”
- “apply recommended defaults for this batch” (also covers ask-first items in the batch)

## Ask-first question shape

Use when the model should **not** prescribe yet (numeric policy, contradictions, elicitation boundaries).

```yaml
id: GAP-LIB-003
priority: critical   # critical | important | optional
theme: exception_path  # system_authority | approval_power | exception_path | visibility | config_default | elicitation_boundary
prompt: |
  Who may cancel a confirmed workshop booking, and until when?
citations:
  - file: sources/library-synthetic.vtt
    cue_id: cue-0012
    note: stakeholder mentioned cancellations without a deadline
why_it_matters: Affects state machine, notifications, fairness tests, and admin override realism.
alternatives:
  - Lecturers only, up to 24h before start
  - Lecturers or librarian, up to 2h before start
  - Librarian only at any time
  - Defer — leave unresolved for student elicitation
recommended_default: Lecturers only, up to 24h before start
suggested_assumption: |
  Lecturers may cancel their own confirmed workshop booking up to 24 hours
  before start; the library coordinator may override/cancel at any time for
  operational reasons. Exact notification copy remains student elicitation.
actions: [accept, modify, reject, defer]
```

Do **not** auto-apply ask-first `recommended_default` / `suggested_assumption` until the instructor acts (or uses a batch shortcut).

### Depth-oriented themes

| Theme | Example prompt focus |
| --- | --- |
| `srs_prescription` | Verify Features, Goals, Interfaces, Data, remaps, trace links already written |
| `system_authority` | Is this interviewee the system operator despite their HR title? |
| `approval_power` | Who approves/publishes/assigns/rejects, and what are the queues? |
| `exception_path` | Reject, expire, escalate, cancel, override |
| `visibility` | What can each role see about others’ data? |
| `config_default` | Caps, defaults, hard constraints the admin enforces |
| `elicitation_boundary` | What must stay unknown so students still have work? |

### Writing stronger items

- Cite cues or say **no coverage** explicitly.
- Tie `why_it_matters` to persona realism **and** student elicitation design.
- For verify clusters, list `prescribed_fact_ids` and make `suggested_assumption` match live YAML.
- Offer alternatives that include at least one **admin-aware** option when the interviewee likely operates the system.
- Prefer verify clusters for inferable SRS; reserve ask-first for true unknowns.

## Decision record

```yaml
decision_id: DEC-LIB-003
gap_id: GAP-LIB-003
action: verify_accept   # verify_accept | accept | modify | reject | defer
chosen: Keep prescribed Feature and satisfies_ids as written
modified_text: null
rationale: Matches cue-0004 booking flow; Feature clustering is appropriate.
approved_by: instructor@example.com
approved_at: "2026-11-02T12:00:00Z"
resulting_fact_ids: [LIB-FEAT-001, LIB-REQ-001, LIB-REQ-002]
```

When `action: accept` (ask-first) or `verify_accept` / `modify`, create/update the corresponding knowledge records and patch personas/workflows in the same turn.

## Resume

On resume: load `gaps.yaml`, skip decided IDs, continue with undecided `critical` then `important` (still ≤ 5). Prefer open `srs_prescription` verify clusters, then `system_authority` / `approval_power`, then other ask-first gaps.
