# uwi-connect readiness

| Metric | Value |
| --- | --- |
| Version / status | **0.2.0 / approved** (`approved_by: instructor`, 2026-11-10) |
| Mode | depth-update from 0.1.0 |
| Sources / cues | 1 VTT; 482 cues |
| Personas | alumni_admin (`platform_admin`) |
| Facts | confirmed + clarified/assumed through DEC-UC-010 |
| Open critical gaps | none (DEC-UC-001..010 decided) |
| validate_scenario | pass |
| reindex | 7 packages / **272** vector docs |

## Depth 0.2.0

- DEC-UC-006: `platform_admin`
- DEC-UC-007: reject/unpublish + in-system notify
- DEC-UC-008: revoke anytime → lose boards + campaigns
- DEC-UC-009: campaign audience = all verified non-revoked
- DEC-UC-010: pending visibility (admin queue / own status / others published-only)

## Scope freeze

- Chatbot: `alumni_admin` only
- UWI-email verification gate; alumni browse jobs/events; submit → admin publish
- Full email campaign builder; audience = verified non-revoked
- Directory / mentorship / messaging / groups out of graded MVP
- Do not silently mutate this approved version — bump version for later changes.
