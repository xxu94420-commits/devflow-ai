import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import Project, Task


@pytest.mark.parametrize("key", ["", "valid-test-key"])
def test_readonly_rejects_all_mutations_without_changing_data(client, monkeypatch, key):
    client.post("/api/demo/seed").raise_for_status()
    settings = get_settings()
    monkeypatch.setattr(settings, "devflow_api_key", "valid-test-key")
    monkeypatch.setattr(settings, "read_only", True)
    headers = {"X-API-Key": key}
    writes = [
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"GET", "HEAD", "OPTIONS"}
    ]
    assert len(writes) >= 10
    for path, method in writes:
        # Deliberately invalid bodies/IDs must be blocked before validation or I/O.
        response = client.request(method, path, json={}, headers=headers)
        assert response.status_code == 403, (path, response.text)
    for method in ["DELETE", "PATCH", "POST", "PUT"]:
        assert client.request(method, "/api/future-route").status_code == 403
    for session in app.dependency_overrides[get_db]():
        assert session.scalar(select(func.count(Project.id))) == 1
        assert session.scalar(select(func.count(Task.id))) == 42
    assert client.get("/api/capabilities").json() == {"read_only": True}
    projects = client.get("/api/projects").json()
    tasks = client.get("/api/tasks").json()
    for path in [
        "/api/health",
        "/api/metrics",
        "/api/reports",
        "/api/reports/download",
        f"/api/projects/{projects[0]['id']}",
        f"/api/tasks/{tasks[0]['id']}",
    ]:
        assert client.get(path).status_code == 200, path
    assert (
        "attachment"
        in client.get("/api/reports/download").headers["content-disposition"]
    )


def test_local_mode_still_allows_writes(client):
    assert client.get("/api/capabilities").json() == {"read_only": False}
    assert client.post("/api/demo/seed").status_code == 200
