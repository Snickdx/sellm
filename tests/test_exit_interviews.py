SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _user_id(client, headers):
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    return me.json()["user_id"]


def test_exit_interview_student_self_service_flow(client):
    student_a = _login(client, "studenta", "password123")
    student_b = _login(client, "studentb", "password123")
    id_a = _user_id(client, student_a)
    id_b = _user_id(client, student_b)

    # Student creates team and adds teammate
    team = client.post(
        "/api/teams",
        headers=student_a,
        json={
            "name": "Exit Team",
            "scenario_slug": "library",
            "member_usernames": ["studentb"],
        },
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    assert any(m["user_id"] == id_a for m in team.json()["members"])
    assert any(m["user_id"] == id_b for m in team.json()["members"])

    # Student freezes repo
    repo = client.post(
        f"/api/teams/{team_id}/repository",
        headers=student_a,
        json={"github_url": "fixture://demo", "commit_sha": SHA, "analyze_now": True},
    )
    assert repo.status_code == 201, repo.text
    assert repo.json()["index_status"] == "ready", repo.json()
    repo_id = repo.json()["id"]

    # Student creates exit session
    created = client.post(
        f"/api/teams/{team_id}/exit-session",
        headers=student_a,
        json={
            "repository_submission_id": repo_id,
            "participant_user_ids": [id_a, id_b],
            "questions_per_student": 2,
            "target_duration_minutes": 25,
        },
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    assert len(created.json()["questions"]) == 4

    for headers in (student_a, student_b):
        cons = client.post(
            f"/api/exit-sessions/{session_id}/consent",
            headers=headers,
            json={"granted": True},
        )
        assert cons.status_code == 200, cons.text

    started = client.post(f"/api/exit-sessions/{session_id}/start", headers=student_a)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "question"
    assert started.json()["current_participant_user_id"] == id_a

    for _ in range(2):
        ans = client.post(
            f"/api/exit-sessions/{session_id}/answers",
            headers=student_a,
            json={
                "text": (
                    "This unit owns booking validation and capacity boundaries. "
                    "Callers should handle ValueError on over-capacity and slot conflicts. "
                    "I verified the behavior with regression tests around capacity."
                )
            },
        )
        assert ans.status_code == 200, ans.text

    mid = client.get(f"/api/exit-sessions/{session_id}", headers=student_b).json()
    assert mid["current_participant_user_id"] == id_b

    for _ in range(2):
        ans = client.post(
            f"/api/exit-sessions/{session_id}/answers",
            headers=student_b,
            json={
                "text": (
                    "The service checks headcount against capacity and rejects overbooking. "
                    "Acceptance would confirm a lecturer cannot book beyond the room limit."
                )
            },
        )
        assert ans.status_code == 200, ans.text

    finished = client.post(f"/api/exit-sessions/{session_id}/finish", headers=student_b)
    assert finished.status_code == 200, finished.text
    assert finished.json()["session"]["status"] == "lecturer_review"
    assert len(finished.json()["reports"]) == 2

    report = client.get(f"/api/exit-sessions/{session_id}/report", headers=student_a)
    assert report.status_code == 200
    assert len(report.json()["assessments"]) == 2


def test_join_by_invite(client):
    student_a = _login(client, "studenta", "password123")
    student_b = _login(client, "studentb", "password123")
    created = client.post("/api/teams", headers=student_a, json={"name": "Invite Team"})
    assert created.status_code == 201
    code = created.json()["invite_code"]
    joined = client.post("/api/teams/join", headers=student_b, json={"invite_code": code})
    assert joined.status_code == 200, joined.text
    ids = {m["user_id"] for m in joined.json()["members"]}
    assert _user_id(client, student_a) in ids
    assert _user_id(client, student_b) in ids


def test_policy_public(client):
    response = client.get("/api/policy")
    assert response.status_code == 200
    body = response.json()
    assert "consent" in body
    assert body["voice"]["grading_uses_audio_cues"] is False
