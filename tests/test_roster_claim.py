from pathlib import Path

CLASSLIST = Path(__file__).resolve().parents[1] / "classlist.csv"


def _login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_admin_import_search_hides_ids_and_claim(client):
    admin = _login(client, "instructor", "instructor-dev")
    assert CLASSLIST.is_file()

    imported = client.post("/api/admin/roster/import", headers=admin)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["total"] >= 3
    assert body["created"] + body["updated"] >= 3

    roster = client.get("/api/admin/roster", headers=admin)
    assert roster.status_code == 200
    students = roster.json()["students"]
    assert students
    assert all("student_number" in s for s in students)
    first_three = students[:3]
    first_id_number = first_three[0]["student_number"]

    # Public search must not expose student_number and must not match by ID.
    by_name = client.get("/api/roster/search", params={"q": first_three[0]["display_name"].split()[0]})
    assert by_name.status_code == 200
    hits = by_name.json()
    assert hits
    assert all("student_number" not in h for h in hits)
    assert all(h["id"] and h["display_name"] for h in hits)

    by_id = client.get("/api/roster/search", params={"q": first_id_number})
    assert by_id.status_code == 200
    assert by_id.json() == []

    member_ids = [s["id"] for s in first_three]
    claimed = client.post(
        "/api/roster/claim",
        json={"group_name": "Alpha Testers", "member_ids": member_ids},
    )
    assert claimed.status_code == 200, claimed.text
    payload = claimed.json()
    assert payload["username"]
    assert payload["password"]
    assert payload["members"]
    assert len(payload["members"]) == 3

    again = client.post(
        "/api/roster/claim",
        json={"group_name": "Other Group", "member_ids": member_ids},
    )
    assert again.status_code == 409

    login = client.post(
        "/api/auth/login",
        json={"username": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200, login.text

    refreshed = client.get("/api/admin/roster", headers=admin).json()
    claimed_rows = [s for s in refreshed["students"] if s["id"] in member_ids]
    assert all(s["status"] == "claimed" for s in claimed_rows)
    assert all(s["account_username"] == payload["username"] for s in claimed_rows)
    assert all(s["group_name"] == "Alpha Testers" for s in claimed_rows)

    student = _login(client, payload["username"], payload["password"])
    mine = client.get("/api/me/group", headers=student)
    assert mine.status_code == 200, mine.text
    group = mine.json()
    assert group["can_edit_members"] is True
    assert len(group["members"]) == 3
    assert group["team_id"] == payload["team_id"]

    available = [
        s for s in client.get("/api/admin/roster", headers=admin).json()["students"] if s["status"] == "available"
    ]
    assert available, "need an ungrouped classmate for swap"
    swapped_out = member_ids[0]
    keep = member_ids[1:]
    new_ids = keep + [available[0]["id"]]
    updated = client.put("/api/me/group/members", headers=student, json={"member_ids": new_ids})
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert {m["id"] for m in body["members"]} == set(new_ids)
    assert available[0]["display_name"] in body["participant_names"]

    after = client.get("/api/admin/roster", headers=admin).json()["students"]
    by_id = {s["id"]: s for s in after}
    assert by_id[swapped_out]["status"] == "available"
    assert by_id[available[0]["id"]]["status"] == "claimed"
    assert by_id[available[0]["id"]]["group_name"] == "Alpha Testers"
