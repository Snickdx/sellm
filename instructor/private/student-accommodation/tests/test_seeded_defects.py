"""Hidden checks for the flawed student-accommodation baseline (FastStart 0.2.0).

Run against templates/student-accommodation:

  cd templates/student-accommodation
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/student-accommodation/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "student-accommodation"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "student-accommodation"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import housing_auth as auth  # noqa: E402
from app.services import listings  # noqa: E402
from app.services.lifecycle import apply_action, visible_to_students  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_not_returned():
    user = auth.login("admin@example.com", "admin-dev")
    assert "password" not in user
    assert "password_hash" not in user


def test_activate_from_pending():
    listing = {
        "id": 1,
        "status": "pending",
        "flag_pending": 1,
        "flag_verified": 0,
        "flag_active": 0,
        "flag_rejected": 0,
    }
    result = apply_action(listing, "activate")
    assert result["ok"] is True
    assert result["row"]["status"] == "active"
    assert result["row"]["flag_active"] == 1


def test_flag_active_shows_pending_status():
    listing = {
        "status": "pending",
        "flag_pending": 1,
        "flag_verified": 0,
        "flag_active": 1,
        "flag_rejected": 0,
    }
    assert visible_to_students(listing) is True


def test_landlord_idor_activate():
    land2 = auth.login("landlord2@example.com", "land-dev")
    pending = [x for x in listings.list_all() if x["status"] == "pending"][0]
    result = listings.transition(land2["id"], pending["id"], "activate")
    assert result["ok"] is True


def test_out_of_area_submit():
    land = auth.login("landlord@example.com", "land-dev")
    result = listings.submit_listing(
        land["id"],
        title="Far Away",
        area="tobago",
        price=1000,
        amenities="",
        contact_phone="1",
        contact_email="a@b.c",
    )
    assert result["ok"] is True


def test_message_pending():
    student = auth.login("student@example.com", "stud-dev")
    pending = [x for x in listings.list_all() if x["status"] == "pending"][0]
    result = listings.send_message(student["id"], pending["id"], "hi")
    assert result["ok"] is True


def test_verify_rejected_without_resubmit():
    listing = {
        "id": 1,
        "status": "rejected",
        "flag_pending": 0,
        "flag_verified": 0,
        "flag_active": 0,
        "flag_rejected": 1,
    }
    result = apply_action(listing, "verify")
    assert result["ok"] is True
    assert result["row"]["status"] == "verified"
    assert result["row"]["flag_rejected"] == 1
