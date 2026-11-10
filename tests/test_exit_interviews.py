SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_team_setup_student_starts_without_names(client):
    """Admin configures group details; student starts interview with no name form."""
    admin = _login(client, "instructor", "instructor-dev")
    student = _login(client, "studenta", "password123")

    team = client.post(
        "/api/admin/teams",
        headers=admin,
        json={
            "name": "Exit Team",
            "scenario_slug": "library",
            "owner_username": "studenta",
            "github_url": "fixture://demo",
            "participant_names": ["Alex Rivera", "Jordan Lee"],
        },
    )
    assert team.status_code == 201, team.text
    body = team.json()
    team_id = body["id"]
    assert body["participant_names"] == ["Alex Rivera", "Jordan Lee"]
    assert body["repository"]["index_status"] == "ready", body["repository"]
    assert body["repository"]["commit_sha"] == SHA

    mine = client.get("/api/me/teams", headers=student)
    assert mine.status_code == 200
    assert any(t["id"] == team_id for t in mine.json())

    # Student starts with no participant_names / repository id in the body
    created = client.post(
        f"/api/teams/{team_id}/exit-session",
        headers=student,
        json={"questions_per_student": 2, "target_duration_minutes": 25},
    )
    assert created.status_code == 201, created.text
    session = created.json()
    session_id = session["id"]
    assert [p["display_name"] for p in session["participants"]] == ["Alex Rivera", "Jordan Lee"]

    cons = client.post(
        f"/api/exit-sessions/{session_id}/consent",
        headers=student,
        json={"granted": True},
    )
    assert cons.status_code == 200, cons.text

    started = client.post(f"/api/exit-sessions/{session_id}/start", headers=student)
    assert started.status_code == 200, started.text
    assert started.json()["current_participant_name"] == "Alex Rivera"

    for _ in range(2):
        ans = client.post(
            f"/api/exit-sessions/{session_id}/answers",
            headers=student,
            json={
                "text": (
                    "This unit owns booking validation and capacity boundaries. "
                    "Callers should handle ValueError on over-capacity and slot conflicts. "
                    "I verified the behavior with regression tests around capacity."
                )
            },
        )
        assert ans.status_code == 200, ans.text

    mid = client.get(f"/api/exit-sessions/{session_id}", headers=student).json()
    assert mid["current_participant_name"] == "Jordan Lee"

    for _ in range(2):
        ans = client.post(
            f"/api/exit-sessions/{session_id}/answers",
            headers=student,
            json={
                "text": (
                    "The service checks headcount against capacity and rejects overbooking. "
                    "Acceptance would confirm a lecturer cannot book beyond the room limit."
                )
            },
        )
        assert ans.status_code == 200, ans.text

    finished = client.post(f"/api/exit-sessions/{session_id}/finish", headers=student)
    assert finished.status_code == 200, finished.text
    assert {r["display_name"] for r in finished.json()["reports"]} == {"Alex Rivera", "Jordan Lee"}


def test_admin_can_patch_team_details(client):
    admin = _login(client, "instructor", "instructor-dev")
    team = client.post(
        "/api/admin/teams",
        headers=admin,
        json={
            "name": "Patch Me",
            "scenario_slug": "library",
            "owner_username": "studentb",
            "participant_names": ["Pat One"],
        },
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    updated = client.patch(
        f"/api/admin/teams/{team_id}",
        headers=admin,
        json={
            "name": "Patched Team",
            "github_url": "fixture://demo",
            "participant_names": ["Pat One", "Pat Two"],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "Patched Team"
    assert body["participant_names"] == ["Pat One", "Pat Two"]
    assert body["repository"]["index_status"] == "ready"


def test_policy_public(client):
    response = client.get("/api/policy")
    assert response.status_code == 200
    body = response.json()
    assert "consent" in body
    assert body["voice"]["grading_uses_audio_cues"] is False
