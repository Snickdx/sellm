# Career Advising exit transcript — mid (Partial / vague (length without gold terms))

Scenario: `career-advising`  
SHA: `cadeadbeef01`  
Expected provisional score range: [3, 4]

## Q1. `special_feature_pattern`

**Examiner:** For «Exploration / advising pipelines» in Career advising, what inherited weakness did your team target?

**Student:** The two advising modes felt copy-pasted and inconsistent in the starter. I said we cleaned those paths, but I cannot name the classes we added or the approach we chose.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/advising.py`, what design decision from your Sprint 1 class diagram for «Exploration / advising pipelines» does this file embody?

**Student:** Sprint one boxes on the whiteboard roughly match what shipped later. Some names moved around when we coded, and I am not sure which relationship stayed faithful versus what we reinvented under pressure.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `explore_career_first` (`app/services/exploration.py`) for «Exploration / advising pipelines» or another task you owned?

**Student:** I made a few edits in the main service path after standup. I cannot find my board card and I did not write down what callers should do when the insert fails.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Exploration / advising pipelines» is this test protecting?

**Student:** The starter suite checks login and counts rows. That is thin for both advising modes and missing prerequisites, so we planned richer cases later but did not land them before the interview.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/exploration.py` for «Exploration / advising pipelines»?

**Student:** A classmate pushed a big branch and I skimmed it before merge. I trusted the chat summary more than running the app myself, so my check was shallow.
