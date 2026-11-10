# Knowledge and persona record shapes

Illustrative only — not a claim about any real interview.

## Confirmed requirement

```yaml
id: LIB-REQ-001
statement: Lecturers can request workshop bookings for their classes.
category: functional
status: confirmed
origin: transcript
source_refs:
  - file: sources/library-synthetic.vtt
    cue_id: cue-0004
    start: "00:00:18.000"
    end: "00:00:26.000"
    speaker: coordinator
known_by: [library_coordinator]
disclosure: when_relevant
acceptance_criteria:
  - A lecturer can submit a valid workshop booking request.
```

## Assumed (instructor-approved synthetic)

```yaml
id: LIB-ASM-001
statement: Maximum workshop capacity defaults to 30 unless overridden.
category: constraint
status: assumed
origin: instructor
decision_id: DEC-LIB-002
approved_by: instructor@example.com
approved_at: "2026-11-02T12:00:00Z"
rationale: Needed for conflict checks; not stated in transcript.
known_by: [library_coordinator, administrator]
disclosure: when_asked
```

## Status vs origin

- `status` = epistemic standing (`confirmed`, `clarified`, `assumed`, `unresolved`, `conflicting`)
- `origin` = who authored the record (`transcript` | `instructor`)
- Never label unsupported content `confirmed`

## Persona with system-admin lens

Keep the organizational title; make in-system authority explicit.

```yaml
id: library_coordinator
display_name: Library Workshop Coordinator
role: >-
  Library staff member who administers the workshop booking system: collects
  booking details, prevents double-booking, applies conflict preferences, and
  escalates capacity disputes.
system_role: platform_admin
admin_capabilities:
  - review_booking_requests
  - prevent_double_booking
  - apply_conflict_preference_rules
  - override_for_larger_cohorts
priorities:
  - Avoid double-booking rooms
  - Collect course code, headcount, date, and resource topics
  - Prefer earlier requests when slots conflict, with override for larger cohorts
communication_style: Practical, concise, flags uncertainty about cancellation deadlines
known_fact_ids:
  - LIB-REQ-001
  - LIB-REQ-002
  - LIB-BR-001
  - LIB-ASM-001
uncertainty_policy: Admit unknowns; do not invent institutional policy beyond approved facts.
referral_rules:
  - Refer formal estate/room-ownership policy disputes to campus facilities / administrator
  - Refer pedagogical content choices to the requesting lecturer
```

### Separating constituent vs admin requirements

Prefer distinct statements when both exist:

```yaml
# constituent
statement: Lecturers submit workshop booking requests with course code, headcount, date, and topics.

# admin / operator
statement: The library coordinator reviews requests, blocks double-bookings, and may override conflicts for larger cohorts.
```

Both may be `confirmed` only with transcript support; otherwise use instructor `clarified` / `assumed` after a gap decision.
