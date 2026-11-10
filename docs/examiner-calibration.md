# Examiner calibration & bias checklist (M7)

Provisional scores from the text examiner are **not** final marks. Instructors must sample and compare.

## Calibration procedure

1. Run a mock exit interview with 3–4 participants on a known repo (`fixture://demo` is fine).
2. Independently score each student on the published COMP 3613 competencies (`special_feature_pattern`, `design_to_code`, `feature_ownership`, `testing`, `verification`) **without** looking at the AI report.
3. Unlock the provisional report and fill the table below.
4. Where disagreement is >1 band (e.g. human “high” vs AI “insufficient”), revise prompts/heuristics or prefer human override.

| Student | Competency | Human | AI provisional | Agree? | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

## Known heuristic limitations

- Length and keyword overlap reward verbose answers; short correct answers may look “low”.
- Code citation presence is checked weakly; verify citations manually.
- Hypothetical questions can inflate fluency without repo evidence — weight evidence links higher.
- Voice STT (M6) still grades **text only**; never infer confidence from typing speed, fluency, or delivery.

## Bias / fairness rules

- Do **not** grade on accent, appearance, or vocal confidence (enforced in scorer + voice ingest).
- Prefer evidence-linked answers over polished prose.
- When students use different IDE agents, score understanding and verification, not tool brand.
- Document overrides in reviewer notes for audit (`/ops/audit`).

## Prompt / bank revision log

| Date | Change | Reason |
| --- | --- | --- |
| 2026-11 | Initial M5 heuristic scorer shipped | Baseline |
| 2026-11 | M6 optional LiveKit + attributed STT; text-only scoring retained | Bias guard |

## Accessibility note

Text-only interviews remain available when LiveKit is unset. Low-bandwidth guidance lives in `/policy`.
