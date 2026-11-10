"""Hidden checks for the flawed career-advising baseline (FastStart 0.2.0).

Run against templates/career-advising:

  cd templates/career-advising
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/career-advising/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "career-advising"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "career-advising"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import advising  # noqa: E402
from app.services import advising_auth as auth  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_not_returned():
    user = auth.login("student@example.com", "stud-dev")
    assert "password" not in user
    assert "password_hash" not in user


def test_career_first_absolute_and_enrol_hint():
    student = auth.login("student@example.com", "stud-dev")
    career = [c for c in advising.list_careers() if c["title"] == "Software Developer"][0]
    result = advising.run_career_first(student["id"], career["id"])
    assert result["ok"] is True
    assert "should pursue" in result["recommendations"][0]["wording"].lower()
    assert "enrol_hint" in result


def test_course_first_skips_gaps():
    student = auth.login("student@example.com", "stud-dev")
    result = advising.run_course_first(student["id"])
    assert result["ok"] is True
    assert result["missing_courses"] == []


def test_gaps_suggests_enrol():
    student = auth.login("student@example.com", "stud-dev")
    career = advising.list_careers()[0]
    result = advising.identify_gaps(student["id"], career["id"])
    assert "enrol" in result.get("next_step", "").lower()


def test_high_school_audience_allowed():
    student = auth.login("student@example.com", "stud-dev")
    result = advising.upsert_profile(
        student["id"],
        programme="Form 6",
        audience="high_school",
        courses="Math,Physics",
        interests="engineering",
    )
    assert result["ok"] is True
    explored = advising.run_course_first(student["id"])
    assert explored["ok"] is True
