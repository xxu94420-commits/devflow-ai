"""Read-only deployment acceptance; never use against a writable workspace."""

import argparse

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("url", help="Verified public demo origin or local preview origin")
args = parser.parse_args()

with httpx.Client(base_url=args.url.rstrip("/"), timeout=30) as client:
    response = client.get("/api/capabilities")
    response.raise_for_status()
    assert response.json() == {"read_only": True}, "Refuse tests on a writable service"
    html = client.get("/")
    html.raise_for_status()
    assert 'id="root"' in html.text
    demo = client.get("/api/projects?mode=demo").json()
    live = client.get("/api/projects?mode=live").json()
    tasks = client.get("/api/tasks?mode=demo").json()
    assert len(demo) == 1 and len(tasks) == 42
    assert all(p["repository"] == "xxu94420-commits/devflow-ai" for p in live)
    for path in [
        "/api/health",
        "/api/metrics?mode=demo",
        "/api/metrics?mode=live",
        f"/api/projects/{demo[0]['id']}",
        f"/api/tasks/{tasks[0]['id']}",
        "/api/reports?mode=demo",
        "/api/ci/status",
        "/api/review/connections",
        "/api/review/trial",
        "/api/ci/runs?mode=live",
    ]:
        client.get(path).raise_for_status()
    trial = client.get("/api/review/trial").json()
    assert client.post("/api/review/trial", json={}).status_code == (
        422 if trial["enabled"] else 403
    )  # Invalid input never invokes a model.
    download = client.get("/api/reports/download?mode=demo")
    download.raise_for_status()
    assert "attachment" in download.headers["content-disposition"]
    assert "synthetic/demo data" in download.text
    for method, path in [
        ("POST", "/api/demo/seed"),
        ("POST", "/api/github/import"),
        ("POST", "/api/tasks"),
        ("POST", "/api/interactions"),
        ("POST", "/api/ci/sync"),
        ("PUT", "/api/ci/runs/1/task"),
        ("PUT", f"/api/tasks/{tasks[0]['id']}"),
        ("DELETE", "/api/future-route"),
        ("PATCH", "/api/future-route"),
    ]:
        assert client.request(method, path, json={}).status_code == 403, path
    assert client.get("/api/tasks?mode=demo").json() == tasks
    assert client.get("/api/projects?mode=demo").json() == demo
    for path in ["/.env", "/api/missing"]:
        assert client.get(path).status_code == 404, path
    print(f"PASS: {len(tasks)} synthetic tasks; {len(live)} real repositories")
    print("PASS: homepage, metrics, project/task details, Markdown attachment")
    print("PASS: writes rejected; records unchanged; unknown/private paths absent")
