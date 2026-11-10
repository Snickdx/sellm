"""Generate/validate exit-interview band fixtures for all COMP 3613 scenarios.

  python scripts/gen_exit_transcript_bands.py --write
  python scripts/gen_exit_transcript_bands.py --validate
  python scripts/gen_exit_transcript_bands.py --write --validate --render
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "exit_transcripts"

# Shared low/mid phrasing avoids gold pattern tokens (state/strategy/observer/…).
LOW = {
    "special_feature_pattern": "Not sure. Teammate handled that.",
    "design_to_code": "Looks the same to me.",
    "feature_ownership": "Mostly pair watched others type.",
    "testing": "Green suite means done.",
    "verification": "Agent wrote my section.",
}

# Mid: ~25–40 words, no gold keywords from knowledge packs.
MID_COMMON = {
    "design_to_code": (
        "Sprint one boxes on the whiteboard roughly match what shipped later. "
        "Some names moved around when we coded, and I am not sure which "
        "relationship stayed faithful versus what we reinvented under pressure."
    ),
    "feature_ownership": (
        "I made a few edits in the main service path after standup. "
        "I cannot find my board card and I did not write down what "
        "callers should do when the insert fails."
    ),
    "verification": (
        "A classmate pushed a big branch and I skimmed it before merge. "
        "I trusted the chat summary more than running the app myself, "
        "so my check was shallow."
    ),
}

SCENARIOS: dict[str, dict] = {
    "library": {
        "title": "Library workshop booking",
        "sha": "libdeadbeef01",
        "index": {
            "files": [
                ("app/services/conflicts.py", 120),
                ("app/services/bookings.py", 90),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("resolve_slot_request", "app/services/conflicts.py", 40, 95),
                ("request_booking", "app/services/bookings.py", 20, 55),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "Two lecturers wanted the room at once and the starter behaved oddly. "
                "I described the problem in standup and said we cleaned the booking "
                "logic, but I cannot name the classes we added or the approach we chose."
            ),
            "testing": (
                "The starter suite checks login and counts rows. That is thin for "
                "workshop rooms fighting over time, so we planned richer cases later "
                "but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For same-slot conflict resolution we targeted the inherited nested "
                "resolve_slot_request in conflicts.py. Capacity was checked per request "
                "only so rooms overbooked, earlier-request-wins was inverted, and larger "
                "cohorts auto-overrode without a coordinator flag. We replaced that with "
                "the Strategy pattern: CapacityGuard, EarlierRequestWins, and "
                "LargerCohortOverride as separate policies composing around the slot."
            ),
            "design_to_code": (
                "In the Sprint 1 class diagram we drew Strategy participants for capacity "
                "and conflict policies. Looking at app/services/bookings.py, request_booking "
                "still creates the booking then should hand off to conflicts strategies. "
                "During Sprint 2 we refactored so bookings no longer embeds nested slot "
                "rules — that design drift was intentional to keep strategy participants "
                "in conflicts.py instead of duplicating capacity checks here."
            ),
            "feature_ownership": (
                "I personally rewrote request_booking in app/services/bookings.py so incomplete "
                "bookings are rejected and new lecturer requests stay pending for coordinator "
                "review. Control flow now validates course_code and resources, then inserts "
                "pending. Trello card LIB-12 and PR #18 on main show my commits. Callers must "
                "handle ValidationError when course_code is empty — that was the failure mode "
                "we missed in the starter, and cancelled bookings no longer count as active "
                "in conflicts."
            ),
            "testing": (
                "tests/test_scenario.py only asserts shallow health and list length, so it still "
                "passes with overbook defects. For same-slot conflict resolution I added a "
                "regression assertion that two accepted bookings cannot exceed room capacity "
                "on the same slot, and another that earlier-request-wins keeps the first "
                "pending request when headcounts tie. The important missing gap was cancelled "
                "bookings still blocking the slot — next test should cover that."
            ),
            "verification": (
                "AI drafted the first Strategy extract near conflicts.py. I personally verified "
                "by running the capacity regression tests, walking resolve_slot_request on paper, "
                "and rejecting an agent patch that dropped the coordinator override flag. "
                "PR #18 on main has my review comments; I refuse agent code without tests for "
                "overbook and cancelled-slot cases. Ownership stayed with me after that review."
            ),
        },
    },
    "job-board": {
        "title": "Job board",
        "sha": "jbdeadbeef01",
        "index": {
            "files": [
                ("app/services/lifecycle.py", 140),
                ("app/services/applications.py", 110),
                ("app/services/listings.py", 100),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("apply_action", "app/services/lifecycle.py", 30, 90),
                ("transition_application", "app/services/applications.py", 40, 80),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "Applications could move into weird statuses in the starter. "
                "I told the team we cleaned that path, but I cannot name the "
                "classes we introduced or the approach we settled on."
            ),
            "testing": (
                "The starter suite checks login and list length. That is thin for "
                "how applications move between statuses, so we planned richer cases "
                "later but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For application lifecycle transitions we targeted the inherited flag-plus-status "
                "soup in lifecycle.py. Nested if/elif allowed illegal moves like submit to hire "
                "and reject to shortlist, and derived_status_from_flags disagreed with status. "
                "We replaced that with the State pattern: one state object per status and an "
                "explicit transition table so only legal moves remain."
            ),
            "design_to_code": (
                "Sprint 1 class diagram showed State participants for pending, shortlisted, "
                "hired, and rejected. Looking at applications.py, transition_application now "
                "delegates to lifecycle apply_action instead of flipping four boolean flags. "
                "That design drift was intentional so pattern participants live in lifecycle.py "
                "rather than scattering status strings across listings and applications."
            ),
            "feature_ownership": (
                "I personally rewrote apply_action in app/services/lifecycle.py and wired "
                "transition_application in applications.py. Control flow rejects illegal "
                "transitions and clears terminal flags on reopen. Trello JB-06 and PR #11 "
                "on main are my commits. Callers must handle IllegalTransitionError — that "
                "failure mode was missing when hire after reject still succeeded in the starter."
            ),
            "testing": (
                "tests/test_scenario.py only checks shallow health and list length, so it still "
                "passes with illegal lifecycle transitions. I added a regression assertion that "
                "reject then shortlist raises, and another that hire is unreachable from submitted "
                "without shortlist. Coverage gap remaining: IDOR on listing_applicants."
            ),
            "verification": (
                "AI drafted the first State extract near lifecycle.py. I verified by running "
                "transition regression tests, walking the transition table on paper, and rejecting "
                "an agent patch that left flag_hired set after reopen. PR #11 has my review; "
                "I refuse agent code without tests for illegal transitions. Ownership stayed with me."
            ),
        },
    },
    "uwi-connect": {
        "title": "Campus networking / info sharing",
        "sha": "ucdeadbeef01",
        "index": {
            "files": [
                ("app/services/notifications.py", 100),
                ("app/services/boards.py", 90),
                ("app/services/campaigns.py", 80),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("notify_observers", "app/services/notifications.py", 20, 60),
                ("publish_listing", "app/services/boards.py", 30, 70),
                ("send_campaign", "app/services/campaigns.py", 25, 65),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "Publishing and campaigns somehow messaged people inconsistently. "
                "I said we cleaned the notify path in standup, but I cannot name "
                "the classes we added or the approach we chose."
            ),
            "testing": (
                "The starter suite checks login and counts rows. That is thin for "
                "who gets messaged when something is published, so we planned richer "
                "cases later but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For notifications on publish and campaign send we targeted the module-level "
                "callback list in notifications.py. Subjects bypassed or double-wrote events, "
                "campaigns notified unverified users, and job publish skipped notify. We replaced "
                "that with the Observer pattern: boards and campaigns as subjects, verified-alumni "
                "subscribers as observers, with consistent audience rules."
            ),
            "design_to_code": (
                "Sprint 1 class diagram showed Observer subjects for publish_listing and "
                "send_campaign. Looking at boards.py, publish_listing now notifies for jobs "
                "and events instead of only events. Design drift moved fan-out into the "
                "observer bus so campaigns.py no longer inserts admin rows twice."
            ),
            "feature_ownership": (
                "I personally fixed publish_listing in boards.py and cleaned send_campaign in "
                "campaigns.py so unverified users are excluded. Control flow goes subject → "
                "notify_observers → persist. Trello UC-03 and PR #9 show my commits. Failure "
                "mode: callers must not assume campaign.sent always reaches every account."
            ),
            "testing": (
                "tests/test_scenario.py is shallow and still passes with missing job notifications. "
                "I added a regression assertion that publishing a job creates a notification for "
                "verified alumni only, and another that campaign send does not duplicate admin "
                "rows. Coverage gap: institutional email domain on verify_email."
            ),
            "verification": (
                "AI drafted the Observer extract in notifications.py. I verified by running "
                "publish/campaign regression tests and rejecting a patch that reintroduced the "
                "global callback list. PR #9 has my review comments; ownership stayed with me "
                "after that review of the notification bus."
            ),
        },
    },
    "thesis-tracker": {
        "title": "Postgrad milestones",
        "sha": "ttdeadbeef01",
        "index": {
            "files": [
                ("app/services/commands.py", 110),
                ("app/services/feedback.py", 90),
                ("app/services/progress.py", 80),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("record", "app/services/commands.py", 15, 50),
                ("submit_work", "app/services/feedback.py", 20, 55),
                ("add_note", "app/services/progress.py", 10, 40),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "Some student submissions seemed to disappear after save in the starter. "
                "I said we cleaned how that work is kept, but I cannot name "
                "the classes we added or the approach we chose."
            ),
            "testing": (
                "The starter suite checks login and counts rows. That is thin for "
                "whether every milestone step leaves a trustworthy record, so we "
                "planned richer cases later but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For domain actions executed and audited we targeted the optional mutable "
                "event_log in commands.py. Submissions skipped record, feedback used silent=True, "
                "and progress notes called rewrite_last before record. We replaced that with the "
                "Command pattern: Command objects plus an invoker that appends immutable command "
                "history for every successful action."
            ),
            "design_to_code": (
                "Sprint 1 class diagram showed Command participants for submit, feedback, and "
                "progress notes. Looking at feedback.py, submit_work now goes through the "
                "invoker instead of mutating then optionally logging. Design drift removed "
                "rewrite_last so command history stays append-only in commands.py."
            ),
            "feature_ownership": (
                "I personally implemented record in commands.py and wired submit_work plus "
                "complete_feedback. Control flow always appends actor and payload. Trello TT-01 "
                "and PR #7 are my commits. Failure mode: callers must not pass silent=True — "
                "that was how audit events disappeared in the starter."
            ),
            "testing": (
                "tests/test_scenario.py is shallow and still passes with missing submission audit "
                "rows. I added a regression assertion that submit_work appends a command history "
                "entry, and another that add_note does not clobber the previous row. Coverage "
                "gap: coordinator overdue flag inversion."
            ),
            "verification": (
                "AI drafted Command classes near commands.py. I verified by running audit "
                "regression tests, inspecting append-only history, and rejecting a patch that "
                "kept rewrite_last. PR #7 has my review; ownership stayed with me after that."
            ),
        },
    },
    "student-accommodation": {
        "title": "Student housing",
        "sha": "sadeadbeef01",
        "index": {
            "files": [
                ("app/services/lifecycle.py", 120),
                ("app/services/listings.py", 100),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("apply_action", "app/services/lifecycle.py", 25, 80),
                ("visible_to_students", "app/services/lifecycle.py", 90, 110),
                ("submit_listing", "app/services/listings.py", 20, 50),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "Listings could show up for students while still awaiting review. "
                "I said we cleaned how publish statuses work, but I cannot name "
                "the classes we added or the approach we chose."
            ),
            "testing": (
                "The starter suite checks login and counts rows. That is thin for "
                "how housing posts move from review to visible, so we planned richer "
                "cases later but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For listing lifecycle transitions we targeted the status-plus-flags soup in "
                "lifecycle.py. Activate from pending skipped verify, visible_to_students trusted "
                "flag_active alone, and resubmit left rejected. We replaced that with the State "
                "pattern: pending → verified → active|inactive with an explicit transition table."
            ),
            "design_to_code": (
                "Sprint 1 class diagram showed State participants for listing statuses. Looking "
                "at listings.py, transition now calls lifecycle apply_action instead of flipping "
                "flags. Design drift moved visibility rules into visible_to_students so students "
                "never see pending or rejected posts."
            ),
            "feature_ownership": (
                "I personally rewrote apply_action and visible_to_students in lifecycle.py. "
                "Control flow blocks activate from pending. Trello SA-01 and PR #5 are my "
                "commits. Failure mode: landlords without ownership must get ForbiddenError "
                "on transition — that was missing in the starter."
            ),
            "testing": (
                "tests/test_scenario.py is shallow and still passes when pending listings are "
                "student-visible. I added a regression assertion that activate from pending "
                "raises, and another that flag_active alone does not make a pending listing "
                "visible. Coverage gap: area restriction to St. Augustine / Mount Hope."
            ),
            "verification": (
                "AI drafted the State extract in lifecycle.py. I verified with visibility "
                "regression tests and rejected a patch that re-enabled activate-from-pending. "
                "PR #5 has my review; ownership stayed with me after that review."
            ),
        },
    },
    "ta-allocations": {
        "title": "TA allocation",
        "sha": "tadeadbeef01",
        "index": {
            "files": [
                ("app/services/strategies.py", 100),
                ("app/services/allocations.py", 90),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("auto_select_ta", "app/services/strategies.py", 20, 70),
                ("assign_manual", "app/services/allocations.py", 15, 55),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "Automatic TA picks felt inconsistent across modes in the starter. "
                "I said we cleaned how ranking works, but I cannot name the classes "
                "we added or the approach we chose."
            ),
            "testing": (
                "The starter suite checks login and counts rows. That is thin for "
                "weekly hour caps and ranking modes, so we planned richer cases "
                "later but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For auto-allocation ranking modes we targeted the nested mode switch in "
                "strategies.py. experience_first hard-filtered the pool, least_loaded and "
                "round_robin skipped the weekly cap, and unknown modes fell back to the first "
                "TA. We replaced that with the Strategy pattern: ranking strategies behind one "
                "interface while hard 20h and budget guards stay outside ranking."
            ),
            "design_to_code": (
                "Sprint 1 class diagram showed Strategy participants for experience_first, "
                "least_loaded, and round_robin. Looking at allocations.py, assign_manual now "
                "enforces weekly cap before insert. Design drift moved ranking into strategies.py "
                "so capacity guards are not buried inside stringly mode branches."
            ),
            "feature_ownership": (
                "I personally rewrote auto_select_ta in strategies.py and fixed assign_manual "
                "over-cap inserts in allocations.py. Control flow rejects over 20h and over "
                "budget. Trello TA-02 and PR #4 are my commits. Failure mode: empty experienced "
                "pool must soft-fall back, not hard-error."
            ),
            "testing": (
                "tests/test_scenario.py is shallow and still passes when manual assign exceeds "
                "the weekly cap. I added a regression assertion that over-cap assign_manual "
                "raises, and another that least_loaded never projects above WEEKLY_HOUR_CAP. "
                "Coverage gap: unknown mode must not silently pick the first TA."
            ),
            "verification": (
                "AI drafted Strategy classes in strategies.py. I verified with cap/budget "
                "regression tests and rejected a patch that kept experience as a hard filter. "
                "PR #4 has my review; ownership stayed with me after that review."
            ),
        },
    },
    "career-advising": {
        "title": "Career advising",
        "sha": "cadeadbeef01",
        "index": {
            "files": [
                ("app/services/exploration.py", 120),
                ("app/services/advising.py", 90),
                ("tests/test_scenario.py", 40),
            ],
            "symbols": [
                ("explore_career_first", "app/services/exploration.py", 20, 70),
                ("explore_course_first", "app/services/exploration.py", 80, 130),
                ("identify_gaps", "app/services/advising.py", 30, 60),
            ],
        },
        "mid": {
            "special_feature_pattern": (
                "The two advising modes felt copy-pasted and inconsistent in the starter. "
                "I said we cleaned those paths, but I cannot name the classes we added "
                "or the approach we chose."
            ),
            "testing": (
                "The starter suite checks login and counts rows. That is thin for "
                "both advising modes and missing prerequisites, so we planned richer "
                "cases later but did not land them before the interview."
            ),
        },
        "high": {
            "special_feature_pattern": (
                "For exploration advising pipelines we targeted duplicated career-first and "
                "course-first flows in exploration.py. Ranking used absolute wording and "
                "course-first skipped missing-course identification. We replaced that with "
                "the Template Method pattern: a shared skeleton with mode-specific hooks for "
                "match, non-absolute rank, identify gaps, and present."
            ),
            "design_to_code": (
                "Sprint 1 class diagram showed Template Method participants for the shared "
                "pipeline. Looking at exploration.py, both modes now call the same skeleton. "
                "Design drift removed enrol/Banner next-step hints from identify_gaps in "
                "advising.py so pattern participants stay on exploration hooks."
            ),
            "feature_ownership": (
                "I personally extracted the shared skeleton in exploration.py and fixed "
                "explore_course_first missing_courses. Control flow always runs gap hooks. "
                "Trello CA-01 and PR #6 are my commits. Failure mode: high-school profiles "
                "must be rejected before exploration results are returned."
            ),
            "testing": (
                "tests/test_scenario.py is shallow and still passes with absolute career "
                "wording. I added a regression assertion that career-first never says "
                "You should pursue as a single forced path, and another that course-first "
                "returns missing_courses. Coverage gap: perfect overlap absolute wording."
            ),
            "verification": (
                "AI drafted the Template Method extract in exploration.py. I verified by "
                "running both pipeline regression tests and rejecting a patch that kept "
                "enrol hints in identify_gaps. PR #6 has my review; ownership stayed with me."
            ),
        },
    },
}


def _index_payload(spec: dict, sha: str) -> dict:
    files = [
        {"path": path, "language": "python", "line_count": lines}
        for path, lines in spec["files"]
    ]
    symbols = [
        {
            "name": name,
            "kind": "function",
            "path": path,
            "line_start": start,
            "line_end": end,
        }
        for name, path, start, end in spec["symbols"]
    ]
    return {
        "commit_sha": sha,
        "files": files,
        "symbols": symbols,
        "tests": [{"path": "tests/test_scenario.py", "language": "python", "line_count": 40}],
    }


def build_fixture(slug: str) -> dict:
    meta = SCENARIOS[slug]
    mid = {**MID_COMMON, **meta["mid"]}
    high = meta["high"]
    return {
        "scenario_slug": slug,
        "repository_sha": meta["sha"],
        "index": _index_payload(meta["index"], meta["sha"]),
        "bands": {
            "low": {
                "label": "Weak / evasive",
                "student_display_name": f"{meta['title']} Low",
                "expected_score_range": [1, 2],
                "answers": dict(LOW),
            },
            "mid": {
                "label": "Partial / vague (length without gold terms)",
                "student_display_name": f"{meta['title']} Mid",
                "expected_score_range": [3, 4],
                "answers": mid,
            },
            "high": {
                "label": "Strong / gold-aligned",
                "student_display_name": f"{meta['title']} High",
                "expected_score_range": [5, 5],
                "answers": high,
            },
        },
    }


def write_fixtures() -> None:
    for slug in SCENARIOS:
        fixture = build_fixture(slug)
        out_dir = OUT / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "bands.yaml"
        header = (
            f"# {SCENARIOS[slug]['title']} — exit-interview answer bands for scorer calibration.\n"
            "# Prompts generated at test time from planner + fixed index.\n"
            "# low→1–2, mid→3–4, high→5 (provisional heuristic with knowledge pack).\n"
        )
        body = yaml.safe_dump(fixture, sort_keys=False, allow_unicode=True, width=100)
        path.write_text(header + body, encoding="utf-8")
        readme = out_dir / "README.md"
        readme.write_text(
            f"# {SCENARIOS[slug]['title']} exit-interview transcript bands\n\n"
            f"See [`bands.yaml`](bands.yaml). Shared runner: "
            f"`tests/test_exit_transcript_bands.py`.\n\n"
            f"```powershell\n"
            f"$env:RAG_BACKEND='none'\n"
            f"python -m pytest tests/test_exit_transcript_bands.py -q -k {slug}\n"
            f"python -m tests.fixtures.exit_transcripts.render_bands --scenario {slug} --write\n"
            f"```\n",
            encoding="utf-8",
        )
        print(f"wrote {path}")


def validate() -> int:
    sys.path.insert(0, str(ROOT))
    from app.course.examiner.scorer import score_session
    from tests.fixtures.exit_transcripts.bands_loader import build_band_bundle, list_scenario_slugs

    failed = 0
    for slug in list_scenario_slugs():
        avgs = {}
        for band in ("low", "mid", "high"):
            bundle, _plan, meta = build_band_bundle(slug, band)
            lo, hi = meta["expected_score_range"]
            reports = score_session(bundle, meta["repository_sha"], scenario_slug=slug)
            scores = []
            for row in reports[0]["competencies"]:
                s = row["score"]
                scores.append(s)
                if s is None or not (lo <= s <= hi):
                    print(f"FAIL {slug}/{band}/{row['name']}: score={s} want [{lo},{hi}]")
                    failed += 1
            avgs[band] = sum(x for x in scores if x) / len(scores)
            print(f"OK   {slug}/{band}: scores={scores} avg={avgs[band]:.2f}")
        if not (avgs["low"] < avgs["mid"] < avgs["high"]):
            print(f"FAIL {slug}: ordering {avgs}")
            failed += 1
    return failed


def render_all() -> None:
    sys.path.insert(0, str(ROOT))
    from tests.fixtures.exit_transcripts.bands_loader import list_scenario_slugs, render_band_transcript

    for slug in list_scenario_slugs():
        for band in ("low", "mid", "high"):
            text = render_band_transcript(slug, band)
            path = OUT / slug / f"transcript_{band}.md"
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_fixtures()
    if args.validate:
        failed = validate()
        if failed:
            raise SystemExit(f"{failed} validation failures")
        print("ALL_OK")
    if args.render:
        render_all()
    if not (args.write or args.validate or args.render):
        parser.print_help()


if __name__ == "__main__":
    main()
