# Job Board exit transcript — mid (Partial / vague (length without gold terms))

Scenario: `job-board`  
SHA: `jbdeadbeef01`  
Expected provisional score range: [3, 4]

## Q1. `special_feature_pattern`

**Examiner:** For «Application lifecycle / transitions» in Job board, what inherited weakness did your team target?

**Student:** Applications could move into weird statuses in the starter. I told the team we cleaned that path, but I cannot name the classes we introduced or the approach we settled on.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/applications.py`, what design decision from your Sprint 1 class diagram for «Application lifecycle / transitions» does this file embody?

**Student:** Sprint one boxes on the whiteboard roughly match what shipped later. Some names moved around when we coded, and I am not sure which relationship stayed faithful versus what we reinvented under pressure.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `transition_application` (`app/services/applications.py`) for «Application lifecycle / transitions» or another task you owned?

**Student:** I made a few edits in the main service path after standup. I cannot find my board card and I did not write down what callers should do when the insert fails.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Application lifecycle / transitions» is this test protecting?

**Student:** The starter suite checks login and list length. That is thin for how applications move between statuses, so we planned richer cases later but did not land them before the interview.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/lifecycle.py` for «Application lifecycle / transitions»?

**Student:** A classmate pushed a big branch and I skimmed it before merge. I trusted the chat summary more than running the app myself, so my check was shallow.
