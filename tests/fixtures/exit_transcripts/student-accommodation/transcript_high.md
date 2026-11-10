# Student Accommodation exit transcript — high (Strong / gold-aligned)

Scenario: `student-accommodation`  
SHA: `sadeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Listing lifecycle / transitions» in Student housing, what inherited weakness did your team target?

**Student:** For listing lifecycle transitions we targeted the status-plus-flags soup in lifecycle.py. Activate from pending skipped verify, visible_to_students trusted flag_active alone, and resubmit left rejected. We replaced that with the State pattern: pending → verified → active|inactive with an explicit transition table.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/listings.py`, what design decision from your Sprint 1 class diagram for «Listing lifecycle / transitions» does this file embody?

**Student:** Sprint 1 class diagram showed State participants for listing statuses. Looking at listings.py, transition now calls lifecycle apply_action instead of flipping flags. Design drift moved visibility rules into visible_to_students so students never see pending or rejected posts.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `apply_action` (`app/services/lifecycle.py`) for «Listing lifecycle / transitions» or another task you owned?

**Student:** I personally rewrote apply_action and visible_to_students in lifecycle.py. Control flow blocks activate from pending. Trello SA-01 and PR #5 are my commits. Failure mode: landlords without ownership must get ForbiddenError on transition — that was missing in the starter.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Listing lifecycle / transitions» is this test protecting?

**Student:** tests/test_scenario.py is shallow and still passes when pending listings are student-visible. I added a regression assertion that activate from pending raises, and another that flag_active alone does not make a pending listing visible. Coverage gap: area restriction to St. Augustine / Mount Hope.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/lifecycle.py` for «Listing lifecycle / transitions»?

**Student:** AI drafted the State extract in lifecycle.py. I verified with visibility regression tests and rejected a patch that re-enabled activate-from-pending. PR #5 has my review; ownership stayed with me after that review.
