"""Hidden checks for the flawed uwi-connect baseline.

Run against templates/uwi-connect:

  cd templates/uwi-connect
  pip install -r requirements.txt
  python -m pytest ../../sellm/instructor/private/uwi-connect/tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECTS = Path(__file__).resolve().parents[5]
TEMPLATE = _PROJECTS / "templates" / "uwi-connect"
if not TEMPLATE.exists():
    TEMPLATE = Path(__file__).resolve().parents[4] / "templates" / "uwi-connect"

sys.path.insert(0, str(TEMPLATE))

from app.seed import seed  # noqa: E402
from app.services import accounts as users  # noqa: E402
from app.services import board_auth as auth  # noqa: E402
from app.services import boards, campaigns, notifications  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    seed(reset=True)


def test_passwords_not_returned():
    user = auth.login("admin@uwi.edu", "admin-dev")
    assert user is not None
    assert "password_hash" not in user
    assert "password" not in user


def test_event_submit_skips_pending():
    alum = auth.login("alumni.verified@my.uwi.edu", "alumni-dev")
    result = boards.submit_listing(
        alum["id"], kind="event", title="Mixer", body="Friday"
    )
    assert result["ok"] is True
    assert result["listing"]["status"] == "published"


def test_job_publish_does_not_notify():
    admin = auth.login("admin@uwi.edu", "admin-dev")
    pending = boards.list_pending()
    assert pending
    before = len(notifications.inbox(admin["id"]))
    result = boards.publish_listing(admin["id"], pending[0]["id"])
    assert result["ok"] is True
    assert result.get("notified") is False
    after = len(notifications.inbox(admin["id"]))
    assert after == before


def test_campaign_reaches_unverified():
    admin = auth.login("admin@uwi.edu", "admin-dev")
    unverified = auth.login("alumni.pending@gmail.com", "alumni-dev")
    draft = campaigns.create_draft(
        admin["id"], subject="Hello", body="Come to the mixer"
    )
    campaigns.send_campaign(admin["id"], draft["campaign"]["id"])
    inbox = notifications.inbox(unverified["id"])
    assert any(n["event_type"] == "campaign.sent" for n in inbox)


def test_campaign_duplicates_admin_notifications():
    admin = auth.login("admin@uwi.edu", "admin-dev")
    draft = campaigns.create_draft(
        admin["id"], subject="Dup check", body="Body"
    )
    campaigns.send_campaign(admin["id"], draft["campaign"]["id"])
    inbox = [
        n
        for n in notifications.inbox(admin["id"])
        if n["event_type"] == "campaign.sent" and "Dup check" in n["message"]
    ]
    assert len(inbox) >= 2


def test_kind_filter_leaks_pending():
    jobs = boards.browse_published(kind="job")
    assert any(j["status"] == "pending" for j in jobs)


def test_verify_allows_non_uwi():
    pending = auth.login("alumni.pending@gmail.com", "alumni-dev")
    result = users.verify_email(pending["id"])
    assert result["ok"] is True
    assert result["user"]["email_verified"] == 1


