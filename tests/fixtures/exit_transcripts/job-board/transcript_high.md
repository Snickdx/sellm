# Job Board exit transcript — high (Strong / gold-aligned)

Scenario: `job-board`  
SHA: `jbdeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Application lifecycle / transitions» in Job board, what inherited weakness did your team target?

**Student:** For application lifecycle transitions we targeted the inherited flag-plus-status soup in lifecycle.py. Nested if/elif allowed illegal moves like submit to hire and reject to shortlist, and derived_status_from_flags disagreed with status. We replaced that with the State pattern: one state object per status and an explicit transition table so only legal moves remain.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/applications.py`, what design decision from your Sprint 1 class diagram for «Application lifecycle / transitions» does this file embody?

**Student:** Sprint 1 class diagram showed State participants for pending, shortlisted, hired, and rejected. Looking at applications.py, transition_application now delegates to lifecycle apply_action instead of flipping four boolean flags. That design drift was intentional so pattern participants live in lifecycle.py rather than scattering status strings across listings and applications.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `transition_application` (`app/services/applications.py`) for «Application lifecycle / transitions» or another task you owned?

**Student:** I personally rewrote apply_action in app/services/lifecycle.py and wired transition_application in applications.py. Control flow rejects illegal transitions and clears terminal flags on reopen. Trello JB-06 and PR #11 on main are my commits. Callers must handle IllegalTransitionError — that failure mode was missing when hire after reject still succeeded in the starter.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Application lifecycle / transitions» is this test protecting?

**Student:** tests/test_scenario.py only checks shallow health and list length, so it still passes with illegal lifecycle transitions. I added a regression assertion that reject then shortlist raises, and another that hire is unreachable from submitted without shortlist. Coverage gap remaining: IDOR on listing_applicants.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/lifecycle.py` for «Application lifecycle / transitions»?

**Student:** AI drafted the first State extract near lifecycle.py. I verified by running transition regression tests, walking the transition table on paper, and rejecting an agent patch that left flag_hired set after reopen. PR #11 has my review; I refuse agent code without tests for illegal transitions. Ownership stayed with me.
