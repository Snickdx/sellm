# Career Advising exit transcript — high (Strong / gold-aligned)

Scenario: `career-advising`  
SHA: `cadeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Exploration / advising pipelines» in Career advising, what inherited weakness did your team target?

**Student:** For exploration advising pipelines we targeted duplicated career-first and course-first flows in exploration.py. Ranking used absolute wording and course-first skipped missing-course identification. We replaced that with the Template Method pattern: a shared skeleton with mode-specific hooks for match, non-absolute rank, identify gaps, and present.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/advising.py`, what design decision from your Sprint 1 class diagram for «Exploration / advising pipelines» does this file embody?

**Student:** Sprint 1 class diagram showed Template Method participants for the shared pipeline. Looking at exploration.py, both modes now call the same skeleton. Design drift removed enrol/Banner next-step hints from identify_gaps in advising.py so pattern participants stay on exploration hooks.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `explore_career_first` (`app/services/exploration.py`) for «Exploration / advising pipelines» or another task you owned?

**Student:** I personally extracted the shared skeleton in exploration.py and fixed explore_course_first missing_courses. Control flow always runs gap hooks. Trello CA-01 and PR #6 are my commits. Failure mode: high-school profiles must be rejected before exploration results are returned.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Exploration / advising pipelines» is this test protecting?

**Student:** tests/test_scenario.py is shallow and still passes with absolute career wording. I added a regression assertion that career-first never says You should pursue as a single forced path, and another that course-first returns missing_courses. Coverage gap: perfect overlap absolute wording.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/exploration.py` for «Exploration / advising pipelines»?

**Student:** AI drafted the Template Method extract in exploration.py. I verified by running both pipeline regression tests and rejecting a patch that kept enrol hints in identify_gaps. PR #6 has my review; ownership stayed with me.
