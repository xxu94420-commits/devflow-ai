import hashlib

import httpx
import pytest
from sqlalchemy import select
from test_junit import XML, bundle

from app import ci
from app import models as m
from app.db import get_db
from app.main import app


def setup_project(client):
    project = client.post(
        "/api/projects",
        json={"name": "real source fixture", "repository": "acme/demo", "mode": "live"},
    ).json()
    task = client.post(
        "/api/tasks",
        json={
            "project_id": project["id"],
            "title": "test ingestion",
            "task_type": "功能开发",
            "estimated_hours": 2,
            "created_at": "2026-09-01T00:00:00",
        },
    ).json()
    return project, task


def transport_factory(attempt=1, variant="available", prs=None):
    content = bundle({"backend.xml": XML})
    if variant == "partial":
        content = bundle({"backend.xml": XML}, ["backend.xml", "frontend.xml"])
    if variant == "invalid":
        content = b"invalid zip"

    def handle(req):
        path = req.url.path
        if path == "/repos/acme/demo":
            return httpx.Response(200, json={"private": False})
        raw = dict(
            id=1000,
            run_attempt=attempt,
            name="quality",
            head_sha="a" * 40,
            head_branch="feature",
            event="push",
            status="completed",
            conclusion="failure",
            pull_requests=prs or [],
            created_at="2026-09-10T10:00:00Z",
            run_started_at="2026-09-10T10:00:00Z",
        )
        if variant == "pending":
            raw.update(status="in_progress", conclusion=None)
        if path.endswith("/actions/runs"):
            if variant == "rate_limit":
                return httpx.Response(429, json={})
            return httpx.Response(200, json={"total_count": 1, "workflow_runs": [raw]})
        if path.endswith("/jobs"):
            if variant == "network":
                raise httpx.ConnectError("token-must-not-be-echoed", request=req)
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "jobs": [
                        {
                            "id": 88,
                            "name": "backend",
                            "status": raw["status"],
                            "conclusion": raw["conclusion"],
                            "completed_at": "2026-09-10T10:05:00Z",
                        }
                    ],
                },
            )
        if "/attempts/" in path:
            return httpx.Response(
                200, json={**raw, "run_attempt": int(path.rsplit("/", 1)[-1])}
            )
        if path.endswith("/artifacts"):
            number = int(req.url.params["name"].rsplit("-", 1)[-1])
            artifacts = (
                []
                if variant == "missing"
                else [
                    {
                        "id": 9000 + number,
                        "name": f"devflow-junit-{number}",
                        "expired": variant == "expired",
                        "size_in_bytes": len(content),
                        "workflow_run": {"head_sha": "a" * 40},
                        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                    }
                ]
            )
            return httpx.Response(200, json={"artifacts": artifacts})
        if path.endswith("/zip"):
            location = "https://reports.blob.core.windows.net/download"
            if variant == "unsafe":
                location = "http://127.0.0.1/secret"
            return httpx.Response(302, headers={"location": location})
        raise AssertionError(path)

    def cdn(req):
        assert "authorization" not in req.headers
        return httpx.Response(200, content=content)

    return httpx.MockTransport(handle), httpx.MockTransport(cdn)


def install_sync(monkeypatch, **options):
    transport, cdn = transport_factory(**options)
    original = ci.sync_project
    headers = (
        {}
        if options.get("variant") == "auth_required"
        else {"Authorization": "Bearer test-only"}
    )

    def sync(db, project, max_runs):
        with httpx.Client(
            base_url="https://api.github.com", transport=transport, headers=headers
        ) as api:
            with httpx.Client(transport=cdn) as downloader:
                return original(
                    db, project, max_runs, client=api, download_client=downloader
                )

    monkeypatch.setattr(ci, "sync_project", sync)


def add_commit_link(client, project, task):
    for db in app.dependency_overrides[get_db]():
        commit = m.Commit(
            project_id=project["id"], sha="a" * 40, message="real test fixture"
        )
        db.add(commit)
        db.commit()
        ident = commit.id
    client.put(
        f"/api/tasks/{task['id']}/links", json={"commit_ids": [ident]}
    ).raise_for_status()
    return ident


def test_sync_idempotence_counts_and_unique_task_link(client, monkeypatch):
    project, task = setup_project(client)
    add_commit_link(client, project, task)
    install_sync(monkeypatch)
    for _ in range(2):
        client.post(
            "/api/ci/sync", json={"project_id": project["id"]}
        ).raise_for_status()
    runs = client.get("/api/ci/runs").json()
    assert len(runs) == 1
    run = runs[0]
    assert run["task_id"] == task["id"] and run["association"] == "automatic"
    assert run["evidence_status"] == "available" and run["skipped"] == 1
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert len(detail["tests"]) == 1
    assert detail["tests"][0]["total"] == 3
    assert detail["tests"][0]["passed"] == 1
    assert any(event["kind"] == "ci_run" for event in detail["timeline"])
    assert detail["first_test_passed"] is False
    assert detail["defect_count"] == 0
    metrics = client.get(
        "/api/metrics?mode=live&start=2026-09-01&end=2026-10-01"
    ).json()
    assert metrics["metrics"]["test_pass_rate"]["value"] == 33.33
    assert client.get("/api/ci/runs?mode=demo").json() == []

    # An earlier unknown execution prevents a false first-pass conclusion.
    from datetime import datetime

    for db in app.dependency_overrides[get_db]():
        db.add(
            m.CIRun(
                project_id=project["id"],
                run_id=999,
                attempt=1,
                name="older",
                head_sha="b" * 40,
                status="completed",
                task_id=task["id"],
                created_at=datetime(2026, 9, 9),
                evidence_status="expired",
            )
        )
        db.commit()
    metrics = client.get(
        "/api/metrics?mode=live&start=2026-09-01&end=2026-10-01"
    ).json()
    assert metrics["metrics"]["first_test_pass_rate"]["value"] is None
    assert client.get(f"/api/tasks/{task['id']}").json()["first_test_passed"] is None


@pytest.mark.parametrize(
    "variant",
    ["missing", "expired", "partial", "invalid", "auth_required", "pending", "unsafe"],
)
def test_unknown_or_partial_does_not_pollute_task_metrics(client, monkeypatch, variant):
    project, task = setup_project(client)
    add_commit_link(client, project, task)
    install_sync(monkeypatch, variant=variant)
    client.post("/api/ci/sync", json={"project_id": project["id"]}).raise_for_status()
    run = client.get("/api/ci/runs").json()[0]
    assert run["evidence_status"] == ("invalid" if variant == "unsafe" else variant)
    assert client.get(f"/api/tasks/{task['id']}").json()["tests"] == []


def test_rerun_backfills_attempts_without_replacing_first(client, monkeypatch):
    project, task = setup_project(client)
    add_commit_link(client, project, task)
    install_sync(monkeypatch, attempt=2)
    client.post("/api/ci/sync", json={"project_id": project["id"]}).raise_for_status()
    assert {r["attempt"] for r in client.get("/api/ci/runs").json()} == {1, 2}
    assert len(client.get(f"/api/tasks/{task['id']}").json()["tests"]) == 2


def test_ambiguous_association_and_manual_resolution(client, monkeypatch):
    project, task = setup_project(client)
    commit_id = add_commit_link(client, project, task)
    other = client.post(
        "/api/tasks",
        json={
            "project_id": project["id"],
            "title": "another",
            "task_type": "功能开发",
            "estimated_hours": 1,
        },
    ).json()
    client.put(
        f"/api/tasks/{other['id']}/links", json={"commit_ids": [commit_id]}
    ).raise_for_status()
    install_sync(monkeypatch)
    client.post("/api/ci/sync", json={"project_id": project["id"]}).raise_for_status()
    run = client.get("/api/ci/runs").json()[0]
    assert run["association"] == "ambiguous" and run["task_id"] is None
    assert len(run["candidate_task_ids"]) == 2
    response = client.put(
        f"/api/ci/runs/{run['id']}/task", json={"task_id": task["id"]}
    )
    assert response.status_code == 200 and response.json()["association"] == "manual"
    client.post("/api/ci/sync", json={"project_id": project["id"]}).raise_for_status()
    assert len(client.get(f"/api/tasks/{task['id']}").json()["tests"]) == 1
    client.put(
        f"/api/ci/runs/{run['id']}/task", json={"task_id": None}
    ).raise_for_status()
    assert client.get(f"/api/tasks/{task['id']}").json()["tests"] == []


def test_late_pr_link_and_cross_project_rejected(client, monkeypatch):
    project, task = setup_project(client)
    install_sync(monkeypatch, prs=[{"number": 13}])
    client.post("/api/ci/sync", json={"project_id": project["id"]}).raise_for_status()
    run = client.get("/api/ci/runs").json()[0]
    assert run["association"] == "unlinked"
    for db in app.dependency_overrides[get_db]():
        pr = m.PullRequest(project_id=project["id"], number=13, title="PR fixture")
        db.add(pr)
        db.commit()
        pr_id = pr.id
    client.put(
        f"/api/tasks/{task['id']}/links", json={"pr_ids": [pr_id]}
    ).raise_for_status()
    assert len(client.get(f"/api/tasks/{task['id']}").json()["tests"]) == 1
    client.post("/api/demo/seed").raise_for_status()
    demo_task = client.get("/api/tasks?mode=demo").json()[0]
    assert (
        client.put(
            f"/api/ci/runs/{run['id']}/task", json={"task_id": demo_task["id"]}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("variant,status", [("network", 502), ("rate_limit", 429)])
def test_failed_sync_rolls_back_and_does_not_echo_credentials(
    client, monkeypatch, variant, status
):
    project, _ = setup_project(client)
    install_sync(monkeypatch, variant=variant)
    response = client.post("/api/ci/sync", json={"project_id": project["id"]})
    assert response.status_code == status
    assert "token-must-not-be-echoed" not in response.text
    assert client.get("/api/ci/runs").json() == []
    for db in app.dependency_overrides[get_db]():
        assert db.scalars(select(m.TestResult)).all() == []
