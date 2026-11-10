# Thesis Tracker exit transcript — high (Strong / gold-aligned)

Scenario: `thesis-tracker`  
SHA: `ttdeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Domain actions executed and audited» in Postgrad milestones, what inherited weakness did your team target?

**Student:** For domain actions executed and audited we targeted the optional mutable event_log in commands.py. Submissions skipped record, feedback used silent=True, and progress notes called rewrite_last before record. We replaced that with the Command pattern: Command objects plus an invoker that appends immutable command history for every successful action.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/feedback.py`, what design decision from your Sprint 1 class diagram for «Domain actions executed and audited» does this file embody?

**Student:** Sprint 1 class diagram showed Command participants for submit, feedback, and progress notes. Looking at feedback.py, submit_work now goes through the invoker instead of mutating then optionally logging. Design drift removed rewrite_last so command history stays append-only in commands.py.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `record` (`app/services/commands.py`) for «Domain actions executed and audited» or another task you owned?

**Student:** I personally implemented record in commands.py and wired submit_work plus complete_feedback. Control flow always appends actor and payload. Trello TT-01 and PR #7 are my commits. Failure mode: callers must not pass silent=True — that was how audit events disappeared in the starter.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Domain actions executed and audited» is this test protecting?

**Student:** tests/test_scenario.py is shallow and still passes with missing submission audit rows. I added a regression assertion that submit_work appends a command history entry, and another that add_note does not clobber the previous row. Coverage gap: coordinator overdue flag inversion.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/commands.py` for «Domain actions executed and audited»?

**Student:** AI drafted Command classes near commands.py. I verified by running audit regression tests, inspecting append-only history, and rejecting a patch that kept rewrite_last. PR #7 has my review; ownership stayed with me after that.
