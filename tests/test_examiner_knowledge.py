"""Examiner knowledge packs: template flaws / patterns / features for judging."""

from app.examiner.knowledge import (
    focus_paths_for,
    judge_concepts_for,
    list_knowledge_slugs,
    resolve_judge_knowledge,
)
from app.examiner.planner import generate_question_plan
from app.examiner.scenario_focus import SCENARIO_SPECIAL_FEATURES
from app.examiner.scorer import _score_answer


def test_every_scenario_has_a_knowledge_pack():
    packs = set(list_knowledge_slugs())
    assert packs == set(SCENARIO_SPECIAL_FEATURES)


def test_job_board_gold_has_state_and_architecture_defect():
    pack = resolve_judge_knowledge("job-board")
    assert pack is not None
    assert pack["intended_pattern"] == "State"
    assert pack["architecture_defect"]["id"] == "JB-DEF-006"
    assert "app/services/lifecycle.py" in pack["focus_paths"]
    concepts = judge_concepts_for("job-board", "special_feature_pattern")
    assert "State" in concepts
    assert any("lifecycle" in c.lower() for c in concepts)


def test_focus_paths_prefer_lifecycle_in_plan_cites():
    index = {
        "commit_sha": "abc",
        "files": [
            {"path": "app/services/listings.py", "language": "python", "line_count": 40},
            {"path": "app/services/lifecycle.py", "language": "python", "line_count": 90},
            {"path": "tests/test_scenario.py", "language": "python", "line_count": 20},
        ],
        "symbols": [
            {
                "name": "list_jobs",
                "kind": "function",
                "path": "app/services/listings.py",
                "line_start": 1,
                "line_end": 10,
            },
            {
                "name": "transition_application",
                "kind": "function",
                "path": "app/services/lifecycle.py",
                "line_start": 20,
                "line_end": 40,
            },
        ],
        "tests": [{"path": "tests/test_scenario.py", "language": "python", "line_count": 20}],
    }
    plan = generate_question_plan(
        participant_user_ids=[-1],
        index=index,
        questions_per_student=1,
        scenario_slug="job-board",
    )
    q = plan["questions"][0]
    # Prompt must stay pattern-agnostic (no State leak).
    assert "State" not in q["prompt"]
    assert "JB-DEF" not in q["prompt"]
    assert "lifecycle" in (q["code_refs"].get("path") or "")


def test_scorer_rewards_pattern_aware_answer_via_gold():
    weak = _score_answer("We fixed some bugs in the app.", ["special_feature", "design_pattern"])
    gold = judge_concepts_for("library", "special_feature_pattern")
    strong = _score_answer(
        "We used the Strategy pattern on same-slot conflict capacity policies "
        "instead of nested resolve_slot_request overrides.",
        ["special_feature", "design_pattern"] + gold,
    )
    assert strong > weak
    assert focus_paths_for("library")[0].endswith("conflicts.py")
