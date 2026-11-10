"""
Hidden regression expectations for the flawed baseline.

Run against templates/library:

  cd templates/library
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/library/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "library"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "library"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import bookings  # noqa: E402
from app.services import library_auth as auth  # noqa: E402
from app.services.conflicts import DEFAULT_CAPACITY, resolve_slot_request  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_hashed_not_returned():
    user = auth.login("coord@example.com", "coord-dev")
    assert user is not None
    assert "password_hash" not in user


def test_aggregate_capacity_not_enforced():
    room = {"id": 1, "name": "A", "capacity": 30}
    existing = [
        {
            "id": 1,
            "status": "accepted",
            "headcount": 20,
            "created_at": "2099-01-01T10:00:00+00:00",
        }
    ]
    incoming = {"headcount": 20, "created_at": "2099-01-02T10:00:00+00:00"}
    verdict = resolve_slot_request(
        incoming=incoming, existing=existing, room=room, coordinator_override=False
    )
    assert verdict["decision"] == "accept"
    assert 20 + 20 > DEFAULT_CAPACITY or 20 + 20 > room["capacity"]


def test_earlier_wins_inverted():
    room = {"id": 1, "capacity": 30}
    existing = [
        {
            "id": 1,
            "status": "accepted",
            "headcount": 15,
            "created_at": "2099-01-01T09:00:00+00:00",
        },
        {
            "id": 2,
            "status": "accepted",
            "headcount": 15,
            "created_at": "2099-01-01T11:00:00+00:00",
        },
    ]
    # Smaller/newer challenger — flawed logic still coexists / uses latest champion
    incoming = {"headcount": 10, "created_at": "2099-01-01T12:00:00+00:00"}
    verdict = resolve_slot_request(
        incoming=incoming, existing=existing, room=room, coordinator_override=False
    )
    assert verdict["decision"] == "accept"
    assert verdict["reason"] in {"coexist on slot", "fallback accept", "larger cohort auto-wins"}


def test_larger_cohort_auto_override_without_flag():
    room = {"id": 1, "capacity": 30}
    existing = [
        {
            "id": 1,
            "status": "accepted",
            "headcount": 10,
            "created_at": "2099-01-01T09:00:00+00:00",
        }
    ]
    incoming = {"headcount": 25, "created_at": "2099-01-02T09:00:00+00:00"}
    verdict = resolve_slot_request(
        incoming=incoming, existing=existing, room=room, coordinator_override=False
    )
    assert verdict["decision"] == "accept"
    assert verdict["override_used"] is True
    assert 1 in verdict["displace_ids"]


def test_incomplete_booking_accepted():
    lect = auth.login("lecturer2@example.com", "lect-dev")
    rooms = bookings.list_rooms()
    result = bookings.request_booking(
        lect["id"],
        room_id=rooms[0]["id"],
        course_code="",
        headcount=5,
        preferred_date="2099-04-01",
        resources="",
    )
    assert result["ok"] is True


def test_cancelled_confirmation_still_works():
    lect = auth.login("lecturer1@example.com", "lect-dev")
    mine = [
        b
        for b in bookings.list_bookings()
        if b["lecturer_id"] == lect["id"] and b["status"] == "accepted"
    ]
    assert mine
    bookings.cancel_booking(lect["id"], mine[0]["id"])
    conf = bookings.get_confirmation(mine[0]["confirmation_code"])
    assert conf["ok"] is True
