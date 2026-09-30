def project(client, name="p"):
    response = client.post(
        "/api/projects",
        json={"name": name, "repository": f"test/{name}", "mode": "demo"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def task(client, pid):
    response = client.post(
        "/api/tasks",
        json={
            "project_id": pid,
            "title": "Implement",
            "task_type": "功能开发",
            "estimated_hours": 2,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_health_projects_duplicate_and_missing(client):
    assert client.get("/api/health").status_code == 200
    pid = project(client)
    assert client.get(f"/api/projects/{pid}").json()["name"] == "p"
    assert client.get("/api/projects?mode=live").json() == []
    assert (
        client.post(
            "/api/projects", json={"name": "p", "repository": "test/p"}
        ).status_code
        == 409
    )
    assert client.get("/api/tasks/999").status_code == 404


def test_task_full_history_and_summary(client):
    pid = project(client)
    tid = task(client, pid)
    interaction = {
        "task_id": tid,
        "tool": "Codex",
        "stage": "功能开发",
        "purpose": "write validation",
        "prompt_summary": "redacted",
        "estimated_before_hours": 2,
        "actual_hours": 1,
        "accepted_count": 1,
    }
    assert client.post("/api/interactions", json=interaction).status_code == 201
    assert (
        client.post(
            "/api/tests", json={"task_id": tid, "name": "unit", "passed": 3, "total": 4}
        ).status_code
        == 201
    )
    defect = client.post("/api/defects", json={"task_id": tid, "title": "boundary"})
    assert defect.status_code == 201
    assert (
        client.post(
            "/api/retrospectives",
            json={
                "task_id": tid,
                "summary": "missed boundary",
                "action_item": "add regression",
            },
        ).status_code
        == 201
    )
    detail = client.get(f"/api/tasks/{tid}").json()
    assert detail["uses_ai"] is True
    assert detail["first_test_passed"] is False
    assert detail["defect_count"] == 1
    assert detail["ai_summary"]["accepted_count"] == 1
    assert len(detail["timeline"]) == 5


def test_cross_project_and_invalid_window(client):
    p1, p2 = project(client, "one"), project(client, "two")
    req = client.post("/api/requirements", json={"project_id": p1, "title": "r"}).json()
    assert (
        client.post(
            "/api/tasks",
            json={
                "project_id": p2,
                "requirement_id": req["id"],
                "title": "x",
                "task_type": "功能开发",
                "estimated_hours": 1,
            },
        ).status_code
        == 422
    )
    assert client.get("/api/metrics?start=2026-01-02&end=2026-01-01").status_code == 422
    assert client.get("/api/metrics?mode=unknown").status_code == 422


def test_secret_not_echoed_in_error(client):
    tid = task(client, project(client))
    secret = "ghp_" + "a" * 30
    response = client.post(
        "/api/interactions",
        json={
            "task_id": tid,
            "tool": "Codex",
            "stage": "功能开发",
            "purpose": "x",
            "prompt_summary": secret,
            "estimated_before_hours": 2,
            "actual_hours": 1,
        },
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_write_auth(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "devflow_api_key", "test-only")
    assert (
        client.post(
            "/api/projects", json={"name": "x", "repository": "test/x"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/projects",
            headers={"X-API-Key": "test-only"},
            json={"name": "x", "repository": "test/x"},
        ).status_code
        == 201
    )
