# Library exit transcript — high (Strong / gold-aligned)

Scenario: `library`  
SHA: `libdeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Same-slot conflict resolution» in Library workshop booking, what inherited weakness did your team target?

**Student:** For same-slot conflict resolution we targeted the inherited nested resolve_slot_request in conflicts.py. Capacity was checked per request only so rooms overbooked, earlier-request-wins was inverted, and larger cohorts auto-overrode without a coordinator flag. We replaced that with the Strategy pattern: CapacityGuard, EarlierRequestWins, and LargerCohortOverride as separate policies composing around the slot.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/bookings.py`, what design decision from your Sprint 1 class diagram for «Same-slot conflict resolution» does this file embody?

**Student:** In the Sprint 1 class diagram we drew Strategy participants for capacity and conflict policies. Looking at app/services/bookings.py, request_booking still creates the booking then should hand off to conflicts strategies. During Sprint 2 we refactored so bookings no longer embeds nested slot rules — that design drift was intentional to keep strategy participants in conflicts.py instead of duplicating capacity checks here.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `request_booking` (`app/services/bookings.py`) for «Same-slot conflict resolution» or another task you owned?

**Student:** I personally rewrote request_booking in app/services/bookings.py so incomplete bookings are rejected and new lecturer requests stay pending for coordinator review. Control flow now validates course_code and resources, then inserts pending. Trello card LIB-12 and PR #18 on main show my commits. Callers must handle ValidationError when course_code is empty — that was the failure mode we missed in the starter, and cancelled bookings no longer count as active in conflicts.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Same-slot conflict resolution» is this test protecting?

**Student:** tests/test_scenario.py only asserts shallow health and list length, so it still passes with overbook defects. For same-slot conflict resolution I added a regression assertion that two accepted bookings cannot exceed room capacity on the same slot, and another that earlier-request-wins keeps the first pending request when headcounts tie. The important missing gap was cancelled bookings still blocking the slot — next test should cover that.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/conflicts.py` for «Same-slot conflict resolution»?

**Student:** AI drafted the first Strategy extract near conflicts.py. I personally verified by running the capacity regression tests, walking resolve_slot_request on paper, and rejecting an agent patch that dropped the coordinator override flag. PR #18 on main has my review comments; I refuse agent code without tests for overbook and cancelled-slot cases. Ownership stayed with me after that review.
