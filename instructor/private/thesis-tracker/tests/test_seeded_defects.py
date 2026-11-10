"""Hidden checks for the flawed thesis-tracker baseline.

Run against templates/thesis-tracker:

  cd templates/thesis-tracker
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/thesis-tracker/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "thesis-tracker"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "thesis-tracker"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import commands, feedback, pairings, progress  # noqa: E402
from app.services import thesis_auth as auth  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_not_returned():
    user = auth.login("coord@example.com", "coord-dev")
    assert "password_hash" not in user


def test_submit_not_audited():
    student = auth.login("student1@example.com", "stud-dev")
    pairing_id = pairings.list_pairings()[0]["id"]
    before = {e["id"] for e in commands.history()}
    feedback.submit_work(
        student["id"], pairing_id=pairing_id, title="T", content="C"
    )
    after = {e["id"] for e in commands.history()}
    assert after == before


def test_complete_feedback_silent():
    supervisor = auth.login("super1@example.com", "super-dev")
    open_fb = [
        f for f in feedback.list_feedback() if f["status"] == "open"
    ][0]
    before = len(commands.history())
    feedback.complete_feedback(supervisor["id"], open_fb["id"], notes="")
    assert len(commands.history()) == before


def test_progress_rewrites_history():
    supervisor = auth.login("super1@example.com", "super-dev")
    pairing_id = pairings.list_pairings()[0]["id"]
    commands.record("marker", actor_id=supervisor["id"], payload={"x": 1})
    before = commands.history()[0]
    progress.add_note(supervisor["id"], pairing_id=pairing_id, body="hello progress")
    # Prior marker row was clobbered in place, then a new note event appended
    rows = {e["id"]: e for e in commands.history()}
    assert before["id"] in rows
    assert rows[before["id"]]["action"] == "progress.note_added.clobber"
    assert any(e["action"] == "progress.note_added" for e in rows.values())


def test_capacity_not_enforced():
    coord = auth.login("coord@example.com", "coord-dev")
    super2 = auth.login("super2@example.com", "super-dev")
    s2 = auth.login("student2@example.com", "stud-dev")
    s3 = auth.login("student3@example.com", "stud-dev")
    r1 = pairings.create_pairing(coord["id"], s2["id"], super2["id"])
    r2 = pairings.create_pairing(coord["id"], s3["id"], super2["id"])
    assert r1["ok"] and r2["ok"]
    assert r2.get("over_capacity") is True


def test_coordinator_overdue_inverted():
    items = feedback.list_feedback(for_coordinator=True)
    # seed has due_date 2020-01-01 open — should be overdue, inverted ⇒ False
    past = next(i for i in items if i["due_date"] == "2020-01-01")
    assert past["overdue"] is False


def test_empty_notes_complete():
    supervisor = auth.login("super1@example.com", "super-dev")
    seed(reset=True)
    open_fb = [f for f in feedback.list_feedback() if f["status"] == "open"][0]
    result = feedback.complete_feedback(supervisor["id"], open_fb["id"], notes="")
    assert result["ok"] is True
    assert result["feedback"]["status"] == "done"
