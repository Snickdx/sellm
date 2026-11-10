"""
Hidden regression expectations for the flawed baseline.

Run against templates/job-board:

  cd templates/job-board
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/job-board/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "job-board"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "job-board"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import applications, listings  # noqa: E402
from app.services import board_auth as auth  # noqa: E402
from app.services.lifecycle import apply_action  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_are_hashed_and_not_returned():
    user = auth.login("admin@example.com", "admin-dev")
    assert user is not None
    assert "password" not in user
    assert "password_hash" not in user


def test_pending_and_expired_visible_to_graduates():
    jobs = listings.list_jobs_for_graduates()
    statuses = {j["status"] for j in jobs}
    deadlines = {j["deadline"] for j in jobs}
    assert "pending" in statuses
    assert "2020-01-01" in deadlines


def test_submit_skips_pending_gate():
    employer = auth.login("employer@example.com", "employer-dev")
    result = listings.submit_listing(
        employer["id"],
        "New Role",
        "Co",
        "Desc",
        "collect",
        "2099-01-01",
    )
    assert result["ok"] is True
    assert result["status"] == "published"


def test_ineligible_graduate_can_apply():
    other = auth.login("grad.other@example.com", "grad-dev")
    listing_id = listings.list_jobs_for_graduates()[0]["id"]
    result = applications.apply(other["id"], listing_id, "please hire me")
    assert result["ok"] is True


def test_lifecycle_allows_hire_from_submitted():
    app = {
        "id": 1,
        "status": "submitted",
        "flag_reviewed": 0,
        "flag_shortlisted": 0,
        "flag_rejected": 0,
        "flag_hired": 0,
    }
    result = apply_action(app, "hire")
    assert result["ok"] is True
    assert result["row"]["status"] == "hired"
    assert result["row"]["flag_hired"] == 1


def test_lifecycle_reopen_leaves_terminal_flags():
    app = {
        "id": 1,
        "status": "hired",
        "flag_reviewed": 1,
        "flag_shortlisted": 1,
        "flag_rejected": 0,
        "flag_hired": 1,
    }
    result = apply_action(app, "reopen")
    assert result["row"]["status"] == "submitted"
    assert result["row"]["flag_hired"] == 1


def test_status_and_flags_diverge_for_graduates():
    grad = auth.login("grad.dcit@example.com", "grad-dev")
    employer = auth.login("employer@example.com", "employer-dev")
    listing_id = listings.list_jobs_for_graduates()[0]["id"]
    created = applications.apply(grad["id"], listing_id, "cover")
    applications.transition_application(
        employer["id"], created["application_id"], "hire"
    )
    # Force inconsistent flags via reject-after-hire path
    applications.transition_application(
        employer["id"], created["application_id"], "reject"
    )
    mine = applications.my_applications(grad["id"])
    row = next(a for a in mine if a["id"] == created["application_id"])
    # derived_status_from_flags prefers hired over rejected when both set
    assert row["flag_hired"] == 1
    assert row["flag_rejected"] == 1
    assert row["status"] == "hired"


def test_employer_idor_on_applicants():
    e1 = auth.login("employer@example.com", "employer-dev")
    e2 = auth.login("employer2@example.com", "employer-dev")
    jobs = [j for j in listings.list_jobs_for_graduates() if j["employer_id"] == e1["id"]]
    assert jobs
    result = applications.listing_applicants(e2["id"], jobs[0]["id"])
    assert result["ok"] is True
