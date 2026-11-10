"""
Hidden regression expectations for the flawed baseline.

Run against templates/ta-allocations:

  cd templates/ta-allocations
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/ta-allocations/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "ta-allocations"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "ta-allocations"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import allocation_auth as auth  # noqa: E402
from app.services import allocations  # noqa: E402
from app.services.constants import WEEKLY_HOUR_CAP  # noqa: E402
from app.services.strategies import auto_select_ta  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_not_returned():
    user = auth.login("hod@example.com", "hod-dev")
    assert "password" not in user
    assert "password_hash" not in user


def test_manual_over_cap_still_assigns():
    hod = auth.login("hod@example.com", "hod-dev")
    # Alex already has 18h; +5 ⇒ 23 > 20
    alex = [t for t in allocations.list_tas() if t["email"] == "alex@example.com"][0]
    course = allocations.list_courses()[0]
    result = allocations.assign_manual(
        hod["id"], ta_id=alex["id"], course_id=course["id"], weekly_hours=5
    )
    assert result["ok"] is True
    assert result["over_cap"] is True


def test_experience_first_hard_filter():
    courses = {c["code"]: c for c in allocations.list_courses()}
    tas = allocations.list_tas()
    # COMP1601 has no experienced TAs in seed
    pick = auto_select_ta(
        mode="experience_first",
        course=courses["COMP1601"],
        tas=tas,
        experience=set(),
        load_by_ta={},
        budget_remaining=50,
        hours=4,
    )
    assert pick["ok"] is False


def test_least_loaded_ignores_cap():
    tas = allocations.list_tas()
    course = allocations.list_courses()[0]
    pick = auto_select_ta(
        mode="least_loaded",
        course=course,
        tas=tas,
        experience=set(),
        load_by_ta={tas[0]["id"]: 19, tas[1]["id"]: 19, tas[2]["id"]: 19},
        budget_remaining=50,
        hours=5,
    )
    assert pick["ok"] is True
    assert pick["projected_load"] > WEEKLY_HOUR_CAP


def test_auto_round_robin_persists_over_cap():
    hod = auth.login("hod@example.com", "hod-dev")
    course = [c for c in allocations.list_courses() if c["code"] == "COMP1601"][0]
    result = allocations.assign_auto(
        hod["id"], course_id=course["id"], weekly_hours=10, mode="round_robin"
    )
    assert result["ok"] is True
