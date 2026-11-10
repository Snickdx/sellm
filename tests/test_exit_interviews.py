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
    # COMP 3613 tree: first two competencies; library special-feature wording
    alex_qs = [q for q in session["questions"] if q["target_user_id"] == session["participants"][0]["user_id"]]
    assert [q["competency"] for q in alex_qs] == ["special_feature_pattern", "design_to_code"]
    assert any("Same-slot conflict resolution" in q["prompt"] for q in alex_qs)

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


def test_student_group_settings_and_named_interview(client):
    """Exit page flow: save group name+repo, start interview with one member name, list past."""
    admin = _login(client, "instructor", "instructor-dev")
    student = _login(client, "studenta", "password123")

    team = client.post(
        "/api/admin/teams",
        headers=admin,
        json={"name": "Seed", "scenario_slug": "library", "owner_username": "studenta"},
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    setup = client.post(
        "/api/me/group-setup",
        headers=student,
        json={
            "team_id": team_id,
            "name": "Student Group",
            "github_url": "fixture://demo",
        },
    )
    assert setup.status_code == 200, setup.text
    assert setup.json()["team"]["name"] == "Student Group"
    assert setup.json()["repository"]["index_status"] == "ready"

    created = client.post(
        f"/api/teams/{team_id}/exit-session",
        headers=student,
        json={"participant_names": ["Alex Rivera"], "questions_per_student": 1},
    )
    assert created.status_code == 201, created.text
    assert [p["display_name"] for p in created.json()["participants"]] == ["Alex Rivera"]

    listed = client.get(f"/api/teams/{team_id}/exit-sessions", headers=student)
    assert listed.status_code == 200
    assert any(s["id"] == created.json()["id"] for s in listed.json())
    assert listed.json()[0]["participant_names"] == ["Alex Rivera"]


def test_student_can_delete_own_exit_session(client):
    """Creators may delete their own interview; instructors still can; others cannot."""
    admin = _login(client, "instructor", "instructor-dev")
    student = _login(client, "studenta", "password123")
    other = _login(client, "studentb", "password123")

    team = client.post(
        "/api/admin/teams",
        headers=admin,
        json={
            "name": "Delete Own",
            "scenario_slug": "library",
            "owner_username": "studenta",
            "github_url": "fixture://demo",
            "participant_names": ["Alex"],
        },
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    # Add studentb as teammate so they can see the session but not delete it.
    member = client.put(
        f"/api/admin/teams/{team_id}/members",
        headers=admin,
        json={"usernames": ["studenta", "studentb"]},
    )
    assert member.status_code == 200, member.text

    created = client.post(
        f"/api/teams/{team_id}/exit-session",
        headers=student,
        json={"questions_per_student": 1},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    assert created.json()["created_by_id"] is not None

    denied = client.delete(f"/api/exit-sessions/{session_id}", headers=other)
    assert denied.status_code == 403, denied.text

    deleted = client.delete(f"/api/exit-sessions/{session_id}", headers=student)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["ok"] is True

    missing = client.get(f"/api/exit-sessions/{session_id}", headers=student)
    assert missing.status_code == 404

    # Instructor can delete another student's session.
    again = client.post(
        f"/api/teams/{team_id}/exit-session",
        headers=student,
        json={"questions_per_student": 1},
    )
    assert again.status_code == 201, again.text
    sid2 = again.json()["id"]
    by_admin = client.delete(f"/api/exit-sessions/{sid2}", headers=admin)
    assert by_admin.status_code == 200, by_admin.text


def test_policy_public(client):
    response = client.get("/api/policy")
    assert response.status_code == 200
    body = response.json()
    assert "consent" in body
    assert body["voice"]["grading_uses_audio_cues"] is False
