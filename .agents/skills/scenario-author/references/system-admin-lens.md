# System-admin lens

Job titles in university interviews often **understate** the interviewee’s relationship to the software under discussion. Many “coordinators,” “advisors,” “heads,” and departmental staff are the people who **run, gatekeep, and configure** the target system.

## Default hypothesis

Unless the transcript clearly frames the speaker as an end user only (student, landlord applicant, supervisee, alumni member with no staff tools), hypothesize:

> This interviewee is a **system operator / admin** for the product being specified, even if their HR title is something else.

Confirm or reject that hypothesis with cues. If cues are ambiguous, raise a critical gap.

## Signals of system authority (from cues)

Treat these as strong operator signals:

- Approves, verifies, publishes, or rejects records others submit
- Assigns people to slots/courses/supervisors within policy/budget
- Manages registration hygiene, access gates, or eligibility
- Sends campaigns, exports packages, or produces oversight summaries
- Overrides conflicts, capacity, or default rules
- Describes “the system should let **me** …” for administrative control
- Speaks about what staff do to keep the platform trustworthy/closed

Treat these as end-user or hybrid signals:

- Submits requests that others must approve
- Consumes recommendations without configuring them
- Describes personal academic/research/landlord experience only
- Explicitly defers operational control to another office

## Persona modeling

Keep the **real organizational title** in `display_name` / role prose. Add explicit system authority:

```yaml
id: pg_coordinator
display_name: Postgraduate Coordinator
role: >-
  Department postgraduate coordinator who administers the thesis-tracking
  system: oversees pairings, monitors progress/feedback, escalates overdue
  items, and produces summaries for graduate studies.
system_role: platform_admin   # platform_admin | operator | approver | end_user | hybrid
admin_capabilities:
  - view_all_pairings
  - monitor_progress_and_feedback
  - flag_or_escalate_overdue_feedback
  - generate_progress_summaries
priorities:
  - Keep oversight of who supervises whom
  - Spot stalled feedback / progress early
  - Produce low-friction progress summaries for grad studies
```

### `system_role` values

| Value | Meaning |
| --- | --- |
| `platform_admin` | Primary staff operator; broad configure/approve/publish/oversight duties for this product |
| `operator` | Day-to-day runs queues, assignments, or monitoring without full policy ownership |
| `approver` | Gatekeeper for submissions; limited otherwise |
| `end_user` | Uses the product as a constituent (student, alumni, landlord, etc.) |
| `hybrid` | Both submits/uses as a peer **and** holds staff tools (rare; justify) |

### `admin_capabilities`

Use short snake_case verbs tied to in-system actions. Prefer capabilities that map to requirements/workflows already in the package or about to be added via assumptions.

## Knowledge modeling implications

When a persona is `platform_admin` / `operator` / `approver`:

- Requirements should separate **constituent actions** from **staff admin actions**
- Business rules should state who may approve / reject / override
- Workflows should include the admin queue step (submit → review → publish/assign)
- `known_fact_ids` should include those admin-side facts
- Referral rules should not send students to “an admin” if **this** persona is the admin — refer only truly external offices (HR, campus IT, grad studies policy, etc.)

## Anti-patterns

- Modeling HoD / coordinator / advisor as a vague “stakeholder voice” with no system verbs
- Renaming everyone `administrator` and losing domain identity
- Giving end-user personas publish/approve powers without transcript or instructor approval
- Leaving `uncertainty_policy` so broad that the admin persona refuses to discuss the queues they run
