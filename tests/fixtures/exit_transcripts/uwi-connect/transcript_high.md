# Uwi Connect exit transcript — high (Strong / gold-aligned)

Scenario: `uwi-connect`  
SHA: `ucdeadbeef01`  
Expected provisional score range: [5, 5]

## Q1. `special_feature_pattern`

**Examiner:** For «Notifications on publish / campaign send» in Campus networking / info sharing, what inherited weakness did your team target?

**Student:** For notifications on publish and campaign send we targeted the module-level callback list in notifications.py. Subjects bypassed or double-wrote events, campaigns notified unverified users, and job publish skipped notify. We replaced that with the Observer pattern: boards and campaigns as subjects, verified-alumni subscribers as observers, with consistent audience rules.

## Q2. `design_to_code`

**Examiner:** Looking at `app/services/boards.py`, what design decision from your Sprint 1 class diagram for «Notifications on publish / campaign send» does this file embody?

**Student:** Sprint 1 class diagram showed Observer subjects for publish_listing and send_campaign. Looking at boards.py, publish_listing now notifies for jobs and events instead of only events. Design drift moved fan-out into the observer bus so campaigns.py no longer inserts admin rows twice.

## Q3. `feature_ownership`

**Examiner:** What did you personally change in `notify_observers` (`app/services/notifications.py`) for «Notifications on publish / campaign send» or another task you owned?

**Student:** I personally fixed publish_listing in boards.py and cleaned send_campaign in campaigns.py so unverified users are excluded. Control flow goes subject → notify_observers → persist. Trello UC-03 and PR #9 show my commits. Failure mode: callers must not assume campaign.sent always reaches every account.

## Q4. `testing`

**Examiner:** In `tests/test_scenario.py`, what behavior of «Notifications on publish / campaign send» is this test protecting?

**Student:** tests/test_scenario.py is shallow and still passes with missing job notifications. I added a regression assertion that publishing a job creates a notification for verified alumni only, and another that campaign send does not duplicate admin rows. Coverage gap: institutional email domain on verify_email.

## Q5. `verification`

**Examiner:** Where did AI assistance or a teammate's PR most influence code you claim near `app/services/notifications.py` for «Notifications on publish / campaign send»?

**Student:** AI drafted the Observer extract in notifications.py. I verified by running publish/campaign regression tests and rejecting a patch that reintroduced the global callback list. PR #9 has my review comments; ownership stayed with me after that review of the notification bus.
