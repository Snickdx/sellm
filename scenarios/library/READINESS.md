# Readiness: library @ 0.1.0

## Automated

- validate_scenario: run `python scripts/validate_scenario.py scenarios/library`
- simulate_personas: run `python scripts/simulate_personas.py scenarios/library`

## Provenance

- Source: `sources/library-synthetic.vtt` (**SYNTHETIC_PILOT**, not a real interview)
- Confirmed transcript-linked facts for booking request, required fields, conflict rule, confirmation/cancel need, capacity
- One instructor-approved assumption: default capacity 30 (`LIB-ASM-001` / `DEC-LIB-001`)

## Personas

- `library_coordinator`, `lecturer`, `administrator` with scoped `known_fact_ids`

## Open gaps

- important: `GAP-LIB-001` cancellation deadline (deliberately left open for elicitation)

## Freeze decision

- instructor_approved: yes (synthetic pilot only)
- notes: Replace with real VTT before classroom use; keep synthetic labeling until then.
