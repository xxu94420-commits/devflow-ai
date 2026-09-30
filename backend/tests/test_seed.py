def test_seed_is_idempotent_and_live_empty(client):
    first = client.post("/api/demo/seed")
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert client.post("/api/demo/seed").json()["created"] is False
    assert len(client.get("/api/tasks?mode=demo").json()) == 42
    assert client.get("/api/tasks?mode=live").json() == []
    metrics = client.get("/api/metrics?mode=demo").json()
    assert metrics["data_label"] == "synthetic/demo data"
    assert metrics["metrics"]["ai_time_saving"]["value"] is None
    detail = client.get("/api/tasks/1").json()
    assert detail["requirement"]
    assert detail["commits"] and detail["pull_requests"]
