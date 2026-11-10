SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_exit_interview_shared_login_names(client):
    """One cohort account owns the team; participants are typed names."""
    headers = _login(client, "studenta", "password123")

    team = client.post(
        "/api/teams",
        headers=headers,
        json={"name": "Exit Team", "scenario_slug": "library"},
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    assert "invite_code" not in team.json()
    assert len(team.json()["members"]) == 1

    repo = client.post(
        f"/api/teams/{team_id}/repository",
        headers=headers,
        json={"github_url": "fixture://demo", "commit_sha": SHA, "analyze_now": True},
    )
    assert repo.status_code == 201, repo.text
    assert repo.json()["index_status"] == "ready", repo.json()
    repo_id = repo.json()["id"]

    created = client.post(
        f"/api/teams/{team_id}/exit-session",
        headers=headers,
        json={
            "repository_submission_id": repo_id,
            "participant_names": ["Alex Rivera", "Jordan Lee"],
            "questions_per_student": 2,
            "target_duration_minutes": 25,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    session_id = body["id"]
    assert len(body["questions"]) == 4
    assert [p["display_name"] for p in body["participants"]] == ["Alex Rivera", "Jordan Lee"]
    assert all(p["user_id"] < 0 for p in body["participants"])

    # Join / invite endpoints are gone (405 if "{team_id}" catches "join")
    assert client.post("/api/teams/join", headers=headers, json={"invite_code": "ABCD"}).status_code in {
        404,
        405,
    }
    assert (
        client.post(
            f"/api/teams/{team_id}/members",
            headers=headers,
            json={"usernames": ["studentb"]},
        ).status_code
        in {404, 405}
    )

    cons = client.post(
        f"/api/exit-sessions/{session_id}/consent",
        headers=headers,
        json={"granted": True},
    )
    assert cons.status_code == 200, cons.text
    assert cons.json()["consent_status"] == "granted"
    assert all(p["consent_status"] == "granted" for p in cons.json()["participants"])

    started = client.post(f"/api/exit-sessions/{session_id}/start", headers=headers)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "question"
    assert started.json()["current_participant_name"] == "Alex Rivera"

    for _ in range(2):
        ans = client.post(
            f"/api/exit-sessions/{session_id}/answers",
            headers=headers,
            json={
                "text": (
                    "This unit owns booking validation and capacity boundaries. "
                    "Callers should handle ValueError on over-capacity and slot conflicts. "
                    "I verified the behavior with regression tests around capacity."
                )
            },
        )
        assert ans.status_code == 200, ans.text

    mid = client.get(f"/api/exit-sessions/{session_id}", headers=headers).json()
    assert mid["current_participant_name"] == "Jordan Lee"

    for _ in range(2):
        ans = client.post(
            f"/api/exit-sessions/{session_id}/answers",
            headers=headers,
            json={
                "text": (
                    "The service checks headcount against capacity and rejects overbooking. "
                    "Acceptance would confirm a lecturer cannot book beyond the room limit."
                )
            },
        )
        assert ans.status_code == 200, ans.text

    finished = client.post(f"/api/exit-sessions/{session_id}/finish", headers=headers)
    assert finished.status_code == 200, finished.text
    assert finished.json()["session"]["status"] == "lecturer_review"
    reports = finished.json()["reports"]
    assert len(reports) == 2
    assert {r["display_name"] for r in reports} == {"Alex Rivera", "Jordan Lee"}

    report = client.get(f"/api/exit-sessions/{session_id}/report", headers=headers)
    assert report.status_code == 200
    assert len(report.json()["assessments"]) == 2
    assert {a["display_name"] for a in report.json()["assessments"]} == {
        "Alex Rivera",
        "Jordan Lee",
    }


def test_policy_public(client):
    response = client.get("/api/policy")
    assert response.status_code == 200
    body = response.json()
    assert "consent" in body
    assert body["voice"]["grading_uses_audio_cues"] is False
