# Instructor gap batch protocol

## Batch size

Ask **at most five** targeted questions per batch. Persist answers before starting another batch.

## Question shape

Every question should be answerable with `accept` / `modify` / `reject` / `defer` and should include a **suggested assumption** the instructor can approve as-is.

```yaml
id: GAP-LIB-003
priority: critical   # critical | important | optional
theme: exception_path  # optional: system_authority | approval_power | exception_path | visibility | config_default | elicitation_boundary
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

### Depth-oriented themes

Prefer these when fine-tuning shallow packages:

| Theme | Example prompt focus |
| --- | --- |
| `system_authority` | Is this interviewee the system operator despite their HR title? |
| `approval_power` | Who approves/publishes/assigns/rejects, and what are the queues? |
| `exception_path` | Reject, expire, escalate, cancel, override |
| `visibility` | What can each role see about others’ data? |
| `config_default` | Caps, defaults, hard constraints the admin enforces |
| `elicitation_boundary` | What must stay unknown so students still have work? |

### Writing stronger questions

- Cite cues or say **no coverage** explicitly.
- Tie `why_it_matters` to persona realism **and** student elicitation design.
- Offer alternatives that include at least one **admin-aware** option when the interviewee likely operates the system.
- Make `suggested_assumption` a single ready-to-file statement (actors + verbs + boundary of what stays deferred).
- Do **not** auto-apply `recommended_default` or `suggested_assumption`.

## Decision record

```yaml
decision_id: DEC-LIB-003
gap_id: GAP-LIB-003
action: accept   # accept | modify | reject | defer
chosen: Lecturers only, up to 24h before start
modified_text: null
rationale: Aligns with capacity planning need stated in cue-0012.
approved_by: instructor@example.com
approved_at: "2026-11-02T12:00:00Z"
resulting_fact_ids: [LIB-REQ-014, LIB-ASM-00x]
```

When `action: accept` and the instructor adopts the suggested assumption (or a modification), create/update the corresponding `assumed` / `clarified` knowledge records and patch personas/workflows in the same turn.

When the instructor says **“apply recommended defaults for this batch”**, treat each question’s `recommended_default` + `suggested_assumption` as accepted unless they singled one out — still write decision records for each.

## Resume

On resume: load `gaps.yaml`, skip decided IDs, continue with the next undecided `critical` then `important` gaps (still ≤ 5). For depth-update mode, prefer undecided gaps with themes `system_authority` and `approval_power` first.
