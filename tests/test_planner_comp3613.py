"""Unit tests for COMP 3613 exit-interview question planner."""

from app.examiner.planner import generate_question_plan
from app.examiner.scenario_focus import SCENARIO_SPECIAL_FEATURES, resolve_scenario_focus


def _tiny_index() -> dict:
    return {
        "commit_sha": "deadbeef",
        "files": [
            {"path": "app/service.py", "language": "python", "line_count": 80},
            {"path": "tests/test_service.py", "language": "python", "line_count": 40},
        ],
        "symbols": [
            {
                "name": "allocate",
                "kind": "function",
                "path": "app/service.py",
                "line_start": 10,
                "line_end": 24,
            }
        ],
        "tests": [{"path": "tests/test_service.py", "language": "python", "line_count": 40}],
    }


def test_resolve_known_and_unknown_focus():
    known = resolve_scenario_focus("library")
    assert known["known"] is True
    assert known["special_feature"] == "Same-slot conflict resolution"

    unknown = resolve_scenario_focus("not-a-real-slug")
    assert unknown["known"] is False
    assert "special feature" in unknown["special_feature"].lower()


def test_plan_order_and_special_feature_in_prompts():
    plan = generate_question_plan(
        participant_user_ids=[-1],
        index=_tiny_index(),
        questions_per_student=3,
        scenario_slug="job-board",
    )
    assert plan["planner_version"] == "comp3613-planner-v3"
    assert plan["has_judge_knowledge"] is True
    assert plan["special_feature"] == "Application lifecycle / transitions"
    comps = [q["competency"] for q in plan["questions"]]
    assert comps == ["special_feature_pattern", "design_to_code", "feature_ownership"]
    assert all("Application lifecycle / transitions" in q["prompt"] for q in plan["questions"])
    # One ask per prompt (no multi-part "and" stacks in the primary).
    pattern = plan["questions"][0]
    assert pattern["prompt"].count("?") == 1
    assert len(pattern["follow_ups"]) >= 2


def test_each_known_slug_appears_in_pattern_prompt():
    for slug, (_title, special) in SCENARIO_SPECIAL_FEATURES.items():
        plan = generate_question_plan(
            participant_user_ids=[-1],
            index=_tiny_index(),
            questions_per_student=1,
            scenario_slug=slug,
        )
        assert len(plan["questions"]) == 1
        assert plan["questions"][0]["competency"] == "special_feature_pattern"
        assert special in plan["questions"][0]["prompt"]


def test_full_tree_has_five_competencies():
    plan = generate_question_plan(
        participant_user_ids=[-1, -2],
        index=_tiny_index(),
        scenario_slug="ta-allocations",
    )
    for uid in ("-1", "-2"):
        comps = [q["competency"] for q in plan["questions"] if q["target_user_id"] == uid]
        assert comps == [
            "special_feature_pattern",
            "design_to_code",
            "feature_ownership",
            "testing",
            "verification",
        ]


def test_spawn_skip_alternate_promotes_follow_up():
    from sqlmodel import Session, SQLModel, create_engine

    from app.examiner.state import spawn_skip_alternate
    from app.models.exit import InterviewQuestion

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        q = InterviewQuestion(
            session_id="sess-1",
            target_user_id=-1,
            sequence=0,
            competency="special_feature_pattern",
            prompt="Primary ask?",
            follow_ups=["Alternate A?", "Alternate B?"],
            status="asked",
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        alt = spawn_skip_alternate(db, q)
        db.commit()
        assert alt is not None
        assert alt.prompt == "Alternate A?"
        assert alt.follow_ups == ["Alternate B?"]
        assert alt.status == "pending"
        assert alt.competency == "special_feature_pattern"
        db.refresh(q)
        assert q.follow_ups == []
