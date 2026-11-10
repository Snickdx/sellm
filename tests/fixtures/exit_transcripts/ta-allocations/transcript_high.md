# Ta Allocations exit transcript — high (Strong / gold-aligned)

Scenario: `ta-allocations`  
SHA: `tadeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Auto-allocation ranking modes» in TA allocation, what inherited weakness did your team target?

**Student:** For auto-allocation ranking modes we targeted the nested mode switch in strategies.py. experience_first hard-filtered the pool, least_loaded and round_robin skipped the weekly cap, and unknown modes fell back to the first TA. We replaced that with the Strategy pattern: ranking strategies behind one interface while hard 20h and budget guards stay outside ranking.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/allocations.py`, what design decision from your Sprint 1 class diagram for «Auto-allocation ranking modes» does this file embody?

**Student:** Sprint 1 class diagram showed Strategy participants for experience_first, least_loaded, and round_robin. Looking at allocations.py, assign_manual now enforces weekly cap before insert. Design drift moved ranking into strategies.py so capacity guards are not buried inside stringly mode branches.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `assign_manual` (`app/services/allocations.py`) for «Auto-allocation ranking modes» or another task you owned?

**Student:** I personally rewrote auto_select_ta in strategies.py and fixed assign_manual over-cap inserts in allocations.py. Control flow rejects over 20h and over budget. Trello TA-02 and PR #4 are my commits. Failure mode: empty experienced pool must soft-fall back, not hard-error.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Auto-allocation ranking modes» is this test protecting?

**Student:** tests/test_scenario.py is shallow and still passes when manual assign exceeds the weekly cap. I added a regression assertion that over-cap assign_manual raises, and another that least_loaded never projects above WEEKLY_HOUR_CAP. Coverage gap: unknown mode must not silently pick the first TA.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/strategies.py` for «Auto-allocation ranking modes»?

**Student:** AI drafted Strategy classes in strategies.py. I verified with cap/budget regression tests and rejected a patch that kept experience as a hard filter. PR #4 has my review; ownership stayed with me after that review.
